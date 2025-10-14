(() => {
  // Telegram WebApp expand
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  try {
    if (tg) {
      tg.ready();
      tg.expand();
      setTimeout(() => { try { tg.expand(); } catch(_){} }, 400);
      setTimeout(() => { try { tg.expand(); } catch(_){} }, 1200);
    }
  } catch(_){}

  // Query params
  const qs = new URLSearchParams(location.search);
  const roomParam = qs.get('room') || '';
  const nameParam = qs.get('n') || '';
  const uidParam = qs.get('uid') || '';
  const avatarParam = qs.get('a') || '';
  const ownerParam = qs.get('owner') || '';

  // UI elements
  const roomInput = document.getElementById('roomInput');
  const roomLabel = document.getElementById('roomLabel');
  const joinBtn = document.getElementById('joinBtn');
  const hangupBtn = document.getElementById('hangupBtn');
  const copyLinkBtn = document.getElementById('copyLinkBtn');
  const testBtn = document.getElementById('testBtn');
  const toggleAudioBtn = document.getElementById('toggleAudioBtn');
  const toggleVideoBtn = document.getElementById('toggleVideoBtn');

  // Stage
  const stageVideoArea = document.getElementById('stageVideoArea');
  const stageNameEl = document.getElementById('stageName');
  const stageOwnerBadge = document.getElementById('stageOwnerBadge');
  const stageAvatarImg = document.getElementById('stageAvatarImg');
  const stageAvatarInitials = document.getElementById('stageAvatarInitials');
  const stageFullscreenBtn = document.getElementById('stageFullscreenBtn');
  const stageCollapseBtn = document.getElementById('stageCollapseBtn');

  // Thumbnails container
  const thumbsStrip = document.getElementById('thumbsStrip');

  // Local media video
  const localVideo = document.createElement('video');
  localVideo.autoplay = true;
  localVideo.playsInline = true;
  localVideo.muted = true;

  // Dedicated stage video element
  const stageVideo = document.createElement('video');
  stageVideo.autoplay = true;
  stageVideo.playsInline = true;
  stageVideo.controls = false;
  stageVideo.style.width = '100%';
  stageVideo.style.height = '100%';
  stageVideo.style.objectFit = 'contain';
  stageVideoArea.appendChild(stageVideo);

  let ws = null;
  let localStream = null;
  let roomId = roomParam || '';
  let joined = false;
  let connecting = false;

  let audioEnabled = true;
  let videoEnabled = true;

  const peers = new Map();

  // User info
  const initUser = tg && tg.initDataUnsafe ? (tg.initDataUnsafe.user || null) : null;
  const initUid = initUser && initUser.id ? String(initUser.id) : '';
  const initPhoto = initUser && initUser.photo_url ? initUser.photo_url : '';

  const meInfo = window.USER_INFO || {};
  const meName = (() => {
    const full = [meInfo.first_name || '', meInfo.last_name || ''].join(' ').trim();
    if (full) return full;
    if (meInfo.username) return '@' + meInfo.username;
    if (nameParam) return decodeURIComponent(nameParam);
    return 'Me';
  })();
  const myUid = (meInfo.user_id ? String(meInfo.user_id) : '') || uidParam || initUid || '';
  let myAvatar = (meInfo.avatar_url || '') || (avatarParam ? decodeURIComponent(avatarParam) : '') || initPhoto || '';
  const isOwnerByLink = ownerParam === '1';
  let ownerUid = '';

  // Stage state
  let stagePeerId = 'local';
  let userManuallyChoseStage = false;

  function getInitials(name) {
    const s = (name || '').trim();
    if (!s) return 'NA';
    const parts = s.split(/\s+/).filter(Boolean);
    if (parts.length === 1) {
      const p = parts[0].replace(/^@/, '');
      return p.slice(0, 2).toUpperCase();
    }
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  function colorFromString(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
    const hue = h % 360;
    return `hsl(${hue}, 65%, 65%)`;
  }
  function setAvatarElements(name, avatarUrl, uid, imgEl, initialsEl) {
    const initials = getInitials(name || 'NA');
    const colorSeed = uid || name || 'seed';
    const bg = colorFromString(String(colorSeed));
    if (avatarUrl) {
      if (imgEl) { imgEl.src = avatarUrl; imgEl.style.display = 'block'; }
      if (initialsEl) initialsEl.style.display = 'none';
    } else {
      if (imgEl) { imgEl.removeAttribute('src'); imgEl.style.display = 'none'; }
      if (initialsEl) {
        initialsEl.textContent = initials;
        initialsEl.style.background = bg;
        initialsEl.style.display = 'flex';
      }
    }
  }

  function wsUrl(path) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}${path}`;
  }
  function getLinkForRoom(id) {
    const base = `${location.origin}${location.pathname}`;
    return `${base}?room=${encodeURIComponent(id)}`;
  }

  function applyStage(peerId) {
    stagePeerId = peerId;
    for (const [, entry] of peers) {
      if (entry.card) entry.card.classList.remove('active-stage');
    }
    const entry = peers.get(peerId);
    if (entry && entry.card) entry.card.classList.add('active-stage');

    if (peerId === 'local') {
      stageNameEl.textContent = meName;
      stageOwnerBadge.style.display = ownerUid && myUid && ownerUid === myUid ? '' : 'none';
      setAvatarElements(meName, myAvatar, myUid, stageAvatarImg, stageAvatarInitials);
      if (localVideo.srcObject) stageVideo.srcObject = localVideo.srcObject;
    } else if (entry) {
      stageNameEl.textContent = entry.name;
      stageOwnerBadge.style.display = ownerUid && entry.uid && ownerUid === entry.uid ? '' : 'none';
      setAvatarElements(entry.name, entry.avatar, entry.uid, stageAvatarImg, stageAvatarInitials);
      if (entry.video && entry.video.srcObject) {
        stageVideo.srcObject = entry.video.srcObject;
      }
    }
  }

  function collapseStageToLocal() {
    userManuallyChoseStage = true;
    applyStage('local');
  }

  stageCollapseBtn.onclick = () => collapseStageToLocal();

  // Fullscreen helpers
  function isFullscreen() {
    return !!document.fullscreenElement;
  }
  function enterFullscreen() {
    const el = stageVideoArea;
    if (el.requestFullscreen) el.requestFullscreen();
  }
  function exitFullscreen() {
    if (document.exitFullscreen) document.exitFullscreen();
  }
  function toggleFullscreen() {
    if (isFullscreen()) exitFullscreen(); else enterFullscreen();
  }
  stageFullscreenBtn.onclick = () => toggleFullscreen();

  document.addEventListener('fullscreenchange', () => {
    stageFullscreenBtn.textContent = isFullscreen() ? 'Exit FS' : 'Fullscreen';
  });

  // Click on stage: if fullscreen -> exit; else if remote -> collapse to local
  stageVideoArea.onclick = (e) => {
    if (isFullscreen()) {
      exitFullscreen();
      return; // do not also collapse in the same click
    }
    if (stagePeerId !== 'local') collapseStageToLocal();
  };

  function ensureThumbClick(card, peerId) {
    if (!card) return;
    card.onclick = () => {
      userManuallyChoseStage = true;
      if (stagePeerId === peerId) {
        if (peerId !== 'local') applyStage('local');
      } else {
        applyStage(peerId);
      }
    };
  }

  function createOrUpdateLocalTile() {
    if (peers.has('local')) return;
    const card = document.createElement('div');
    card.className = 'thumb';
    card.dataset.peerId = 'local';

    const title = document.createElement('h4');
    const avWrap = document.createElement('div'); avWrap.className = 'avatar-wrap';
    const avImg = document.createElement('img'); avImg.className = 'avatar-img';
    const avInit = document.createElement('div'); avInit.className = 'avatar-initials';
    avWrap.appendChild(avImg); avWrap.appendChild(avInit);

    const nameSpan = document.createElement('span'); nameSpan.textContent = meName;
    const ownerBadge = document.createElement('span');
    ownerBadge.className = 'owner-badge';
    ownerBadge.textContent = '(owner)';
    ownerBadge.style.display = 'none';

    title.appendChild(avWrap);
    title.appendChild(nameSpan);
    title.appendChild(ownerBadge);

    const videoWrap = document.createElement('div');
    localVideo.style.width = '100%';
    localVideo.style.height = '110px';
    localVideo.style.objectFit = 'cover';
    localVideo.style.background = '#000';
    localVideo.style.borderRadius = '8px';
    videoWrap.appendChild(localVideo);

    card.appendChild(title);
    card.appendChild(videoWrap);
    thumbsStrip.appendChild(card);

    const entry = {
      card,
      video: localVideo,
      name: meName,
      uid: myUid,
      avatar: myAvatar,
      isOwner: false,
      avatarImg: avImg,
      avatarInitials: avInit,
      nameLabel: nameSpan,
      ownerBadge
    };
    peers.set('local', entry);
    setAvatarElements(meName, myAvatar, myUid, avImg, avInit);
    ensureThumbClick(card, 'local');
  }

  function createRemoteTile(peerId, name, avatar, isOwner, uid) {
    let entry = peers.get(peerId);
    if (entry && entry.card) {
      entry.name = name || entry.name;
      entry.avatar = avatar || entry.avatar;
      entry.uid = uid || entry.uid;
      entry.isOwner = !!isOwner;
      if (entry.nameLabel) entry.nameLabel.textContent = entry.name;
      if (entry.ownerBadge) entry.ownerBadge.style.display = entry.isOwner ? '' : 'none';
      setAvatarElements(entry.name, entry.avatar, entry.uid, entry.avatarImg, entry.avatarInitials);
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
    thumbsStrip.appendChild(card);

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
    peers.set(peerId, entry);
    setAvatarElements(entry.name, entry.avatar, entry.uid, avImg, avInit);
    ensureThumbClick(card, peerId);
    return card;
  }

  function removeRemoteTile(peerId) {
    const entry = peers.get(peerId);
    if (!entry) return;
    if (stagePeerId === peerId) applyStage('local');
    if (entry.video && entry.video.srcObject) {
      try { entry.video.srcObject.getTracks().forEach(t => t.stop()); } catch(_){}
      entry.video.srcObject = null;
    }
    if (entry.card && entry.card.parentNode) entry.card.parentNode.removeChild(entry.card);
    peers.delete(peerId);
  }

  async function initMedia() {
    if (localStream) return;
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    localVideo.srcObject = localStream;
    stageVideo.srcObject = localStream; // show self immediately
  }

  function updateToggleButtons() {
    toggleAudioBtn.textContent = audioEnabled ? 'Mute mic' : 'Unmute mic';
    toggleVideoBtn.textContent = videoEnabled ? 'Stop video' : 'Start video';
  }
  function applyTrackStates() {
    if (!localStream) return;
    localStream.getAudioTracks().forEach(t => (t.enabled = audioEnabled));
    localStream.getVideoTracks().forEach(t => (t.enabled = videoEnabled));
  }

  function ensurePeerConnection(peerId) {
    let entry = peers.get(peerId);
    if (!entry) { entry = {}; peers.set(peerId, entry); }
    if (entry.pc) return entry.pc;

    const pc = new RTCPeerConnection({ iceServers: window.ICE_SERVERS || [{ urls: 'stun:stun.l.google.com:19302' }] });

    pc.onicecandidate = (e) => {
      if (e.candidate && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ice', to: peerId, data: e.candidate }));
      }
    };

    pc.ontrack = (e) => {
      createRemoteTile(peerId, entry.name || 'Remote', entry.avatar || '', entry.isOwner, entry.uid);
      const videoEl = peers.get(peerId)?.video;
      if (videoEl) {
        videoEl.srcObject = e.streams[0];
        if (stagePeerId === peerId) stageVideo.srcObject = videoEl.srcObject;
      }
    };

    if (localStream) {
      for (const track of localStream.getTracks()) pc.addTrack(track, localStream);
    }
    entry.pc = pc;
    peers.set(peerId, entry);
    return pc;
  }

  async function makeOfferTo(peerId) {
    const pc = ensurePeerConnection(peerId);
    const offer = await pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: true });
    await pc.setLocalDescription(offer);
    ws.send(JSON.stringify({ type: 'offer', to: peerId, data: offer }));
  }
  async function handleOffer(from, offer) {
    const pc = ensurePeerConnection(from);
    await pc.setRemoteDescription(new RTCSessionDescription(offer));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    ws.send(JSON.stringify({ type: 'answer', to: from, data: answer }));
  }
  async function handleAnswer(from, answer) {
    const entry = peers.get(from);
    if (!entry || !entry.pc) return;
    await entry.pc.setRemoteDescription(new RTCSessionDescription(answer));
  }
  async function handleIce(from, cand) {
    const entry = peers.get(from);
    if (!entry || !entry.pc) return;
    try { await entry.pc.addIceCandidate(new RTCIceCandidate(cand)); }
    catch(e){ console.warn('ICE add failed', e); }
  }

  async function cacheLocalAvatarIfNeeded() {
    try {
      if (!myUid || !myAvatar || !/^https?:\/\//i.test(myAvatar)) return;
      const resp = await fetch('/avatar/cache', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ uid: myUid, url: myAvatar })
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && data.avatar) {
        myAvatar = data.avatar;
        const localEntry = peers.get('local');
        if (localEntry) {
          localEntry.avatar = myAvatar;
          setAvatarElements(meName, myAvatar, myUid, localEntry.avatarImg, localEntry.avatarInitials);
          if (stagePeerId === 'local') setAvatarElements(meName, myAvatar, myUid, stageAvatarImg, stageAvatarInitials);
        }
      }
    } catch(e) {
      console.warn('avatar cache error', e);
    }
  }

  createOrUpdateLocalTile();
  applyStage('local');

  joinBtn.onclick = async () => {
    if (joined || connecting) return;
    connecting = true;
    joinBtn.disabled = true;

    roomId = (roomInput.value || '').trim();
    if (!roomId) {
      alert('Enter room id');
      joinBtn.disabled = false;
      connecting = false;
      return;
    }
    roomLabel.textContent = roomId;

    try {
      await initMedia();
      applyTrackStates();
      await cacheLocalAvatarIfNeeded();

      ws = new WebSocket(wsUrl(`/ws/${encodeURIComponent(roomId)}`));

      ws.onopen = () => {
        joined = true;
        connecting = false;
        joinBtn.disabled = true;
        ws.send(JSON.stringify({
          type: 'hello',
          name: meName,
          uid: myUid,
          avatar: myAvatar,
          is_owner: (ownerParam === '1'),
          info: (window.USER_INFO || {})
        }));
      };

      ws.onmessage = async ev => {
        const msg = JSON.parse(ev.data);
        switch (msg.type) {
          case 'error':
            alert(msg.message || 'Server error');
            break;
          case 'owner-set':
            ownerUid = msg.owner_uid || '';
            for (const [, entry] of peers.entries()) {
              entry.isOwner = !!(ownerUid && entry.uid && ownerUid === entry.uid);
              if (entry.ownerBadge) entry.ownerBadge.style.display = entry.isOwner ? '' : 'none';
            }
            if (stagePeerId === 'local') {
              stageOwnerBadge.style.display = ownerUid === myUid ? '' : 'none';
            } else {
              const se = peers.get(stagePeerId);
              stageOwnerBadge.style.display = se && se.uid && ownerUid === se.uid ? '' : 'none';
            }
            break;
          case 'peers':
            {
              const list = Array.isArray(msg.peers) ? msg.peers : [];
              ownerUid = msg.owner_uid || ownerUid;
              for (const p of list) {
                if (!p || !p.id) continue;
                createRemoteTile(
                  p.id,
                  p.name || 'Remote',
                  p.avatar || '',
                  !!(ownerUid && p.uid && ownerUid === p.uid),
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
                  !!(ownerUid && msg.uid && ownerUid === msg.uid),
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
                const entry = peers.get(pid) || {};
                entry.name = msg.name || entry.name || 'Remote';
                entry.avatar = msg.avatar || entry.avatar || '';
                entry.uid = msg.uid || entry.uid || '';
                entry.isOwner = !!(ownerUid && entry.uid && ownerUid === entry.uid);
                peers.set(pid, entry);
                createRemoteTile(pid, entry.name, entry.avatar, entry.isOwner, entry.uid);
                if (stagePeerId === pid) applyStage(pid);
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
                const entry = peers.get(pid);
                if (entry && entry.pc) { try { entry.pc.close(); } catch(_){} }
                removeRemoteTile(pid);
              }
            }
            break;
          default:
            console.debug('WS message:', msg);
        }
      };

      ws.onclose = () => {
        ws = null;
        joinBtn.disabled = false;
        connecting = false;
      };

    } catch (e) {
      console.error(e);
      alert('Failed to join: ' + e.message);
      joinBtn.disabled = false;
      connecting = false;
    }
  };

  function hangup() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: 'bye' })); } catch(_){}
      ws.close();
    }
    for (const [pid, entry] of peers.entries()) {
      if (pid !== 'local') {
        try { entry.pc && entry.pc.close(); } catch(_){}
        removeRemoteTile(pid);
      } else {
        try { entry.pc && entry.pc.close(); } catch(_){}
      }
    }
    if (localStream) {
      localStream.getTracks().forEach(t => t.stop());
      localStream = null;
      localVideo.srcObject = null;
      stageVideo.srcObject = null;
    }
    stageOwnerBadge.style.display = 'none';
    stageNameEl.textContent = meName;
    stagePeerId = 'local';
    userManuallyChoseStage = false;
    joined = false;
    connecting = false;
    audioEnabled = true;
    videoEnabled = true;
    updateToggleButtons();
    joinBtn.disabled = false;
  }
  hangupBtn.onclick = hangup;

  copyLinkBtn.onclick = async () => {
    const id = roomInput.value.trim() || roomId || '';
    if (!id) { alert('No room id'); return; }
    const link = getLinkForRoom(id);
    try {
      await navigator.clipboard.writeText(link);
      alert('Copied: ' + link);
    } catch {
      prompt('Copy link:', link);
    }
  };

  testBtn.onclick = async () => {
    try {
      await initMedia();
      applyTrackStates();
      stageVideo.srcObject = localVideo.srcObject;
    } catch (e) {
      alert('Failed to init media: ' + e.message);
    }
  };

  toggleAudioBtn.onclick = () => {
    audioEnabled = !audioEnabled;
    applyTrackStates();
    updateToggleButtons();
  };
  toggleVideoBtn.onclick = () => {
    videoEnabled = !videoEnabled;
    applyTrackStates();
    updateToggleButtons();
  };

  if (roomParam) roomInput.value = roomParam;
  roomLabel.textContent = roomId || '(none)';

  updateToggleButtons();
  createOrUpdateLocalTile();
  applyStage('local');
})();
