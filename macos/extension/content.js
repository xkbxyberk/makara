// Looks at the page for playable media, for the toolbar icon only. Nothing leaves the
// browser: the answer goes to this extension's background script, which shows it on the icon.
(() => {
  const MANIFEST = /\.(m3u8|mpd)(\?|#|$)/i;

  function hasMedia() {
    // A <video> or <audio> element: even a blob: one (sites that stream through Media Source)
    // means the page plays media; yt-dlp works from the page URL, not the element.
    if (document.querySelector('video, audio')) return true;
    return performance.getEntriesByType('resource').some((entry) => MANIFEST.test(entry.name));
  }

  let last = null;
  function report() {
    const found = hasMedia();
    if (found === last) return;
    last = found;
    browser.runtime.sendMessage({ type: 'media', found }).catch(() => undefined);
  }

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
})();
