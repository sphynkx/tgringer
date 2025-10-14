/* ## Stage and local video management */
(function(){
  const App = window.App;
  const { refs, state, utils } = App;

  /* Create video elements */
  const localVideo = document.createElement('video');
  localVideo.autoplay = true;
  localVideo.playsInline = true;
  localVideo.muted = true;

  const stageVideo = document.createElement('video');
  stageVideo.autoplay = true;
  stageVideo.playsInline = true;
  stageVideo.controls = false;
  stageVideo.style.width = '100%';
  stageVideo.style.height = '100%';
  stageVideo.style.objectFit = 'contain';
  refs.stageVideoArea.appendChild(stageVideo);

  /* Expose refs */
  App.refs.localVideo = localVideo;
  App.refs.stageVideo = stageVideo;

  /* Avatar helpers for local tile and stage header */
  function setLocalAvatar() {
    const entry = App.state.peers.get('local');
    if (!entry) return;
    utils.setAvatarElements(state.meName, state.myAvatar, state.myUid, entry.avatarImg, entry.avatarInitials);
  }
  function setStageAvatar(name, avatar, uid, isOwner) {
    utils.setAvatarElements(name, avatar, uid, refs.stageAvatarImg, refs.stageAvatarInitials);
    refs.stageOwnerBadge.style.display = isOwner ? '' : 'none';
    refs.stageNameEl.textContent = name || 'User';
  }

  /* Apply stage to peerId */
  function applyStage(peerId) {
    state.stagePeerId = peerId;
    for (const [, entry] of state.peers.entries()) {
      if (entry.card) entry.card.classList.remove('active-stage');
    }
    if (peerId === 'local') {
      const entry = state.peers.get('local');
      if (entry && entry.card) entry.card.classList.add('active-stage');
      if (localVideo.srcObject) stageVideo.srcObject = localVideo.srcObject;
      const isOwner = !!(state.ownerUid && state.myUid && state.ownerUid === state.myUid);
      setStageAvatar(state.meName, state.myAvatar, state.myUid, isOwner);
    } else {
      const entry = state.peers.get(peerId);
      if (entry && entry.card) entry.card.classList.add('active-stage');
      if (entry && entry.video && entry.video.srcObject) stageVideo.srcObject = entry.video.srcObject;
      const isOwner = !!(state.ownerUid && entry && entry.uid && state.ownerUid === entry.uid);
      const name = (entry && entry.name) ? entry.name : 'Remote';
      const avatar = (entry && entry.avatar) ? entry.avatar : '';
      const uid = (entry && entry.uid) ? entry.uid : '';
      setStageAvatar(name, avatar, uid, isOwner);
    }
  }

  /* Export applyStage and getStageMeta for recording overlay */
  App.applyStage = applyStage;
  App.getStageMeta = function() {
    if (state.stagePeerId === 'local') {
      return { name: state.meName, uid: state.myUid };
    }
    const entry = state.peers.get(state.stagePeerId);
    return {
      name: (entry && entry.name) ? entry.name : 'Remote',
      uid: (entry && entry.uid) ? entry.uid : '',
    };
  };

  /* Stage controls */
  refs.stageCollapseBtn.onclick = () => {
    state.userManuallyChoseStage = true;
    applyStage('local');
  };

  function isFullscreen() { return !!document.fullscreenElement; }
  function enterFullscreen() { const el = refs.stageVideoArea; if (el.requestFullscreen) el.requestFullscreen(); }
  function exitFullscreen() { if (document.exitFullscreen) document.exitFullscreen(); }
  function toggleFullscreen() { if (isFullscreen()) exitFullscreen(); else enterFullscreen(); }

  refs.stageFullscreenBtn.onclick = () => toggleFullscreen();
  document.addEventListener('fullscreenchange', () => {
    refs.stageFullscreenBtn.textContent = isFullscreen() ? 'Exit FS' : 'Fullscreen';
  });

  refs.stageVideoArea.onclick = () => {
    if (isFullscreen()) { exitFullscreen(); return; }
    if (state.stagePeerId !== 'local') applyStage('local');
  };

  /* Expose helpers */
  App.local = {
    setLocalAvatar,
  };
})();
