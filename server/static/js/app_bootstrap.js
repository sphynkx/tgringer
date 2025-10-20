/* ## App bootstrap, params, Telegram expand, utils */
(function(){
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
  const roomParam   = qs.get('room') || '';
  const nameParam   = qs.get('n') || '';
  const uidParam    = qs.get('uid') || '';
  const avatarParam = qs.get('a') || '';
  const chatParam   = qs.get('chat') || qs.get('chat_id') || '';
  const ownerParam  = qs.get('owner') || '';
  const uPacked     = qs.get('u') || '';

  /* Helpers */
  function base64UrlDecode(s) {
    try {
      let b64 = s.replace(/-/g, '+').replace(/_/g, '/');
      const pad = b64.length % 4;
      if (pad) b64 += '='.repeat(4 - pad);
      const json = atob(b64);
      return JSON.parse(json);
    } catch (e) {
      console.warn('[BOOT] u param decode failed', e);
      return null;
    }
  }

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

  /* Telegram init user (WebView) */
  const tgApp = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const initUser  = tgApp && tgApp.initDataUnsafe ? (tgApp.initDataUnsafe.user || null) : null;
  const initUid   = initUser && initUser.id ? String(initUser.id) : '';
  const initPhoto = initUser && initUser.photo_url ? initUser.photo_url : '';
  const initName  = (() => {
    if (!initUser) return '';
    const fn = initUser.first_name || '';
    const ln = initUser.last_name || '';
    const uname = initUser.username ? '@' + initUser.username : '';
    const full = [fn, ln].join(' ').trim();
    return full || uname || '';
  })();

  /* Server-injected user info + fallback from URL u= (base64url JSON) */
  const injected = (typeof window.USER_INFO === 'object' && window.USER_INFO) ? window.USER_INFO : null;
  const fromUPacked = uPacked ? base64UrlDecode(uPacked) : null;
  const meInfo = injected && injected.user_id ? injected : (fromUPacked && fromUPacked.user_id ? fromUPacked : {});

  const meName = (() => {
    const serverName = ([meInfo.first_name || '', meInfo.last_name || ''].join(' ').trim()) || (meInfo.username ? '@' + meInfo.username : '');
    return serverName || (nameParam ? decodeURIComponent(nameParam) : '') || initName || 'Me';
  })();

  const myUid    = (meInfo.user_id ? String(meInfo.user_id) : '') || uidParam || initUid || '';
  const myAvatar = (meInfo.avatar_url || '') || (avatarParam ? decodeURIComponent(avatarParam) : '') || initPhoto || '';

  const state = {
    roomId: roomParam || '',
    meName,
    myUid,
    myAvatar,
    chatId: (chatParam || ((meInfo.user_id && String(meInfo.user_id)) || '') || myUid || ''),  /* default chat -> myUid */
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

    isScreenSharing: false,
    screenStream: null,
    prevVideoTrack: null,
    screenAudioSenders: new Map(),
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
    const params = new URLSearchParams();
    params.set('room', id || '');
    if (state.myUid) params.set('uid', state.myUid);
    if (state.meName && state.meName !== 'Me') params.set('n', state.meName);
    if (state.myAvatar) params.set('a', state.myAvatar);
    if (state.chatId) params.set('chat', state.chatId);
    if (state.isOwnerByLink) params.set('owner', '1');
    return `${base}?${params.toString()}`;
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

  window.App = {
    tgApp,
    qs,
    refs,
    state,
    utils: { wsUrl, getLinkForRoom, getInitials, colorFromString, setAvatarElements },
  };

  try {
    if (refs.stageNameEl) refs.stageNameEl.textContent = state.meName || 'Me';
    if (refs.stageAvatarImg || refs.stageAvatarInitials) {
      setAvatarElements(state.meName, state.myAvatar, state.myUid, refs.stageAvatarImg, refs.stageAvatarInitials);
    }
    if (state.isOwnerByLink && !state.myUid && meInfo && meInfo.user_id) {
      /* final fallback */
      state.myUid = String(meInfo.user_id);
      state.chatId = state.chatId || state.myUid;
    }
  } catch(_){}

  console.log('[BOOT] state:', {
    roomId: state.roomId, myUid: state.myUid, chatId: state.chatId,
    meName: state.meName, hasAvatar: !!state.myAvatar, ownerLink: state.isOwnerByLink,
    hasInjectedUser: !!(injected && injected.user_id), hasUPacked: !!fromUPacked
  });
})();