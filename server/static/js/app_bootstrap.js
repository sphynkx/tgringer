/* ## App bootstrap, params, Telegram expand, utils */
(function(){
  /* Telegram WebApp expand */
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  try {
    if (tg) {
      tg.ready();
      tg.expand();
      setTimeout(() => { try { tg.expand(); } catch(_){} }, 400);
      setTimeout(() => { try { tg.expand(); } catch(_){} }, 1200);
    }
  } catch(_){}

  /* Query params */
  const qs = new URLSearchParams(location.search);
  const roomParam = qs.get('room') || '';
  const nameParam = qs.get('n') || '';
  const uidParam = qs.get('uid') || '';
  const avatarParam = qs.get('a') || '';
  const ownerParam = qs.get('owner') || '';

  /* UI refs */
  const refs = {
    roomInput: document.getElementById('roomInput'),
    roomLabel: document.getElementById('roomLabel'),
    joinBtn: document.getElementById('joinBtn'),
    hangupBtn: document.getElementById('hangupBtn'),
    copyLinkBtn: document.getElementById('copyLinkBtn'),
    testBtn: document.getElementById('testBtn'),
    toggleAudioBtn: document.getElementById('toggleAudioBtn'),
    toggleVideoBtn: document.getElementById('toggleVideoBtn'),
    shareScreenBtn: document.getElementById('shareScreenBtn'),
    shareSysAudioToOthersChk: document.getElementById('shareSysAudioToOthersChk'),
    recordSysAudioChk: document.getElementById('recordSysAudioChk'),

    stageVideoArea: document.getElementById('stageVideoArea'),
    stageNameEl: document.getElementById('stageName'),
    stageOwnerBadge: document.getElementById('stageOwnerBadge'),
    stageAvatarImg: document.getElementById('stageAvatarImg'),
    stageAvatarInitials: document.getElementById('stageAvatarInitials'),
    stageFullscreenBtn: document.getElementById('stageFullscreenBtn'),
    stageCollapseBtn: document.getElementById('stageCollapseBtn'),

    thumbsStrip: document.getElementById('thumbsStrip'),
    recordIndicator: document.getElementById('recordIndicator'),
    screenIndicator: document.getElementById('screenIndicator'),
  };

  /* Telegram user info */
  const tgApp = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const initUser = tgApp && tgApp.initDataUnsafe ? (tgApp.initDataUnsafe.user || null) : null;
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

  /* State */
  const state = {
    roomId: roomParam || '',
    meName,
    myUid,
    myAvatar,
    isOwnerByLink: (ownerParam === '1'),
    ownerUid: '',
    ws: null,
    localStream: null,
    peers: new Map(),
    joined: false,
    connecting: false,
    audioEnabled: true,
    videoEnabled: true,
    stagePeerId: 'local',
    userManuallyChoseStage: false,

    /* Screen share state */
    isScreenSharing: false,
    screenStream: null,
    prevVideoTrack: null,
    screenAudioSenders: new Map(), /* peerId -> RTCRtpSender */
  };

  if (state.roomId && refs.roomInput) refs.roomInput.value = state.roomId;
  if (refs.roomLabel) refs.roomLabel.textContent = state.roomId || '(none)';

  /* Utils */
  function wsUrl(path) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}${path}`;
  }

  function getLinkForRoom(id) {
    const base = `${location.origin}${location.pathname}`;
    return `${base}?room=${encodeURIComponent(id)}`;
  }

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

  /* Export namespace */
  window.App = {
    tgApp,
    qs,
    refs,
    state,
    utils: {
      wsUrl,
      getLinkForRoom,
      getInitials,
      colorFromString,
      setAvatarElements,
    },
  };
})();
