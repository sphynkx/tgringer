(() => {
  const qs = new URLSearchParams(location.search);
  const roomParam = qs.get('room') || '';
  const nameParam = qs.get('n') || '';
  const uidParam = qs.get('uid') || '';

  const roomInput = document.getElementById('roomInput');
  const roomLabel = document.getElementById('roomLabel');
  const joinBtn = document.getElementById('joinBtn');
  const hangupBtn = document.getElementById('hangupBtn');
  const copyLinkBtn = document.getElementById('copyLinkBtn');
  const testBtn = document.getElementById('testBtn');
  const toggleAudioBtn = document.getElementById('toggleAudioBtn');
  const toggleVideoBtn = document.getElementById('toggleVideoBtn');

  const localVideo = document.getElementById('localVideo');
  const localNameLabel = document.getElementById('localNameLabel');
  const localAvatar = document.getElementById('localAvatar');
  const localOwnerBadge = document.getElementById('localOwnerBadge');

  const remoteGrid = document.getElementById('remoteGrid');

  let ws = null;
  let localStream = null;
  let roomId = roomParam || '';
  let joined = false;
  let connecting = false;

  let audioEnabled = true;
  let videoEnabled = true;

  const peers = new Map(); // peerId -> { pc, card, video, nameLabel, avatarImg, name, uid, avatar }

  const meInfo = window.USER_INFO || {};
  const meName = (() => {
    const full = [meInfo.first_name || '', meInfo.last_name || ''].join(' ').trim();
    if (full) return full;
    if (meInfo.username) return '@' + meInfo.username;
    if (nameParam) return decodeURIComponent(nameParam);
    return 'Me';
  })();
  const myUid = (meInfo.user_id ? String(meInfo.user_id) : '') || uidParam || '';
  const myAvatar = meInfo.avatar_url || '';

  console.debug('[APP] USER_INFO:', meInfo);
  console.debug('[APP] meName:', meName, 'myUid:', myUid, 'myAvatar:', myAvatar);

  localNameLabel.textContent = meName;
  if (myAvatar) {
    localAvatar.src = myAvatar;
    localAvatar.style.display = '';
  } else {
    localAvatar.style.display = 'none';
  }

  roomInput.value = roomId;
  roomLabel.textContent = roomId || '(none)';

  function wsUrl(path) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}${path}`;
  }

  function getLinkForRoom(id) {
    const base = `${location.origin}${location.pathname}`;
    return `${base}?room=${encodeURIComponent(id)}`;
  }

  function createRemoteTile(id, name, avatar, isOwner) {
    if (peers.has(id) && peers.get(id).card) {
      // Update labels if needed
      const entry = peers.get(id);
      if (name && entry.nameLabel) entry.nameLabel.textContent = name;
      if (avatar && entry.avatarImg) {
        entry.avatarImg.src = avatar;
        entry.avatarImg.style.display = '';
      }
      if (entry.ownerBadge) {
        entry.ownerBadge.style.display = isOwner ? '' : 'none';
      }
      entry.name = name || entry.name || 'Remote';
      entry.avatar = avatar || entry.avatar || '';
      return entry.card;
    }

    const card = document.createElement('div');
    card.className = 'card';
    card.dataset.peerId = id;

    const titleBox = document.createElement('div');
    titleBox.className = 'title';

    const avatarImg = document.createElement('img');
    avatarImg.className = 'avatar';
    if (avatar) {
      avatarImg.src = avatar;
      avatarImg.style.display = '';
    } else {
      avatarImg.style.display = 'none';
    }

    const title = document.createElement('h4');
    title.style.margin = '0';

    const nameLabel = document.createElement('span');
    nameLabel.textContent = name || 'Remote';

    const ownerBadge = document.createElement('span');
    ownerBadge.className = 'owner';
    ownerBadge.textContent = '(owner)';
    ownerBadge.style.display = isOwner ? '' : 'none';

    title.appendChild(nameLabel);
    title.appendChild(document.createTextNode(' '));
    title.appendChild(ownerBadge);

    titleBox.appendChild(avatarImg);
    titleBox.appendChild(title);

    const video = document.createElement('video');
    video.autoplay = true;
    video.playsInline = true;

    card.appendChild(titleBox);
    card.appendChild(video);
    remoteGrid.appendChild(card);

    if (!peers.has(id)) peers.set(id, {});
    const entry = peers.get(id);
    entry.card = card;
    entry.video = video;
    entry.nameLabel = nameLabel;
    entry.avatarImg = avatarImg;
    entry.ownerBadge = ownerBadge;
    entry.name = name || 'Remote';
    entry.avatar = avatar || '';
    peers.set(id, entry);

    console.debug('[APP] Tile created for', id, 'name=', name, 'owner=', isOwner);
    return card;
  }

  function removeRemoteTile(id) {
    const entry = peers.get(id);
    if (!entry) return;
    if (entry.video && entry.video.srcObject) {
      try {
        entry.video.srcObject.getTracks().forEach(t => t.stop());
      } catch {}
      entry.video.srcObject = null;
    }
    if (entry.card && entry.card.parentNode) {
      entry.card.parentNode.removeChild(entry.card);
    }
    peers.delete(id);
    console.debug('[APP] Tile removed for', id);
  }

  async function initMedia() {
    if (localStream) return;
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    localVideo.srcObject = localStream;
    console.debug('[APP] Got local media');
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

  function ensurePeerConnection(targetId) {
    let entry = peers.get(targetId);
    if (!entry) {
      entry = {};
      peers.set(targetId, entry);
    }
    if (entry.pc) return entry.pc;

    const pc = new RTCPeerConnection({ iceServers: window.ICE_SERVERS || [{ urls: 'stun:stun.l.google.com:19302' }] });

    pc.onicecandidate = (e) => {
      if (e.candidate && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ice', to: targetId, data: e.candidate }));
      }
    };

    pc.ontrack = (e) => {
      createRemoteTile(targetId, entry.name || 'Remote', entry.avatar || '', !!entry.isOwner);
      const videoEl = peers.get(targetId).video;
      videoEl.srcObject = e.streams[0];
      console.debug('[APP] Remote track for', targetId);
    };

    if (localStream) {
      for (const track of localStream.getTracks()) {
        pc.addTrack(track, localStream);
      }
    }
    entry.pc = pc;
    peers.set(targetId, entry);
    return pc;
  }

  async function makeOfferTo(targetId) {
    const pc = ensurePeerConnection(targetId);
    const offer = await pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: true });
    await pc.setLocalDescription(offer);
    ws.send(JSON.stringify({ type: 'offer', to: targetId, data: offer }));
    console.debug('[APP] Sent offer to', targetId);
  }

  async function handleOffer(fromId, offer) {
    const pc = ensurePeerConnection(fromId);
    await pc.setRemoteDescription(new RTCSessionDescription(offer));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    ws.send(JSON.stringify({ type: 'answer', to: fromId, data: answer }));
    console.debug('[APP] Sent answer to', fromId);
  }

  async function handleAnswer(fromId, answer) {
    const entry = peers.get(fromId);
    if (!entry || !entry.pc) return;
    await entry.pc.setRemoteDescription(new RTCSessionDescription(answer));
    console.debug('[APP] Applied answer from', fromId);
  }

  async function handleIce(fromId, cand) {
    const entry = peers.get(fromId);
    if (!entry || !entry.pc) return;
    try {
      await entry.pc.addIceCandidate(new RTCIceCandidate(cand));
      console.debug('[APP] ICE added from', fromId);
    } catch (e) {
      console.warn('[APP] ICE add failed from', fromId, e);
    }
  }

  joinBtn.onclick = async () => {
    if (joined || connecting) return;
    connecting = TrueSafe();
    joinBtn.disabled = true;

    roomId = roomInput.value.trim();
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

      ws = new WebSocket(wsUrl(`/ws/${encodeURIComponent(roomId)}`));

      ws.onopen = () => {
        joined = true;
        connecting = false;
        joinBtn.disabled = true;
        console.debug('[APP] WebSocket open, sending hello with name/uid:', meName, myUid);
        ws.send(JSON.stringify({ type: 'hello', name: meName, uid: myUid, avatar: myAvatar, info: (window.USER_INFO || {}) }));
      };

      ws.onmessage = async (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'error') {
          console.warn('[APP] server error:', msg);
          alert(msg.message || 'Server error');
          return;
        }
        if (msg.type === 'peers') {
          const list = Array.isArray(msg.peers) ? msg.peers : [];
          const ownerUid = msg.owner_uid || '';
          // Mark local owner if matches
          if (myUid && ownerUid && myUid === ownerUid) {
            localOwnerBadge.style.display = '';
          } else {
            localOwnerBadge.style.display = 'none';
          }
          for (const p of list) {
            if (p && p.id) {
              const isOwner = !!(ownerUid && p.uid && ownerUid === p.uid);
              createRemoteTile(p.id, p.name || 'Remote', p.avatar || '', isOwner);
              const entry = peers.get(p.id) || {};
              entry.isOwner = isOwner;
              entry.uid = p.uid || '';
              entry.name = p.name || 'Remote';
              entry.avatar = p.avatar || '';
              peers.set(p.id, entry);
              ensurePeerConnection(p.id);
              await makeOfferTo(p.id);
            }
          }
          console.debug('[APP] peers list:', list);
        } else if (msg.type === 'peer-joined') {
          const pid = msg.id;
          const pname = msg.name || 'Remote';
          const pavatar = msg.avatar || '';
          const puid = msg.uid || '';
          const isOwner = false; // owner-ness will be received via peer-info if needed
          if (pid) {
            createRemoteTile(pid, pname, pavatar, isOwner);
            const entry = peers.get(pid) || {};
            entry.uid = puid;
            entry.name = pname;
            entry.avatar = pavatar;
            peers.set(pid, entry);
            ensurePeerConnection(pid);
            console.debug('[APP] peer-joined:', pid, pname);
          }
        } else if (msg.type === 'peer-info') {
          const pid = msg.id;
          const pname = msg.name || 'Remote';
          const pavatar = msg.avatar || '';
          const puid = msg.uid || '';
          if (pid) {
            const entry = peers.get(pid) || {};
            entry.name = pname;
            entry.avatar = pavatar || entry.avatar;
            entry.uid = puid || entry.uid;
            peers.set(pid, entry);
            createRemoteTile(pid, pname, entry.avatar || '', entry.isOwner || false);
            console.debug('[APP] peer-info:', pid, pname);
          }
        } else if (msg.type === 'offer') {
          await handleOffer(msg.from, msg.data);
        } else if (msg.type === 'answer') {
          await handleAnswer(msg.from, msg.data);
        } else if (msg.type === 'ice') {
          await handleIce(msg.from, msg.data);
        } else if (msg.type === 'peer-left') {
          const pid = msg.id;
          if (pid) {
            const entry = peers.get(pid);
            if (entry && entry.pc) {
              try { entry.pc.close(); } catch {}
            }
            removeRemoteTile(pid);
          }
          console.debug('[APP] peer-left:', pid);
        } else if (msg.type === 'bye') {
          const pid = msg.id;
          if (pid) {
            const entry = peers.get(pid);
            if (entry && entry.pc) {
              try { entry.pc.close(); } catch {}
            }
            removeRemoteTile(pid);
          }
          console.debug('[APP] bye from:', pid);
        } else {
          console.debug('[APP] ws msg:', msg);
        }
      };

      ws.onclose = () => {
        console.debug('[APP] WebSocket closed');
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

  function TrueSafe() { return true; }

  function hangup() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'bye' }));
      ws.close();
    }
    for (const [pid, entry] of peers.entries()) {
      try { entry.pc && entry.pc.close(); } catch {}
      removeRemoteTile(pid);
    }
    peers.clear();

    if (localStream) {
      localStream.getTracks().forEach(t => t.stop());
      localStream = null;
      localVideo.srcObject = null;
    }
    joined = false;
    connecting = false;
    joinBtn.disabled = false;
    audioEnabled = true;
    videoEnabled = true;
    localOwnerBadge.style.display = 'none';
    updateToggleButtons();
    console.debug('[APP] Hangup done');
  }

  hangupBtn.onclick = () => hangup();

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
    } catch (e) {
      console.error(e);
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

  if (roomParam) {
    roomInput.value = roomParam;
  }

  updateToggleButtons();
})();