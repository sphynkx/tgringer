/* ## WebRTC signaling, peers, tiles, WebSocket, indicators, screen share */
(function(){
  const App = window.App;
  const { refs, state, utils, local, applyStage } = App;

  /* Call timer */

  let callTimerId = null;
  let callStartMs = 0;


  function pad2(n) {
    return String(n).padStart(2, '0');
  }


  function formatTime(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const hh = Math.floor(total / 3600);
    const mm = Math.floor((total % 3600) / 60);
    const ss = total % 60;
    return `${pad2(hh)}:${pad2(mm)}:${pad2(ss)}`;
  }


  function startCallTimer() {
    stopCallTimer(false);
    callStartMs = Date.now();
    callTimerId = setInterval(() => {
      const diff = Date.now() - callStartMs;
      if (refs.callTimer) refs.callTimer.textContent = formatTime(diff);
    }, 1000);
    if (refs.callTimer) refs.callTimer.textContent = "00:00:00";
  }


  function stopCallTimer(resetDisplay) {
    if (callTimerId) {
      clearInterval(callTimerId);
      callTimerId = null;
    }
    if (resetDisplay && refs.callTimer) {
      refs.callTimer.textContent = "00:00:00";
    }
  }


  function remotePeersCount() {
    let count = 0;
    for (const [pid] of state.peers.entries()) {
      if (pid !== 'local') count++;
    }
    return count;
  }


  function maybeStopTimerIfAlone() {
    if (!state.joined) return;
    if (remotePeersCount() === 0) {
      stopCallTimer(false);
    }
  }


  /* Debounce mark for stage switch */

  function markStageSwitch() {
    try { window.__STAGE_SWITCH_TS = Date.now(); } catch(_){}
  }


  /* Create local tile */

  function createLocalTile() {
    if (state.peers.has('local')) return;
    const card = document.createElement('div');
    card.className = 'thumb';
    card.dataset.peerId = 'local';

    const title = document.createElement('h4');
    const avWrap = document.createElement('div'); avWrap.className = 'avatar-wrap';
    const avImg = document.createElement('img'); avImg.className = 'avatar-img';
    const avInit = document.createElement('div'); avInit.className = 'avatar-initials';
    avWrap.appendChild(avImg); avWrap.appendChild(avInit);

    const nameSpan = document.createElement('span'); nameSpan.textContent = state.meName;
    const ownerBadge = document.createElement('span');
    ownerBadge.className = 'owner-badge';
    ownerBadge.textContent = '(owner)';
    ownerBadge.style.display = 'none';

    title.appendChild(avWrap);
    title.appendChild(nameSpan);
    title.appendChild(ownerBadge);

    const videoWrap = document.createElement('div');
    const localVideo = refs.localVideo;
    localVideo.style.width = '100%';
    localVideo.style.height = '110px';
    localVideo.style.objectFit = 'cover';
    localVideo.style.background = '#000';
    localVideo.style.borderRadius = '8px';
    videoWrap.appendChild(localVideo);

    card.appendChild(title);
    card.appendChild(videoWrap);
    refs.thumbsStrip.appendChild(card);

    const entry = {
      card,
      video: localVideo,
      name: state.meName,
      uid: state.myUid,
      avatar: state.myAvatar,
      isOwner: false,
      avatarImg: avImg,
      avatarInitials: avInit,
      nameLabel: nameSpan,
      ownerBadge,
    };
    state.peers.set('local', entry);
    local.setLocalAvatar();
    ensureThumbClick(card, 'local');
  }


  function ensureThumbClick(card, peerId) {
    if (!card) return;
    card.onclick = () => {
      state.userManuallyChoseStage = true;
      if (state.stagePeerId === peerId) {
        if (peerId !== 'local') {
          markStageSwitch();
          applyStage('local');
        }
      } else {
        markStageSwitch();
        applyStage(peerId);
      }
    };
  }


  /* Remote tile creation */

  function createRemoteTile(peerId, name, avatar, isOwner, uid) {
    let entry = state.peers.get(peerId);
    if (entry && entry.card) {
      entry.name = name || entry.name;
      entry.avatar = avatar || entry.avatar;
      entry.uid = uid || entry.uid;
      entry.isOwner = !!isOwner;
      if (entry.nameLabel) entry.nameLabel.textContent = entry.name;
      if (entry.ownerBadge) entry.ownerBadge.style.display = entry.isOwner ? '' : 'none';
      App.utils.setAvatarElements(entry.name, entry.avatar, entry.uid, entry.avatarImg, entry.avatarInitials);
      return entry.card;
    }

    const card = document.createElement('div');
    card.className = 'thumb';
    card.dataset.peerId = peerId;

    const title = document.createElement('h4');
    const avWrap = document.createElement('div'); avWrap.className = 'avatar-wrap';
    const avImg = document.createElement('img'); avImg.className = 'avatar-img';
    const avInit = document.createElement('div'); avInit.className = 'avatar-initials';
    avWrap.appendChild(avImg); avWrap.appendChild(avInit);

    const nameSpan = document.createElement('span'); nameSpan.textContent = name || 'Remote';
    const ownerBadge = document.createElement('span');
    ownerBadge.className = 'owner-badge';
    ownerBadge.textContent = '(owner)';
    ownerBadge.style.display = isOwner ? '' : 'none';

    title.appendChild(avWrap);
    title.appendChild(nameSpan);
    title.appendChild(ownerBadge);

    const video = document.createElement('video');
    video.autoplay = true;
    video.playsInline = true;
    video.style.width = '100%';
    video.style.height = '110px';
    video.style.objectFit = 'cover';
    video.style.background = '#000';
    video.style.borderRadius = '8px';

    card.appendChild(title);
    card.appendChild(video);
    refs.thumbsStrip.appendChild(card);

    entry = {
      card,
      video,
      name: name || 'Remote',
      uid: uid || '',
      avatar: avatar || '',
      isOwner: !!isOwner,
      avatarImg: avImg,
      avatarInitials: avInit,
      nameLabel: nameSpan,
      ownerBadge
    };
    state.peers.set(peerId, entry);
    App.utils.setAvatarElements(entry.name, entry.avatar, entry.uid, avImg, avInit);
    ensureThumbClick(card, peerId);
    return card;
  }


  function removeRemoteTile(peerId) {
    const entry = state.peers.get(peerId);
    if (!entry) return;
    if (state.stagePeerId === peerId) applyStage('local');
    if (entry.video && entry.video.srcObject) {
      try { entry.video.srcObject.getTracks().forEach(t => t.stop()); } catch(_){}
      entry.video.srcObject = null;
    }
    if (entry.card && entry.card.parentNode) entry.card.parentNode.removeChild(entry.card);
    state.peers.delete(peerId);
  }


  /* Media init */

  async function initMedia() {
    if (state.localStream) return;
    state.localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    refs.localVideo.srcObject = state.localStream;
    refs.stageVideo.srcObject = state.localStream;
    window.LOCAL_STREAM = state.localStream;
  }


  function updateToggleButtons() {
    refs.toggleAudioBtn.textContent = state.audioEnabled ? 'Mute mic' : 'Unmute mic';
    refs.toggleVideoBtn.textContent = state.videoEnabled ? 'Stop video' : 'Start video';
    refs.shareScreenBtn.textContent = state.isScreenSharing ? 'Stop sharing' : 'Share screen';
    if (refs.screenIndicator) {
      refs.screenIndicator.style.display = state.isScreenSharing ? 'inline-block' : 'none';
    }
  }


  function applyTrackStates() {
    if (!state.localStream) return;
    state.localStream.getAudioTracks().forEach(t => (t.enabled = state.audioEnabled));
    state.localStream.getVideoTracks().forEach(t => (t.enabled = state.videoEnabled));
  }


  /* PeerConnection ensure */

  function ensurePeerConnection(peerId) {
    let entry = state.peers.get(peerId);
    if (!entry) { entry = {}; state.peers.set(peerId, entry); }
    if (entry.pc) return entry.pc;

    const pc = new RTCPeerConnection({ iceServers: window.ICE_SERVERS || [{ urls: 'stun:stun.l.google.com:19302' }] });

    pc.onicecandidate = (e) => {
      if (e.candidate && state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'ice', to: peerId, data: e.candidate }));
      }
    };

    pc.ontrack = (e) => {
      createRemoteTile(peerId, entry.name || 'Remote', entry.avatar || '', entry.isOwner, entry.uid);
      const v = state.peers.get(peerId)?.video;
      if (v) {
        v.srcObject = e.streams[0];
        if (state.stagePeerId === peerId) {
          markStageSwitch();
          refs.stageVideo.srcObject = v.srcObject;
        }
      }
    };

    if (state.localStream) {
      for (const track of state.localStream.getTracks()) pc.addTrack(track, state.localStream);
    }
    entry.pc = pc;
    state.peers.set(peerId, entry);
    return pc;
  }


  async function makeOfferTo(peerId) {
    const pc = ensurePeerConnection(peerId);
    const offer = await pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: true });
    await pc.setLocalDescription(offer);
    state.ws.send(JSON.stringify({ type: 'offer', to: peerId, data: offer }));
  }


  async function handleOffer(from, offer) {
    const pc = ensurePeerConnection(from);
    await pc.setRemoteDescription(new RTCSessionDescription(offer));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    state.ws.send(JSON.stringify({ type: 'answer', to: from, data: answer }));
  }


  async function handleAnswer(from, answer) {
    const entry = state.peers.get(from);
    if (!entry || !entry.pc) return;
    await entry.pc.setRemoteDescription(new RTCSessionDescription(answer));
  }


  async function handleIce(from, cand) {
    const entry = state.peers.get(from);
    if (!entry || !entry.pc) return;
    try { await entry.pc.addIceCandidate(new RTCIceCandidate(cand)); }
    catch(e){ console.warn('ICE add failed', e); }
  }


  /* Avatar cache for local (optional) */

  async function cacheLocalAvatarIfNeeded() {
    try {
      if (!state.myUid || !state.myAvatar || !/^https?:\/\//i.test(state.myAvatar)) return;
      const resp = await fetch('/avatar/cache', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ uid: state.myUid, url: state.myAvatar })
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && data.avatar) {
        state.myAvatar = data.avatar;
        const localEntry = state.peers.get('local');
        if (localEntry) {
          localEntry.avatar = state.myAvatar;
          App.utils.setAvatarElements(state.meName, state.myAvatar, state.myUid, localEntry.avatarImg, localEntry.avatarInitials);
          if (state.stagePeerId === 'local') App.utils.setAvatarElements(state.meName, state.myAvatar, state.myUid, refs.stageAvatarImg, refs.stageAvatarInitials);
        }
      }
    } catch(e) {
      console.warn('avatar cache error', e);
    }
  }


  function showRecordIndicator(active, mode) {
    if (!refs.recordIndicator) return;
    if (!active) {
      refs.recordIndicator.style.display = 'none';
      return;
    }
    refs.recordIndicator.style.display = 'inline-block';
    refs.recordIndicator.textContent = (mode === 'pause') ? 'REC (paused)' : 'REC';
  }


  /* Screen share */

  function getAllVideoSenders() {
    const senders = [];
    for (const [, entry] of state.peers.entries()) {
      if (!entry.pc) continue;
      const list = entry.pc.getSenders ? entry.pc.getSenders() : [];
      for (const s of list) {
        if (s && s.track && s.track.kind === 'video') senders.push({ peerId: findPeerIdByPC(entry.pc), sender: s });
      }
    }
    return senders;
  }


  function findPeerIdByPC(pc) {
    for (const [pid, entry] of state.peers.entries()) {
      if (entry.pc === pc) return pid;
    }
    return null;
  }


  async function startScreenShare() {
    if (!state.localStream) {
      await initMedia();
      applyTrackStates();
    }

    const wantForwardSysAudio = !!(refs.shareSysAudioToOthersChk && refs.shareSysAudioToOthersChk.checked);

    let displayStream = null;
    try {
      displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 25, cursor: "motion" },
        audio: wantForwardSysAudio ? true : false
      });
    } catch (e) {
      console.warn('getDisplayMedia denied or failed', e);
      return;
    }
    if (!displayStream) return;

    const vTrack = displayStream.getVideoTracks()[0];
    if (!vTrack) {
      try { displayStream.getTracks().forEach(t => t.stop()); } catch(_){}
      return;
    }

    vTrack.onended = () => {
      try { stopScreenShare(); } catch(_){}
    };

    const prevV = state.localStream.getVideoTracks()[0] || null;
    state.prevVideoTrack = prevV;

    const senders = getAllVideoSenders();
    await Promise.all(senders.map(async ({ sender }) => {
      try { await sender.replaceTrack(vTrack); } catch(e){ console.warn('replaceTrack failed', e); }
    }));

    markStageSwitch();
    refs.stageVideo.srcObject = displayStream;

    state.isScreenSharing = true;
    state.screenStream = displayStream;

    if (wantForwardSysAudio) {
      const aTrack = displayStream.getAudioTracks()[0] || null;
      if (aTrack) {
        for (const [pid, entry] of state.peers.entries()) {
          if (!entry.pc) continue;
          try {
            const sender = entry.pc.addTrack(aTrack, displayStream);
            state.screenAudioSenders.set(pid, sender);
          } catch(e) {
            console.warn('addTrack audio failed', e);
          }
        }
      }
    }

    updateToggleButtons();
  }


  async function stopScreenShare() {
    const restoreV = state.prevVideoTrack;
    const senders = getAllVideoSenders();
    if (restoreV) {
      await Promise.all(senders.map(async ({ sender }) => {
        try { await sender.replaceTrack(restoreV); } catch(e){ console.warn('restore replaceTrack failed', e); }
      }));
    }

    for (const [pid, sender] of state.screenAudioSenders.entries()) {
      try {
        const entry = state.peers.get(pid);
        if (entry && entry.pc && sender) {
          entry.pc.removeTrack(sender);
        }
      } catch(_){}
    }
    state.screenAudioSenders.clear();

    if (state.screenStream) {
      try { state.screenStream.getTracks().forEach(t => t.stop()); } catch(_){}
    }
    state.screenStream = null;
    state.isScreenSharing = false;

    if (state.stagePeerId === 'local') {
      markStageSwitch();
      refs.stageVideo.srcObject = refs.localVideo.srcObject || null;
    } else {
      const entry = state.peers.get(state.stagePeerId);
      markStageSwitch();
      refs.stageVideo.srcObject = (entry && entry.video && entry.video.srcObject) ? entry.video.srcObject : null;
    }

    updateToggleButtons();
  }


  /* Join flow */

  refs.joinBtn.onclick = async () => {
    if (state.joined || state.connecting) return;
    state.connecting = true;
    refs.joinBtn.disabled = true;

    state.roomId = (refs.roomInput.value || '').trim();
    if (!state.roomId) {
      alert('Enter room id');
      refs.joinBtn.disabled = false;
      state.connecting = false;
      return;
    }
    refs.roomLabel.textContent = state.roomId;

    try {
      await initMedia();
      applyTrackStates();
      await cacheLocalAvatarIfNeeded();

      state.ws = new WebSocket(utils.wsUrl(`/ws/${encodeURIComponent(state.roomId)}`));

      state.ws.onopen = () => {
        window.WS_INSTANCE = state.ws;
        state.joined = true;
        state.connecting = false;
        refs.joinBtn.disabled = true;
        startCallTimer();
        state.ws.send(JSON.stringify({
          type: 'hello',
          name: state.meName,
          uid: state.myUid,
          avatar: state.myAvatar,
          is_owner: state.isOwnerByLink,
          info: (window.USER_INFO || {})
        }));
      };

      state.ws.onmessage = async ev => {
        const msg = JSON.parse(ev.data);
        switch (msg.type) {
          case 'error':
            alert(msg.message || 'Server error');
            break;
          case 'owner-set':
            state.ownerUid = msg.owner_uid || '';
            for (const [, entry] of state.peers.entries()) {
              entry.isOwner = !!(state.ownerUid && entry.uid && state.ownerUid === entry.uid);
              if (entry.ownerBadge) entry.ownerBadge.style.display = entry.isOwner ? '' : 'none';
            }
            if (state.stagePeerId === 'local') {
              refs.stageOwnerBadge.style.display = (state.ownerUid === state.myUid) ? '' : 'none';
            } else {
              const se = state.peers.get(state.stagePeerId);
              refs.stageOwnerBadge.style.display = (se && se.uid && state.ownerUid === se.uid) ? '' : 'none';
            }
            break;
          case 'peers':
            {
              const list = Array.isArray(msg.peers) ? msg.peers : [];
              state.ownerUid = msg.owner_uid || state.ownerUid;
              for (const p of list) {
                if (!p || !p.id) continue;
                createRemoteTile(
                  p.id,
                  p.name || 'Remote',
                  p.avatar || '',
                  !!(state.ownerUid && p.uid && state.ownerUid === p.uid),
                  p.uid || ''
                );
                ensurePeerConnection(p.id);
                await makeOfferTo(p.id);
              }
            }
            break;
          case 'peer-joined':
            {
              const pid = msg.id;
              if (pid) {
                createRemoteTile(
                  pid,
                  msg.name || 'Remote',
                  msg.avatar || '',
                  !!(state.ownerUid && msg.uid && state.ownerUid === msg.uid),
                  msg.uid || ''
                );
                ensurePeerConnection(pid);
              }
            }
            break;
          case 'peer-info':
            {
              const pid = msg.id;
              if (pid) {
                const entry = state.peers.get(pid) || {};
                entry.name = msg.name || entry.name || 'Remote';
                entry.avatar = msg.avatar || entry.avatar || '';
                entry.uid = msg.uid || entry.uid || '';
                entry.isOwner = !!(state.ownerUid && entry.uid && state.ownerUid === entry.uid);
                state.peers.set(pid, entry);
                createRemoteTile(pid, entry.name, entry.avatar, entry.isOwner, entry.uid);
                if (state.stagePeerId === pid) {
                  markStageSwitch();
                  applyStage(pid);
                }
              }
            }
            break;
          case 'offer': await handleOffer(msg.from, msg.data); break;
          case 'answer': await handleAnswer(msg.from, msg.data); break;
          case 'ice': await handleIce(msg.from, msg.data); break;
          case 'peer-left':
          case 'bye':
            {
              const pid = msg.id;
              if (pid) {
                const entry = state.peers.get(pid);
                if (entry && entry.pc) { try { entry.pc.close(); } catch(_){ } }
                removeRemoteTile(pid);
                maybeStopTimerIfAlone();
              }
            }
            break;
          case 'record-start':
            showRecordIndicator(true, 'rec');
            break;
          case 'record-pause':
            showRecordIndicator(true, 'pause');
            break;
          case 'record-resume':
            showRecordIndicator(true, 'rec');
            break;
          case 'record-stop':
            showRecordIndicator(false);
            break;
          default:
            console.debug('WS message:', msg);
        }
      };

      state.ws.onclose = () => {
        state.ws = null;
        window.WS_INSTANCE = null;
        refs.joinBtn.disabled = false;
        state.connecting = false;
        stopCallTimer(false);
        if (state.isScreenSharing) {
          try { stopScreenShare(); } catch(_){}
        }
      };

    } catch (e) {
      console.error(e);
      alert('Failed to join: ' + e.message);
      refs.joinBtn.disabled = false;
      state.connecting = false;
    }
  };


  /* Hangup with recording auto-stop and screen-share auto-stop */

  function hangup() {
    if (state.isOwnerByLink && window.STOP_ACTIVE_RECORDING) {
      try { window.STOP_ACTIVE_RECORDING(); } catch(e){ console.warn('Stop recording on hangup failed', e); }
    }
    if (state.isScreenSharing) {
      try { stopScreenShare(); } catch(_){}
    }
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      try { state.ws.send(JSON.stringify({ type: 'bye' })); } catch(_){}
      state.ws.close();
    }
    for (const [pid, entry] of state.peers.entries()) {
      if (pid !== 'local') {
        try { entry.pc && entry.pc.close(); } catch(_){}
        removeRemoteTile(pid);
      } else {
        try { entry.pc && entry.pc.close(); } catch(_){}
      }
    }
    if (state.localStream) {
      state.localStream.getTracks().forEach(t => t.stop());
      state.localStream = null;
      refs.localVideo.srcObject = null;
      refs.stageVideo.srcObject = null;
    }
    refs.stageOwnerBadge.style.display = 'none';
    refs.stageNameEl.textContent = state.meName;
    state.stagePeerId = 'local';
    state.userManuallyChoseStage = false;
    state.joined = false;
    state.connecting = false;
    state.audioEnabled = true;
    state.videoEnabled = true;
    updateToggleButtons();
    refs.joinBtn.disabled = false;
    showRecordIndicator(false);
    stopCallTimer(false);
  }

  refs.hangupBtn.onclick = hangup;


  refs.copyLinkBtn.onclick = async () => {
    const id = refs.roomInput.value.trim() || state.roomId || '';
    if (!id) { alert('No room id'); return; }
    const link = utils.getLinkForRoom(id);
    try {
      await navigator.clipboard.writeText(link);
      alert('Copied: ' + link);
    } catch {
      prompt('Copy link:', link);
    }
  };


  refs.testBtn.onclick = async () => {
    try {
      await initMedia();
      applyTrackStates();
      refs.stageVideo.srcObject = refs.localVideo.srcObject;
    } catch (e) {
      alert('Failed to init media: ' + e.message);
    }
  };


  refs.toggleAudioBtn.onclick = () => {
    state.audioEnabled = !state.audioEnabled;
    applyTrackStates();
    updateToggleButtons();
  };


  refs.toggleVideoBtn.onclick = () => {
    state.videoEnabled = !state.videoEnabled;
    applyTrackStates();
    updateToggleButtons();
  };


  refs.shareScreenBtn.onclick = async () => {
    if (!state.isScreenSharing) {
      await startScreenShare();
    } else {
      await stopScreenShare();
    }
  };


  if (state.roomId && refs.roomInput) refs.roomInput.value = state.roomId;
  if (refs.roomLabel) refs.roomLabel.textContent = state.roomId || '(none)';
  refs.callTimer = document.getElementById('callTimer');

  updateToggleButtons();
  createLocalTile();
  applyStage('local');

  App.media = { initMedia, applyTrackStates, updateToggleButtons };
  App.peersApi = { createRemoteTile, ensurePeerConnection, makeOfferTo };
})();
