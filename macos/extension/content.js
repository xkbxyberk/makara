// Finds the media Berk is watching or listening to, and the one address yt-dlp can download it
// from: on a feed (X, Instagram, Reddit, TikTok, Facebook) that is the post the player sits in,
// not the page. Only this extension's background script hears about it; it asks the app (on
// this Mac, offline) whether the address is supported, and may then ask this script to offer
// the download in a small card on the page (Settings > Safari).
(() => {
  const MANIFEST = /\.(m3u8|mpd)(\?|#|$)/i;
  const DIRECT = /\.(mp4|m4v|webm|mov|mp3|m4a|ogg|opus|flac|wav)(\?|#|$)/i;
  const t = (key) => browser.i18n.getMessage(key);
  const host = location.hostname.toLowerCase().replace(/^(www|m|mobile)\./, '');

  /** Links next to a player that name its post, per site. The first that is a post wins. */
  const POSTS = [
    // X: the post's own timestamp is the link to it (a quoted post's has no <time> link).
    [['x.com', 'twitter.com'], 'article', 'a[href*="/status/"]:has(time)', 'a[href*="/status/"]'],
    [['instagram.com'], 'article', 'a[href*="/p/"], a[href*="/reel/"]'],
    [['reddit.com', 'old.reddit.com', 'new.reddit.com'], 'shreddit-post, article, .thing', 'a[href*="/comments/"]'],
    [['tiktok.com'], '[data-e2e="recommend-list-item-container"], article, [class*="ItemContainer"]', 'a[href*="/video/"]'],
    [['facebook.com'], '[role="article"]', 'a[href*="/videos/"], a[href*="/reel/"], a[href*="/watch"]'],
    [['youtube.com'], 'ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-reel-video-renderer',
      'a[href*="/watch?v="], a[href*="/shorts/"]'],
  ];

  /** Addresses for one player, best first; the background keeps the first the app supports. */
  function candidates(media) {
    const list = [];
    const add = (url, direct = false) => {
      if (url && !list.some((c) => c.url === url)) list.push({ url, direct });
    };
    // An empty href would resolve to the page itself.
    const link = (href) => (href ? VD.permalink(href, location.href) : null);
    for (const [hosts, container, ...links] of POSTS) {
      if (!hosts.includes(host) || !media) continue;
      const post = media.closest(container);
      // Reddit's post element carries its address itself.
      add(link(post?.getAttribute?.('permalink')));
      for (const selector of links) {
        for (const a of post?.querySelectorAll(selector) ?? []) add(link(a.getAttribute('href')));
      }
    }
    // SoundCloud plays from an <audio> outside the page; its player bar names the track.
    if (host === 'soundcloud.com' && document.querySelector('.playControl.playing')) {
      add(link(document.querySelector('a.playbackSoundBadge__titleLink')?.getAttribute('href')));
    }
    add(VD.permalink(location.href));
    const canonical = document.querySelector('link[rel="canonical"]')?.href;
    const og = document.querySelector('meta[property="og:url"]')?.content;
    for (const url of [canonical, og]) add(link(url));
    // A plain file the player loads (not a blob: stream) can be downloaded as it is.
    const src = media?.currentSrc;
    if (src && VD.isWebPage(src) && DIRECT.test(src)) add(src, true);
    return list.filter((c) => VD.isWebPage(c.url)).slice(0, 6);
  }

  function area(el) {
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    return w * h;
  }

  /** The player that matters now: one that plays (with sound first), else the most visible. */
  function current() {
    const all = [...document.querySelectorAll('video, audio')];
    const score = (el) => (!el.paused ? 2e9 : 0) + (!el.paused && !el.muted ? 2e9 : 0) + area(el);
    return all.sort((a, b) => score(b) - score(a))[0] ?? null;
  }

  function hasMedia() {
    // A <video> or <audio> element: even a blob: one (sites that stream through Media Source)
    // means the page plays media; yt-dlp works from the page URL, not the element.
    if (document.querySelector('video, audio')) return true;
    return performance.getEntriesByType('resource').some((entry) => MANIFEST.test(entry.name));
  }

  const send = (message) => browser.runtime.sendMessage(message).catch(() => undefined);

  let last = '';
  function report() {
    const found = hasMedia() || host === 'soundcloud.com';
    const list = found ? candidates(current()) : [];
    const key = JSON.stringify([found, list]);
    if (key === last) return;
    last = key;
    void send({ type: 'media', found, candidates: list });
  }

  // ---- the offer --------------------------------------------------------------------------------
  // Asked when a player starts playing *with sound* and is big enough to be the thing watched:
  // muted autoplay in a feed, GIF-like loops and small previews do not count.
  const asked = new WeakSet();

  function watched(media) {
    if (media.paused || media.muted || media.volume === 0) return false;
    if (media instanceof HTMLVideoElement) {
      const r = media.getBoundingClientRect();
      if (r.width < 200 || r.height < 110) return false;
    }
    return true;
  }

  async function maybeOffer(media) {
    if (asked.has(media) || !watched(media)) return;
    asked.add(media);
    const reply = await send({ type: 'playing', candidates: candidates(media) });
    if (reply?.offer) card.show(media, reply.offer);
  }

  for (const event of ['play', 'playing', 'volumechange']) {
    document.addEventListener(event, (e) => {
      if (e.target instanceof HTMLMediaElement) {
        report();
        void maybeOffer(e.target);
      }
    }, true);
  }
  document.addEventListener('pause', report, true);

  // SoundCloud's player has no element on the page to listen to: watch its play button.
  if (host === 'soundcloud.com') {
    let playing = null;
    setInterval(() => {
      const href = document.querySelector('.playControl.playing') && document.querySelector('a.playbackSoundBadge__titleLink')?.getAttribute('href');
      if (!href || href === playing) return;
      playing = href;
      report();
      void send({ type: 'playing', candidates: candidates(null) }).then((reply) => reply?.offer && card.show(null, reply.offer));
    }, 1500);
  }

  /**
   * The card: in a closed shadow root, so the page can neither style nor read it, and every
   * handler ignores synthetic (page-made) clicks. Its texts are the extension's own.
   */
  const card = (() => {
    let frame = null;
    let hideTimer = 0;
    let follow = 0;

    function remove() {
      clearTimeout(hideTimer);
      cancelAnimationFrame(follow);
      frame?.remove();
      frame = null;
    }

    function place(box, media) {
      const width = 300;
      let top = 16;
      let left = innerWidth - width - 16;
      const r = media?.isConnected ? media.getBoundingClientRect() : null;
      if (r && r.bottom > 60 && r.top < innerHeight - 60) {
        top = Math.min(Math.max(r.top + 12, 12), innerHeight - 120);
        left = Math.min(Math.max(r.right - width - 12, 12), innerWidth - width - 12);
      }
      box.style.top = `${Math.round(top)}px`;
      box.style.left = `${Math.round(left)}px`;
    }

    function show(media, offer) {
      remove();
      frame = document.createElement('div');
      const root = frame.attachShadow({ mode: 'closed' });
      const style = document.createElement('style');
      style.textContent = CSS;
      const box = document.createElement('div');
      box.className = 'card';
      box.setAttribute('role', 'dialog');
      box.setAttribute('aria-label', t('offer_title'));
      const icon = glyph();
      const text = document.createElement('div');
      text.className = 'text';
      const title = document.createElement('strong');
      title.textContent = t(media instanceof HTMLAudioElement || !media ? 'offer_title_audio' : 'offer_title');
      const status = document.createElement('span');
      status.className = 'status';
      status.textContent = t('offer_body');
      text.append(title, status);
      const close = button('×', 'close', () => {
        void send({ type: 'dismiss', url: offer.url });
        remove();
      });
      close.setAttribute('aria-label', t('offer_close'));
      const actions = document.createElement('div');
      actions.className = 'actions';
      const download = button(t('offer_download'), 'primary', async () => {
        clearTimeout(hideTimer);
        for (const b of actions.querySelectorAll('button')) b.disabled = true;
        status.textContent = t('offer_adding');
        const reply = await send({ type: 'download', url: offer.url });
        if (reply?.ok) {
          title.textContent = t('offer_added');
          status.textContent = t('offer_added_body');
          actions.replaceChildren(button(t('offer_show'), '', () => {
            void send({ type: 'open', url: 'videodownloader://show?route=download' });
            remove();
          }));
          hideTimer = setTimeout(remove, 5000);
        } else {
          title.textContent = t('offer_failed');
          status.textContent = reply?.offline ? t('title_offline') : (browser.i18n.getMessage(`error_${reply?.code}`) || t('offer_failed_body'));
          actions.replaceChildren(button(t('popup_open_in_app'), '', () => {
            void send({ type: 'inspect', url: offer.url });
            remove();
          }));
        }
      });
      const choose = button(t('offer_choose'), '', () => {
        void send({ type: 'inspect', url: offer.url });
        remove();
      });
      const mute = button(t('offer_mute'), 'link', () => {
        void send({ type: 'mute', url: location.href });
        remove();
      });
      actions.append(download, choose, mute);
      box.append(icon, text, close, actions);
      root.append(style, box);
      // Inside a full-screen player's container, or it would be hidden behind it.
      const full = document.fullscreenElement;
      (full && !(full instanceof HTMLMediaElement) ? full : document.documentElement).append(frame);
      const track = () => {
        place(box, media);
        follow = requestAnimationFrame(track);
      };
      track();
      // Unanswered, it goes away by itself (and is not asked again for this video).
      hideTimer = setTimeout(remove, 15000);
      box.addEventListener('pointerenter', () => clearTimeout(hideTimer));
    }

    /** Drawn inline: an extension image would have to be readable by every page (a fingerprint),
     * and a data: image is blocked by many sites' content policy. */
    function glyph() {
      const NS = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(NS, 'svg');
      svg.setAttribute('viewBox', '0 0 32 32');
      svg.setAttribute('class', 'icon');
      svg.setAttribute('aria-hidden', 'true');
      const shape = (name, attrs) => {
        const el = document.createElementNS(NS, name);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
        svg.append(el);
      };
      shape('rect', { x: '1', y: '1', width: '30', height: '30', rx: '8', fill: '#0a84ff' });
      shape('path', { d: 'M16 8v12m-5-5 5 5 5-5M10 24h12', fill: 'none', stroke: '#fff', 'stroke-width': '2.4',
        'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
      return svg;
    }

    function button(label, kind, action) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = kind;
      b.textContent = label;
      b.addEventListener('click', (event) => {
        if (event.isTrusted) void action();
      });
      return b;
    }

    return { show, remove };
  })();

  const CSS = `
    :host { all: initial; }
    .card {
      position: fixed; z-index: 2147483647; width: 300px; box-sizing: border-box;
      display: grid; grid-template-columns: 32px 1fr auto; gap: 4px 10px; align-items: start;
      padding: 12px 12px 10px; border-radius: 14px;
      font: 13px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
      color: #1d1d1f; background: rgba(250, 250, 252, 0.86);
      -webkit-backdrop-filter: saturate(180%) blur(20px); backdrop-filter: saturate(180%) blur(20px);
      box-shadow: 0 0 0 0.5px rgba(0, 0, 0, 0.18), 0 10px 30px rgba(0, 0, 0, 0.22);
      animation: in 0.18s ease-out;
    }
    @media (prefers-color-scheme: dark) {
      .card { color: #f5f5f7; background: rgba(40, 40, 44, 0.86);
        box-shadow: 0 0 0 0.5px rgba(255, 255, 255, 0.16), 0 10px 30px rgba(0, 0, 0, 0.5); }
      button { background: rgba(255, 255, 255, 0.12); color: #f5f5f7; }
      .status { color: rgba(245, 245, 247, 0.65); }
    }
    @media (prefers-reduced-motion: reduce) { .card { animation: none; } }
    @keyframes in { from { opacity: 0; transform: translateY(-4px); } }
    .icon { width: 32px; height: 32px; grid-row: span 2; }
    .text { display: flex; flex-direction: column; min-width: 0; }
    strong { font-weight: 600; }
    .status { color: rgba(29, 29, 31, 0.62); font-size: 12px; }
    .actions { grid-column: 2 / 4; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 4px; }
    button {
      font: inherit; font-size: 12px; border: 0; border-radius: 7px; padding: 4px 10px; cursor: default;
      background: rgba(0, 0, 0, 0.07); color: #1d1d1f;
    }
    button:focus-visible { outline: 2px solid #0a84ff; outline-offset: 1px; }
    button:disabled { opacity: 0.5; }
    .primary { background: #0a84ff; color: #fff; font-weight: 500; }
    .link { background: none; padding: 4px 2px; color: #0a84ff; margin-left: auto; }
    .close { background: none; padding: 0 4px; font-size: 16px; line-height: 1; opacity: 0.55; }
    .close:hover { opacity: 1; }
  `;

  report();
  // Single-page sites swap their player in and out; look again, at most twice a second.
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    setTimeout(() => {
      pending = false;
      report();
    }, 500);
  }).observe(document.documentElement, { childList: true, subtree: true });
  // Scrolling a feed changes which player is the one in view.
  let scrolled = 0;
  addEventListener('scroll', () => {
    clearTimeout(scrolled);
    scrolled = setTimeout(report, 300);
  }, { passive: true });
})();
