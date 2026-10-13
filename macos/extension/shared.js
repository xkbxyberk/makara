// Shared by the background script, the popup and the unit tests (no modules: Safari's
// background scripts are classic scripts). Everything hangs off `globalThis.VD`.
//
// The extension never decides *what* to download: the backend's quick choices (`offers`,
// see backend/app/ytdlp/offers.py) do. This file only talks to the app, remembers a choice,
// and formats what the backend says.
(() => {
  /** Hosts that are one site for a remembered choice. Mirrors `QuickRules.site(of:)` in the app. */
  const ALIASES = { 'youtu.be': 'youtube.com', 'music.youtube.com': 'youtube.com' };

  function siteOf(url) {
    try {
      const { protocol, hostname } = new URL(url);
      if (protocol !== 'http:' && protocol !== 'https:') return null;
      const host = hostname.toLowerCase().replace(/^(www|m)\./, '');
      return ALIASES[host] ?? (host || null);
    } catch {
      return null;
    }
  }

  /**
   * This Mac and the local network. Mirrors LocalHost.swift, which the relay enforces anyway:
   * the extension never makes the app fetch a router, a NAS or the app's own API.
   */
  function isLocal(hostname) {
    const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
    if (!host || host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local')) return true;
    if (!host.includes('.') && !host.includes(':')) return true;
    if (host.includes(':')) {
      return host === '::1' || host === '::' || /^(fe80:|fc|fd|::ffff:)/.test(host);
    }
    const parts = host.split('.').map(Number);
    if (parts.length !== 4 || parts.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return false;
    const [a, b] = parts;
    return a === 127 || a === 10 || a === 0 || (a === 169 && b === 254) || (a === 192 && b === 168)
      || (a === 172 && b >= 16 && b <= 31) || (a === 100 && b >= 64 && b <= 127);
  }

  /** A public web page: something the app may inspect. */
  function isWebPage(url) {
    try {
      const { protocol, hostname } = new URL(url);
      return (protocol === 'http:' || protocol === 'https:') && !isLocal(hostname);
    } catch {
      return false;
    }
  }

  /**
   * The one address of a post or video, from a link found next to the media on the page: X's
   * `/status/<id>` without `/video/1` or `/photo/1`, Instagram's `/p|reel/<code>/`, a Reddit
   * post's `/comments/<id>/`, a TikTok `/@user/video/<id>`, a YouTube `watch?v=` or Short.
   * Anything else is kept as it is, without its #fragment. null for nothing or a non-web link.
   */
  function permalink(href, base) {
    let url;
    try {
      url = new URL(href, base);
    } catch {
      return null;
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    const host = url.hostname.toLowerCase().replace(/^(www|m|mobile)\./, '');
    const path = url.pathname;
    let match;
    if (host === 'x.com' || host === 'twitter.com') {
      match = path.match(/^\/([A-Za-z0-9_]{1,30})\/status\/(\d{1,25})(?:\/|$)/);
      return match ? `https://x.com/${match[1]}/status/${match[2]}` : null;
    }
    if (host === 'instagram.com') {
      match = path.match(/^(?:\/[A-Za-z0-9_.]{1,30})?\/(p|reels?|tv)\/([A-Za-z0-9_-]{5,40})(?:\/|$)/);
      return match ? `https://www.instagram.com/${match[1] === 'p' ? 'p' : 'reel'}/${match[2]}/` : null;
    }
    if (host === 'reddit.com' || host === 'old.reddit.com' || host === 'new.reddit.com') {
      match = path.match(/^\/r\/([A-Za-z0-9_]{1,30})\/comments\/([a-z0-9]{1,12})(?:\/|$)/i);
      return match ? `https://www.reddit.com/r/${match[1]}/comments/${match[2]}/` : null;
    }
    if (host === 'tiktok.com') {
      match = path.match(/^\/@([A-Za-z0-9_.-]{1,40})\/video\/(\d{5,25})(?:\/|$)/);
      return match ? `https://www.tiktok.com/@${match[1]}/video/${match[2]}` : null;
    }
    if (host === 'youtube.com' || host === 'music.youtube.com' || host === 'youtu.be') {
      const id = host === 'youtu.be' ? path.slice(1) : url.searchParams.get('v') ?? path.match(/^\/shorts\/([^/]+)/)?.[1];
      if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) return null;
      return path.startsWith('/shorts/') ? `https://www.youtube.com/shorts/${id}` : `https://www.youtube.com/watch?v=${id}`;
    }
    url.hash = '';
    return url.href;
  }

  const positive = (value, max) =>
    value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value) && value > 0 && value <= max);

  /** The remembered shape of a choice, as /api/quick returns it. Same checks as the web panel. */
  function isRule(rule) {
    if (!rule || typeof rule !== 'object') return false;
    if (rule.kind === 'audio') return ['opus', 'm4a', 'mp3'].includes(rule.format);
    return (
      rule.kind === 'video' &&
      positive(rule.height, 10000) &&
      positive(rule.fps, 1000) &&
      (rule.hdr === undefined || typeof rule.hdr === 'boolean') &&
      (rule.output === undefined || rule.output === null || ['mkv', 'compat_mp4'].includes(rule.output))
    );
  }

  /**
   * What the toolbar icon says about a tab. `supports` is the backend's offline answer
   * (null: the app is not running); `media` is whether the page itself has a <video>/<audio>
   * or loads a streaming manifest.
   */
  function iconState(supports, media) {
    if (supports === null) return 'offline';
    if (supports.supported && supports.kind === 'playlist') return 'list';
    if (supports.supported || media) return 'ready';
    return 'none';
  }

  const ICONS = {
    ready: { 16: 'images/toolbar-active-16.png', 32: 'images/toolbar-active-32.png' },
    list: { 16: 'images/toolbar-active-16.png', 32: 'images/toolbar-active-32.png' },
    none: { 16: 'images/toolbar-16.png', 32: 'images/toolbar-32.png' },
    offline: { 16: 'images/toolbar-16.png', 32: 'images/toolbar-32.png' },
  };
  const TITLES = { ready: 'title_ready', list: 'title_list', none: 'title_none', offline: 'title_offline' };

  const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'];
  /** Binary units, exactly as the app shows them (`Format.bytes`). */
  function formatBytes(bytes) {
    if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '';
    if (bytes < 1024) return `${bytes} ${UNITS[0]}`;
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < UNITS.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value.toFixed(value >= 100 ? 0 : 1)} ${UNITS[unit]}`;
  }

  /** The backend's size confidence, as everywhere in the app: exact, ≈ approximate, ~ estimated. */
  function sizePrefix(kind) {
    return { approx: '≈', estimated: '~', partial: '≥' }[kind] ?? '';
  }

  function formatDuration(seconds) {
    if (!seconds || !Number.isFinite(seconds)) return '';
    const s = Math.round(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const rest = String(s % 60).padStart(2, '0');
    return h ? `${h}:${String(m).padStart(2, '0')}:${rest}` : `${m}:${rest}`;
  }

  /**
   * One request through the app's relay (SafariWebExtensionHandler + Relay.swift). Answers
   * `{ok, status, json}`, or `{ok: false, offline: true}` when the app does not answer.
   */
  async function api(path, { method = 'GET', query, body } = {}) {
    try {
      const reply = await browser.runtime.sendNativeMessage('application.id', { type: 'api', method, path, query, body });
      return reply ?? { ok: false, offline: true };
    } catch {
      return { ok: false, offline: true };
    }
  }

  /** Bring the app forward (or start it), optionally on a link or a screen. */
  async function openApp(link = 'videodownloader://show') {
    try {
      return (await browser.runtime.sendNativeMessage('application.id', { type: 'open', url: link }))?.ok === true;
    } catch {
      return false;
    }
  }

  function inspectLink(url) {
    return `videodownloader://inspect?url=${encodeURIComponent(url)}`;
  }

  // ---- remembered choices, per site, in the extension's own storage ----------------------
  const RULES_KEY = 'quickRules';

  async function loadRule(url) {
    const site = siteOf(url);
    if (!site) return null;
    const stored = (await browser.storage.local.get(RULES_KEY))?.[RULES_KEY] ?? {};
    return isRule(stored[site]) ? stored[site] : null;
  }

  async function saveRule(url, rule) {
    const site = siteOf(url);
    if (!site || !isRule(rule)) return;
    const stored = (await browser.storage.local.get(RULES_KEY))?.[RULES_KEY] ?? {};
    await browser.storage.local.set({ [RULES_KEY]: { ...stored, [site]: rule } });
  }

  globalThis.VD = {
    siteOf, isLocal, isWebPage, permalink, isRule, iconState, ICONS, TITLES, formatBytes, sizePrefix, formatDuration,
    api, openApp, inspectLink, loadRule, saveRule,
  };
})();
