/* ## Recording logic (owner-only), canvas composition, chunk upload, bot notify */
(function(){
  const App = window.App;
  if (!App || !App.state.isOwnerByLink) return;

  const { refs, state } = App;

  const recordBtn = document.getElementById('recordBtn');
  const pauseBtn  = document.getElementById('pauseRecordBtn');
  const stopBtn   = document.getElementById('stopRecordBtn');
  const recordStatusEl = document.getElementById('recordStatus');
  const sendToBotChk   = document.getElementById('sendToBotChk');
  const recordSysAudioChk = document.getElementById('recordSysAudioChk');

  const recCanvas = document.createElement('canvas');
  recCanvas.width = 1280; recCanvas.height = 720;
  const ctx = recCanvas.getContext('2d');

  const lastFrameCanvas = document.createElement('canvas');
  lastFrameCanvas.width = recCanvas.width; lastFrameCanvas.height = recCanvas.height;
  const lastCtx = lastFrameCanvas.getContext('2d');

  const STAGE_DEBOUNCE_MS = 150;

  let recorder = null, recordingId = null, startedTs = null;
  let audioCtx = null, mixDest = null, compNode = null, masterGain = null;
  let paused = false, chunkSeq = 0;

  function setStatus(t) { recordStatusEl.textContent = t; }
  function isStageInDebounce() {
    const ts = (typeof window.__STAGE_SWITCH_TS === 'number') ? window.__STAGE_SWITCH_TS : 0;
    return ts && (Date.now() - ts) < STAGE_DEBOUNCE_MS;
  }

  function drawLoop() {
    if (isStageInDebounce()) {
      try { ctx.drawImage(lastFrameCanvas, 0, 0, recCanvas.width, recCanvas.height); }
      catch(_){ ctx.fillStyle = '#000'; ctx.fillRect(0,0,recCanvas.width,recCanvas.height); }
      requestAnimationFrame(drawLoop); return;
    }
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, recCanvas.width, recCanvas.height);
    const stageVideo = refs.stageVideo;
    if (stageVideo && stageVideo.readyState >= 2) {
      const vw = stageVideo.videoWidth || 640, vh = stageVideo.videoHeight || 480;
      const ratio = Math.min(recCanvas.width / vw, recCanvas.height / vh);
      const dw = Math.floor(vw * ratio), dh = Math.floor(vh * ratio);
      const dx = Math.floor((recCanvas.width - dw) / 2), dy = Math.floor((recCanvas.height - dh) / 2);
      try { ctx.drawImage(stageVideo, dx, dy, dw, dh); } catch(_){}
    }
    const meta = App.getStageMeta ? App.getStageMeta() : { name: state.meName || 'User' };
    const name = meta.name || state.meName || 'User';
    ctx.font = '20px system-ui, sans-serif';
    const padX = 10, padY = 6; const metrics = ctx.measureText(name);
    const boxW = Math.ceil(metrics.width) + padX * 2; const boxH = 28 + padY * 2;
    ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fillRect(16, recCanvas.height - boxH - 16, boxW, boxH);
    ctx.fillStyle = '#ffffff'; ctx.fillText(name, 16 + padX, recCanvas.height - boxH - 16 + padY + 20);
    try { lastCtx.drawImage(recCanvas, 0, 0, lastFrameCanvas.width, lastFrameCanvas.height); } catch(_){}
    requestAnimationFrame(drawLoop);
  }
  requestAnimationFrame(drawLoop);

  function buildMixedAudioStream() {
    const AC = window.AudioContext || window.webkitAudioContext;
    audioCtx = new AC();
    mixDest = audioCtx.createMediaStreamDestination();
    const compChk = document.getElementById('compressAudioChk');
    const useComp = !!(compChk && compChk.checked);
    if (useComp) {
      try {
        const comp = audioCtx.createDynamicsCompressor();
        comp.threshold.value = -24; comp.knee.value = 30; comp.ratio.value = 12; comp.attack.value = 0.003; comp.release.value = 0.25;
        compNode = comp;
      } catch(_){}
    }
    masterGain = audioCtx.createGain(); masterGain.gain.value = 0.9;
    if (compNode) compNode.connect(masterGain); masterGain.connect(mixDest);
    const chainInput = compNode || masterGain;
    const added = new Set();
    function addTrack(track) {
      if (!track || track.kind !== 'audio') return;
      if (added.has(track.id)) return;
      added.add(track.id);
      const temp = new MediaStream([track]);
      const src = audioCtx.createMediaStreamSource(temp);
      src.connect(chainInput);
    }
    const local = state.localStream; if (local) local.getAudioTracks().forEach(addTrack);
    for (const [, e] of state.peers.entries()) {
      if (e && e.video && e.video.srcObject) e.video.srcObject.getAudioTracks().forEach(addTrack);
    }
    if (recordSysAudioChk && recordSysAudioChk.checked) {
      const ss = state.screenStream; if (ss) { const sa = ss.getAudioTracks(); if (sa && sa.length) sa.forEach(addTrack); }
    }
    return mixDest.stream;
  }

  async function startRecording() {
    const formStart = new FormData();
    formStart.append('room_id', state.roomId || '');
    formStart.append('owner_uid', state.myUid || state.ownerUid || '');
    formStart.append('chat_id', state.chatId || state.myUid || state.ownerUid || '');
    console.log('[REC] start payload', {
      room_id: state.roomId, owner_uid: (state.myUid || state.ownerUid || ''), chat_id: (state.chatId || state.myUid || state.ownerUid || '')
    });

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

    paused = false; chunkSeq = 0;

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
    recordBtn.disabled = true; pauseBtn.disabled = false; stopBtn.disabled = false;
  }

  function pauseRecording() {
    if (!recorder) return;
    if (paused) {
      try { recorder.resume(); } catch(_){}
      paused = false; setStatus('Recording...'); pauseBtn.textContent = 'Pause';
    } else {
      try { recorder.pause(); } catch(_){}
      paused = true; setStatus('Paused'); pauseBtn.textContent = 'Resume';
    }
  }

  async function finishRecording() {
    const sendFlag = (sendToBotChk && sendToBotChk.checked) ? '1' : '0';
    const formFinish = new FormData();
    formFinish.append('recording_id', recordingId);
    formFinish.append('send_to_bot', sendFlag);
    formFinish.append('owner_uid', state.myUid || state.ownerUid || '');
    formFinish.append('chat_id', state.chatId || state.myUid || state.ownerUid || '');
    console.log('[REC] finish payload', {
      recording_id: recordingId, send_to_bot: sendFlag,
      owner_uid: (state.myUid || state.ownerUid || ''), chat_id: (state.chatId || state.myUid || state.ownerUid || '')
    });

    const resp = await fetch('/record/finish', { method: 'POST', body: formFinish });
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.url) showDownloadLink(data.url);
      setStatus('Uploaded');
    } else {
      setStatus('Upload failed');
    }

    try { if (audioCtx && audioCtx.close) await audioCtx.close(); } catch(_){}
    recorder = null; recordingId = null;
    recordBtn.disabled = false; pauseBtn.disabled = true; stopBtn.disabled = true; pauseBtn.textContent = 'Pause';
  }

  function stopRecording() {
    if (!recorder) return;
    setStatus('Stopping...'); pauseBtn.disabled = true; stopBtn.disabled = true;
    try { recorder.stop(); } catch(_){}
  }

  function showDownloadLink(url) {
    let box = document.getElementById('recordDownloadBox');
    if (!box) {
      box = document.createElement('div'); box.id = 'recordDownloadBox'; box.style.marginTop = '8px';
      document.querySelector('.card').appendChild(box);
    }
    box.innerHTML = `<a href="${url}" target="_blank" style="color:#5b8cfe;">Download recording</a>`;
  }

  window.STOP_ACTIVE_RECORDING = stopRecording;

  recordBtn.onclick = startRecording;
  pauseBtn.onclick = pauseRecording;
  stopBtn.onclick  = stopRecording;

  setStatus('Idle');
  recordBtn.disabled = false; pauseBtn.disabled = true; stopBtn.disabled = true;
})();