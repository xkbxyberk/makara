// The toolbar icon and the link menu. Safari may unload this script at any time, so every
// listener is registered at the top level and per-tab state lives in session storage.
const t = (key, ...subs) => browser.i18n.getMessage(key, subs.map(String));

// ---- whether a tab's page plays media (reported by content.js) ------------------------------
// Session storage survives the background being unloaded (it is cleared when Safari quits);
// without it, a page with a player on an unknown site would lose its lit icon.
const memory = new Map();
const sessionStore = browser.storage?.session;

async function getMedia(tabId) {
  if (!sessionStore) return memory.get(tabId) === true;
  const key = `media:${tabId}`;
  return (await sessionStore.get(key).catch(() => ({})))?.[key] === true;
}

async function setMedia(tabId, found) {
  if (!sessionStore) {
    if (found === null) memory.delete(tabId);
    else memory.set(tabId, found);
    return;
  }
  const key = `media:${tabId}`;
  await (found === null ? sessionStore.remove(key) : sessionStore.set({ [key]: found })).catch(() => undefined);
}

// ---- small per-tab and per-session records -------------------------------------------------------
async function sessionGet(key, fallback) {
  if (!sessionStore) return memory.has(key) ? memory.get(key) : fallback;
  return (await sessionStore.get(key).catch(() => ({})))?.[key] ?? fallback;
}

async function sessionSet(key, value) {
  if (!sessionStore) {
    if (value === null) memory.delete(key);
    else memory.set(key, value);
    return;
  }
  await (value === null ? sessionStore.remove(key) : sessionStore.set({ [key]: value })).catch(() => undefined);
}

/** What the page's player is, as an address the app supports: `{url, kind}` or null. */
const getTarget = (tabId) => sessionGet(`target:${tabId}`, null);
const setTarget = (tabId, target) => sessionSet(`target:${tabId}`, target);

// ---- which address the app can download -----------------------------------------------------
const supportsCache = new Map(); // url -> {at, answer}: a feed reports the same posts again and again

async function supportsOf(url) {
  const hit = supportsCache.get(url);
  if (hit && Date.now() - hit.at < 60_000) return hit.answer;
  const reply = await VD.api('api/supports', { query: { url } });
  const answer = reply.offline ? null : reply.json;
  if (answer) {
    if (supportsCache.size > 300) supportsCache.clear();
    supportsCache.set(url, { at: Date.now(), answer });
  }
  return answer;
}

/**
 * The first of the page's candidates (best first, see content.js) that is one video or sound
 * the app knows: a post's own address beats the feed it is shown in. A list (a channel, an
 * album) is kept only when nothing better is there. `offline` when the app does not answer.
 */
async function resolve(candidates) {
  let list = null;
  for (const candidate of (Array.isArray(candidates) ? candidates : []).slice(0, 6)) {
    const url = typeof candidate?.url === 'string' ? candidate.url : '';
    if (!VD.isWebPage(url) || url.length > 2048) continue;
    if (candidate.direct === true) return { url, kind: 'video' };
    const answer = await supportsOf(url);
    if (answer === null) return { offline: true };
    if (!answer.supported) continue;
    if (answer.kind !== 'playlist') return { url, kind: answer.kind, downloaded: answer.downloaded === true };
    list ??= { url, kind: 'playlist' };
  }
  return list;
}

// ---- offering the download on the page --------------------------------------------------------
const MUTED_KEY = 'offerMuted';

/** The app's setting (Ayarlar > Safari): "page" offers on the page, "icon" lights the icon only. */
let offerSetting = { at: 0, value: 'page' };
async function offerMode() {
  if (Date.now() - offerSetting.at < 30_000) return offerSetting.value;
  const reply = await VD.api('api/extension');
  const value = reply.ok && reply.json?.offer === 'icon' ? 'icon' : 'page';
  offerSetting = { at: Date.now(), value };
  return value;
}

async function mutedSites() {
  return (await browser.storage.local.get(MUTED_KEY).catch(() => ({})))?.[MUTED_KEY] ?? {};
}

async function setMuted(url, muted) {
  const site = VD.siteOf(url);
  if (!site) return;
  const sites = await mutedSites();
  if (muted) sites[site] = true;
  else delete sites[site];
  await browser.storage.local.set({ [MUTED_KEY]: sites }).catch(() => undefined);
}

/** Each video is offered once a session: dismissed, ignored or downloaded, it is not asked again. */
async function firstOffer(url) {
  const offered = await sessionGet('offered', []);
  if (offered.includes(url)) return false;
  await sessionSet('offered', [...offered.slice(-499), url]);
  return true;
}

async function offerFor(tab, candidates) {
  const target = await resolve(candidates);
  if (!target || target.offline || target.kind === 'playlist') return null;
  await setTarget(tab.id, target);
  void refresh(tab.id, tab.url);
  if ((await offerMode()) !== 'page') return null;
  if ((await mutedSites())[VD.siteOf(tab.url)]) return null;
  if (!(await firstOffer(target.url))) return null;
  return { url: target.url, downloaded: target.downloaded === true };
}

/**
 * Show the offer where Berk expects it, in the extension's own menu under its toolbar icon
 * (Berk, 14 Oct). Safari may refuse to open it without a click, or open nothing: only when the
 * popup itself says it is up does that count. Otherwise the page shows its card.
 */
let popupOpened = null;
async function present(tab, offer) {
  if (typeof browser.action?.openPopup !== 'function') return offer;
  const opened = new Promise((resolve) => {
    popupOpened = resolve;
    setTimeout(() => resolve(false), 900);
  });
  try {
    await browser.action.openPopup({ windowId: tab.windowId });
  } catch {
    return offer;
  }
  return (await opened) ? null : offer;
}

/** One click: the remembered choice for that site (or today's default), straight to the queue. */
async function quick(link) {
  const reply = await VD.api('api/quick', { method: 'POST', body: { url: link, rule: await VD.loadRule(link) } });
  return { ok: reply.ok === true, offline: reply.offline === true, code: reply.json?.error?.code ?? null };
}

// ---- the icon --------------------------------------------------------------------------------
const latest = new Map(); // tab id -> the newest refresh, so a slow old answer cannot win

/**
 * Ask the app (offline, a few milliseconds: no site is contacted) whether yt-dlp knows this
 * page, and show the answer on the icon. Only the page's address goes, and only to the app on
 * this Mac; local and non-web pages are not asked about at all.
 */
async function refresh(tabId, url) {
  if (tabId === undefined || tabId < 0) return;
  const ticket = (latest.get(tabId) ?? 0) + 1;
  latest.set(tabId, ticket);
  let state = 'none';
  if (VD.isWebPage(url)) {
    // The player's own post first (a feed page itself is not something to download).
    const target = await getTarget(tabId);
    const answer = target ? { supported: true, kind: target.kind } : await supportsOf(url);
    state = VD.iconState(answer, await getMedia(tabId));
  }
  if (latest.get(tabId) !== ticket) return;
  await browser.action.setIcon({ tabId, path: VD.ICONS[state] }).catch(() => undefined);
  await browser.action.setTitle({ tabId, title: t(VD.TITLES[state]) }).catch(() => undefined);
}

browser.tabs.onUpdated.addListener(async (tabId, change, tab) => {
  if (change.url) await Promise.all([setMedia(tabId, null), setTarget(tabId, null)]);
  if (change.url || change.status === 'complete') void refresh(tabId, tab.url);
});
browser.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await browser.tabs.get(tabId).catch(() => null);
  if (tab) void refresh(tabId, tab.url);
});
browser.tabs.onRemoved.addListener((tabId) => {
  latest.delete(tabId);
  void setMedia(tabId, null);
  void setTarget(tabId, null);
});

/** Messages from content.js (the page's player, the card's buttons) and the popup. */
browser.runtime.onMessage.addListener((message, sender) => {
  const tab = sender.tab;
  const url = typeof message?.url === 'string' ? message.url : '';
  switch (message?.type) {
    case 'media':
      if (tab?.id === undefined) return undefined;
      return (async () => {
        await setMedia(tab.id, message.found === true);
        const target = message.found === true ? await resolve(message.candidates) : null;
        await setTarget(tab.id, target && !target.offline ? target : null);
        await refresh(tab.id, tab.url);
      })();
    case 'playing':
      if (tab?.id === undefined) return undefined;
      return offerFor(tab, message.candidates)
        .then((offer) => (offer ? present(tab, offer) : null))
        .then((offer) => ({ offer }));
    case 'popup-open':
      popupOpened?.(true);
      popupOpened = null;
      return Promise.resolve(true);
    case 'download':
      return VD.isWebPage(url) ? quick(url) : Promise.resolve({ ok: false });
    case 'inspect':
      return VD.isWebPage(url) ? VD.openApp(VD.inspectLink(url)) : Promise.resolve(false);
    case 'open':
      return ['makara://show?route=download', 'makara://show?route=library'].includes(url)
        ? VD.openApp(url)
        : Promise.resolve(false);
    case 'dismiss':
      return Promise.resolve(true); // already recorded as offered
    case 'mute':
      return setMuted(url, true);
    default:
      return undefined;
  }
});

// ---- right-click on a link ------------------------------------------------------------------
// Made on every load, not only at install: whether Safari keeps them across a restart is not
// something to rely on. One run at a time, because a load can also get onInstalled: two at once
// create every id twice. An id that is still there is no failure, but the callback must read
// lastError all the same, or Safari records an unchecked error on the extension (gotcha 56).
const MENUS = () => [
  { id: 'vd-download', title: t('menu_download'), contexts: ['link'] },
  { id: 'vd-inspect', title: t('menu_inspect'), contexts: ['link'] },
  // On the page itself and on a player. YouTube answers the first right-click on its player
  // with its own menu; a second right-click there opens Safari's, with this item in it.
  { id: 'vd-page', title: t('menu_download_page'), contexts: ['page', 'video', 'audio', 'frame'] },
];

const createMenu = (item) =>
  new Promise((done) => {
    browser.contextMenus.create(item, () => {
      void browser.runtime.lastError;
      done();
    });
  });

let menusReady = Promise.resolve();
function installMenus() {
  menusReady = menusReady
    .then(async () => {
      await browser.contextMenus.removeAll().catch(() => undefined);
      for (const item of MENUS()) await createMenu(item);
    })
    .catch(() => undefined);
  return menusReady;
}
installMenus();
browser.runtime.onInstalled.addListener(installMenus);

/**
 * What "download this page" means where Berk right-clicked: a player's own http(s) file if it
 * has one; else the embedded page (a YouTube player inside another site's frame); else the page.
 * A blob: stream is something only the page can explain, and yt-dlp works from the page.
 */
function pageLink(info, tab) {
  if ((info.mediaType === 'video' || info.mediaType === 'audio') && VD.isWebPage(info.srcUrl)) return info.srcUrl;
  if (VD.isWebPage(info.frameUrl) && info.frameUrl !== info.pageUrl) return info.frameUrl;
  return info.pageUrl ?? tab?.url;
}

async function flash(tabId, ok) {
  await browser.action.setBadgeText({ tabId, text: ok ? '✓' : '!' }).catch(() => undefined);
  setTimeout(() => browser.action.setBadgeText({ tabId, text: '' }).catch(() => undefined), 4000);
}

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  const link = info.menuItemId === 'vd-page' ? pageLink(info, tab) : info.linkUrl;
  if (!VD.isWebPage(link)) {
    // Never this Mac or the local network, nor a non-web frame: say no instead of doing nothing.
    if (tab?.id !== undefined) await flash(tab.id, false);
    return;
  }
  if (info.menuItemId === 'vd-inspect') {
    await VD.openApp(VD.inspectLink(link));
    return;
  }
  const reply = await quick(link);
  if (reply.offline) {
    await VD.openApp(VD.inspectLink(link)); // the app was closed: open it on that link instead
    return;
  }
  if (tab?.id !== undefined) await flash(tab.id, reply.ok);
});
