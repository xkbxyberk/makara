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
    const reply = await VD.api('api/supports', { query: { url } });
    state = VD.iconState(reply.offline ? null : reply.json, await getMedia(tabId));
  }
  if (latest.get(tabId) !== ticket) return;
  await browser.action.setIcon({ tabId, path: VD.ICONS[state] }).catch(() => undefined);
  await browser.action.setTitle({ tabId, title: t(VD.TITLES[state]) }).catch(() => undefined);
}

browser.tabs.onUpdated.addListener(async (tabId, change, tab) => {
  if (change.url) await setMedia(tabId, null);
  if (change.url || change.status === 'complete') void refresh(tabId, tab.url);
});
browser.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await browser.tabs.get(tabId).catch(() => null);
  if (tab) void refresh(tabId, tab.url);
});
browser.tabs.onRemoved.addListener((tabId) => {
  latest.delete(tabId);
  void setMedia(tabId, null);
});

browser.runtime.onMessage.addListener((message, sender) => {
  if (message?.type === 'media' && sender.tab?.id !== undefined) {
    void setMedia(sender.tab.id, message.found === true).then(() => refresh(sender.tab.id, sender.tab.url));
  }
  return undefined;
});

// ---- right-click on a link ------------------------------------------------------------------
// Made on every load, not only at install: whether Safari keeps them across a restart is not
// something to rely on. Removing first keeps it idempotent.
function installMenus() {
  browser.contextMenus.removeAll().finally(() => {
    browser.contextMenus.create({ id: 'vd-download', title: t('menu_download'), contexts: ['link'] });
    browser.contextMenus.create({ id: 'vd-inspect', title: t('menu_inspect'), contexts: ['link'] });
  });
}
installMenus();
browser.runtime.onInstalled.addListener(installMenus);

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  const link = info.linkUrl;
  if (!VD.isWebPage(link)) return; // never this Mac or the local network
  if (info.menuItemId === 'vd-inspect') {
    await VD.openApp(VD.inspectLink(link));
    return;
  }
  // One click: the remembered choice for that site (or today's default), straight to the queue.
  const reply = await VD.api('api/quick', { method: 'POST', body: { url: link, rule: await VD.loadRule(link) } });
  if (reply.offline) {
    await VD.openApp(VD.inspectLink(link)); // the app was closed: open it on that link instead
    return;
  }
  const tabId = tab?.id;
  if (tabId === undefined) return;
  await browser.action.setBadgeText({ tabId, text: reply.ok ? '✓' : '!' }).catch(() => undefined);
  setTimeout(() => browser.action.setBadgeText({ tabId, text: '' }).catch(() => undefined), 4000);
});
