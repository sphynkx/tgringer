/* ## Recording logic (owner-only) using canvas composition of the actual stage video
   ## Features:
   ## - Records stage video only (not thumbnails)
   ## - Name overlay of current staged participant
   ## - Streams chunks to server (start/chunk/finish)
   ## - Pause: recorder.pause() + gating chunk upload
   ## - Optional master dynamics compressor (WebAudio) with toggle
   ## Notes:
   ## - ASCII-only comments
*/

(function(){
  const App = window.App;
  if (!App || !App.state.isOwnerByLink) return;

  const { refs, state } = App;

  /* UI elements */

  const recordBtn = document.getElementById('recordBtn');
  const pauseBtn = document.getElementById('pauseRecordBtn');
  const stopBtn = document.getElementById('stopRecordBtn');
  const recordStatusEl = document.getElementById('recordStatus');
  const sendToBotChk = document.getElementById('sendToBotChk');

  /* Optional compressor toggle UI (injected if not present) */

  let compressAudioChk = document.getElementById('compressAudioChk');

  if (!compressAudioChk) {
    const ownerControls = document.getElementById('ownerRecordControls');
    if (ownerControls) {
      const wrap = document.createElement('label');
      wrap.style.cssText = 'font-size:12px;display:flex;align-items:center;gap:4px;';
      const inp = document.createElement('input');
      inp.type = 'checkbox';
      inp.id = 'compressAudioChk';
      /* Default disabled; can be overridden via global flag */
      inp.checked = !!window.REC_USE_COMPRESSOR;
      const txt = document.createTextNode('Audio compressor');
      wrap.appendChild(inp);
      wrap.appendChild(txt);
      ownerControls.insertBefore(wrap, recordStatusEl);
      compressAudioChk = inp;
    }
  }


  /* Canvas 1280x720 */

  const recCanvas = document.createElement('canvas');
  recCanvas.width = 1280;
  recCanvas.height = 720;
  const ctx = recCanvas.getContext('2d');


  /* State */

  let recorder = null;
  let recordingId = null;
  let startedTs = null;

  let audioCtx = null;
  let mixDest = null;

  /* optional chain nodes */
  let compNode = null;
  let masterGain = null;

  let paused = false;
  let chunkSeq = 0;


  /* Helpers */

  function setStatus(t) {
    recordStatusEl.textContent = t;
  }


  function broadcast(type) {
    const ws = state.ws;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, timestamp: Date.now() }));
    }
  }


  function shouldUseCompressor() {
    if (compressAudioChk) return !!compressAudioChk.checked;
    return !!window.REC_USE_COMPRESSOR;
  }


  /* Draw loop from the real stage video and overlay current stage name */

  function drawLoop() {
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, recCanvas.width, recCanvas.height);

    const stageVideo = refs.stageVideo;
    if (stageVideo && stageVideo.readyState >= 2) {
      const vw = stageVideo.videoWidth || 640;
      const vh = stageVideo.videoHeight || 480;
      const ratio = Math.min(recCanvas.width / vw, recCanvas.height / vh);
      const dw = Math.floor(vw * ratio);
      const dh = Math.floor(vh * ratio);
      const dx = Math.floor((recCanvas.width - dw) / 2);
      const dy = Math.floor((recCanvas.height - dh) / 2);
      try { ctx.drawImage(stageVideo, dx, dy, dw, dh); } catch {}
    }

    const meta = App.getStageMeta ? App.getStageMeta() : { name: 'User' };
    const name = meta.name || 'User';

    ctx.font = '20px system-ui, sans-serif';
    const padX = 10, padY = 6;
    const metrics = ctx.measureText(name);
    const boxW = Math.ceil(metrics.width) + padX * 2;
    const boxH = 28 + padY * 2;

    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(16, recCanvas.height - boxH - 16, boxW, boxH);

    ctx.fillStyle = '#ffffff';
    ctx.fillText(name, 16 + padX, recCanvas.height - boxH - 16 + padY + 20);

    requestAnimationFrame(drawLoop);
  }
  requestAnimationFrame(drawLoop);


  /* WebAudio mix chain:
     Sources (local + all remote audio tracks) -> [DynamicsCompressor?] -> MasterGain -> MediaStreamDestination
     Compressor is optional, decided at recording start (not switched live during a recording)
  */

  function buildMixedAudioStream() {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    mixDest = audioCtx.createMediaStreamDestination();

    /* Create chain nodes */
    const useComp = shouldUseCompressor();

    if (useComp) {
      compNode = audioCtx.createDynamicsCompressor();
      /* Typical podcast-ish settings; tweak as needed */
      try {
        compNode.threshold.value = -24;   /* dB */
        compNode.knee.value = 30;         /* dB */
        compNode.ratio.value = 12;        /* unitless */
        compNode.attack.value = 0.003;    /* s */
        compNode.release.value = 0.25;    /* s */
      } catch(_) {}
    } else {
      compNode = null;
    }

    masterGain = audioCtx.createGain();
    /* Gentle headroom to avoid clipping after summation */
    masterGain.gain.value = 0.9;

    /* Wire chain end */
    if (useComp && compNode) {
      compNode.connect(masterGain);
    }
    masterGain.connect(mixDest);

    /* Connect each source to chain input */
    const chainInput = (useComp && compNode) ? compNode : masterGain;

    const added = new Set();

    function addTrack(track) {
      if (!track || track.kind !== 'audio') return;
      if (added.has(track.id)) return;
      added.add(track.id);
      const temp = new MediaStream([track]);
      const src = audioCtx.createMediaStreamSource(temp);
      src.connect(chainInput);
    }

    /* Local */
    const local = state.localStream;
    if (local) local.getAudioTracks().forEach(addTrack);

    /* Remote */
    for (const [, e] of state.peers.entries()) {
      if (e && e.video && e.video.srcObject) {
        e.video.srcObject.getAudioTracks().forEach(addTrack);
      }
    }

    return mixDest.stream;
  }


  /* Recording control */

  async function startRecording() {
    const formStart = new FormData();
    formStart.append('room_id', state.roomId || '');
    formStart.append('owner_uid', state.myUid || '');
    const respStart = await fetch('/record/start', { method: 'POST', body: formStart });
    if (!respStart.ok) { alert('Failed to start recording'); return; }
    const dataStart = await respStart.json();
    recordingId = dataStart.recording_id;
    startedTs = dataStart.started_ts;

    const vStream = recCanvas.captureStream(30);
    const aStream = buildMixedAudioStream();

    const combined = new MediaStream();
    vStream.getVideoTracks().forEach(t => combined.addTrack(t));
    aStream.getAudioTracks().forEach(t => combined.addTrack(t));

    paused = false;
    chunkSeq = 0;

    recorder = new MediaRecorder(combined, { mimeType: 'video/webm;codecs=vp8,opus' });

    recorder.ondataavailable = async (e) => {
      if (!e.data || e.data.size === 0) return;
      if (paused) return;
      chunkSeq++;
      const formChunk = new FormData();
      formChunk.append('recording_id', recordingId);
      formChunk.append('seq', String(chunkSeq));
      formChunk.append('file', new File([e.data], `chunk-${chunkSeq}.webm`, { type: e.data.type }));
      try { await fetch('/record/chunk', { method: 'POST', body: formChunk }); }
      catch (err) { console.warn('[REC] chunk send failed seq=', chunkSeq, err); }
    };

    recorder.onstop = async () => {
      setStatus('Finishing...');
      await finishRecording();
    };

    recorder.start(2000);
    setStatus('Recording...');
    recordBtn.disabled = true;
    pauseBtn.disabled = false;
    stopBtn.disabled = false;
    broadcast('record-start');
  }


  function pauseRecording() {
    if (!recorder) return;
    if (paused) {
      try { recorder.resume(); } catch {}
      paused = false;
      setStatus('Recording...');
      pauseBtn.textContent = 'Pause';
      broadcast('record-resume');
    } else {
      try { recorder.pause(); } catch {}
      paused = true;
      setStatus('Paused');
      pauseBtn.textContent = 'Resume';
      broadcast('record-pause');
    }
  }


  async function finishRecording() {
    const sendFlag = sendToBotChk && sendToBotChk.checked ? '1' : '0';
    const formFinish = new FormData();
    formFinish.append('recording_id', recordingId);
    formFinish.append('send_to_bot', sendFlag);
    const resp = await fetch('/record/finish', { method: 'POST', body: formFinish });
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.url) showDownloadLink(data.url);
      setStatus('Uploaded');
    } else {
      setStatus('Upload failed');
    }

    /* Cleanup local state */
    try {
      if (audioCtx) {
        /* Closing AudioContext is optional; browsers may block it */
        if (audioCtx.close) { await audioCtx.close(); }
      }
    } catch(_) {}

    recorder = null;
    recordingId = null;
    recordBtn.disabled = false;
    pauseBtn.disabled = true;
    stopBtn.disabled = true;
    pauseBtn.textContent = 'Pause';
    broadcast('record-stop');
  }


  function stopRecording() {
    if (!recorder) return;
    setStatus('Stopping...');
    pauseBtn.disabled = true;
    stopBtn.disabled = true;
    try { recorder.stop(); } catch {}
  }


  function showDownloadLink(url) {
    let box = document.getElementById('recordDownloadBox');
    if (!box) {
      box = document.createElement('div');
      box.id = 'recordDownloadBox';
      box.style.marginTop = '8px';
      document.querySelector('.card').appendChild(box);
    }
    box.innerHTML = `<a href="${url}" target="_blank" style="color:#5b8cfe;">Download recording</a>`;
  }


  /* Expose stop for hangup auto-finalize */

  window.STOP_ACTIVE_RECORDING = stopRecording;


  /* Wire controls */

  recordBtn.onclick = startRecording;
  pauseBtn.onclick = pauseRecording;
  stopBtn.onclick = stopRecording;


  /* Initial state */

  setStatus('Idle');
  recordBtn.disabled = false;
  pauseBtn.disabled = true;
  stopBtn.disabled = true;
})();