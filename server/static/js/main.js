(() => {
  const qs = new URLSearchParams(location.search);
  const roomParam = qs.get('room') || '';
  const roomInput = document.getElementById('roomInput');
  const roomLabel = document.getElementById('roomLabel');
  const joinBtn = document.getElementById('joinBtn');
  const hangupBtn = document.getElementById('hangupBtn');
  const copyLinkBtn = document.getElementById('copyLinkBtn');
  const testBtn = document.getElementById('testBtn');
  const toggleAudioBtn = document.getElementById('toggleAudioBtn');
  const toggleVideoBtn = document.getElementById('toggleVideoBtn');
  const localVideo = document.getElementById('localVideo');
  const remoteVideo = document.getElementById('remoteVideo');
  const localNameLabel = document.getElementById('localNameLabel');
  const remoteNameLabel = document.getElementById('remoteNameLabel');

  let pc = null;
  let ws = null;
  let localStream = null;
  let peerId = null;
  let isOfferer = false;
  let roomId = roomParam || '';
  let joined = false;

  let audioEnabled = true;
  let videoEnabled = true;

  const ui = window.UI_STRINGS || {};
  const meName = (() => {
    const u = window.USER_INFO || {};
    const full = [u.first_name || '', u.last_name || ''].join(' ').trim();
    if (full) return full;
    if (u.username) return '@' + u.username;
    return 'Me';
  })();
  localNameLabel.textContent = meName;
  remoteNameLabel.textContent = 'Remote';

  roomInput.value = roomId;
  roomLabel.textContent = roomId || '(none)';

  function wsUrl(path) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}${path}`;
  }

  function getLinkForRoom(id) {
    const base = `${location.origin}${location.pathname}`;
    const url = `${base}?room=${encodeURIComponent(id)}`;
    return url;
  }

  async function initMedia() {
    if (localStream) return;
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    localVideo.srcObject = localStream;
    console.debug('Got local media');
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

  function createPeer() {
    pc = new RTCPeerConnection({ iceServers: window.ICE_SERVERS || [{ urls: 'stun:stun.l.google.com:19302' }] });

    pc.onicecandidate = (e) => {
      if (e.candidate && ws) {
        console.debug('Send ICE:', e.candidate);
        ws.send(JSON.stringify({ type: 'ice', data: e.candidate }));
      }
    };

    pc.ontrack = (e) => {
      console.debug('Got remote track:', e.streams);
      remoteVideo.srcObject = e.streams[0];
    };

    if (localStream) {
      for (const track of localStream.getTracks()) {
        pc.addTrack(track, localStream);
      }
    }
  }

  async function makeOffer() {
    console.debug('Creating offer...');
    const offer = await pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: true });
    await pc.setLocalDescription(offer);
    console.debug('Local description set (offer)');
    ws.send(JSON.stringify({ type: 'offer', data: offer }));
  }

  async function makeAnswer(offer) {
    console.debug('Received offer:', offer);
    await pc.setRemoteDescription(new RTCSessionDescription(offer));
    console.debug('Remote description set (offer)');
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    console.debug('Local description set (answer)');
    ws.send(JSON.stringify({ type: 'answer', data: answer }));
  }

  async function handleAnswer(answer) {
    console.debug('Received answer:', answer);
    await pc.setRemoteDescription(new RTCSessionDescription(answer));
    console.debug('Remote description set (answer)');
  }

  joinBtn.onclick = async () => {
    if (joined) return;
    roomId = roomInput.value.trim();
    if (!roomId) {
      alert('Enter room id');
      return;
    }
    roomLabel.textContent = roomId;

    try {
      await initMedia();
      applyTrackStates();
      createPeer();

      ws = new WebSocket(wsUrl(`/ws/${encodeURIComponent(roomId)}`));

      ws.onopen = () => {
        joined = true;
        console.debug('WebSocket open');
        // Introduce ourselves (name) for remote label
        ws.send(JSON.stringify({ type: 'hello', name: meName }));
      };

      ws.onmessage = async (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'ready') {
          if (msg.id) peerId = msg.id;
          isOfferer = (peerId === msg.offerer);
          console.debug('Ready. peerId:', peerId, 'isOfferer:', isOfferer, 'msg:', msg);
          if (isOfferer) {
            await makeOffer();
          }
        } else if (msg.type === 'peer-info') {
          // Remote peer name arrived
          if (msg.name) {
            remoteNameLabel.textContent = msg.name;
          }
        } else if (msg.type === 'offer') {
          if (!pc.currentRemoteDescription) {
            await makeAnswer(msg.data);
          } else {
            console.warn('Offer received, but remote description already set.');
          }
        } else if (msg.type === 'answer') {
          if (pc.signalingState === 'have-local-offer' && !pc.currentRemoteDescription) {
            await handleAnswer(msg.data);
          } else if (pc.signalingState === 'stable') {
            console.warn('Answer received, but signaling state is stable.');
          } else {
            await handleAnswer(msg.data);
          }
        } else if (msg.type === 'ice') {
          try {
            await pc.addIceCandidate(new RTCIceCandidate(msg.data));
            console.debug('ICE candidate added:', msg.data);
          } catch (e) {
            console.warn('addIceCandidate failed', e);
          }
        } else if (msg.type === 'peer-left') {
          console.debug('Remote left');
          if (remoteVideo.srcObject) {
            remoteVideo.srcObject.getTracks().forEach(t => t.stop());
            remoteVideo.srcObject = null;
          }
          remoteNameLabel.textContent = 'Remote';
        } else if (msg.type === 'bye') {
          console.debug('Received bye');
          hangup();
        }
      };

      ws.onclose = () => {
        console.debug('WebSocket closed');
        ws = null;
      };

    } catch (e) {
      console.error(e);
      alert('Failed to join: ' + e.message);
    }
  };

  function hangup() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'bye' }));
      ws.close();
    }
    if (pc) {
      pc.getSenders().forEach(s => {
        try { s.track && s.track.stop(); } catch {}
      });
      pc.close();
      pc = null;
    }
    if (localStream) {
      localStream.getTracks().forEach(t => t.stop());
      localStream = null;
      localVideo.srcObject = null;
    }
    if (remoteVideo.srcObject) {
      remoteVideo.srcObject.getTracks().forEach(t => t.stop());
      remoteVideo.srcObject = null;
    }
    joined = false;
    audioEnabled = true;
    videoEnabled = true;
    updateToggleButtons();
    remoteNameLabel.textContent = 'Remote';
    console.debug('Hangup done');
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