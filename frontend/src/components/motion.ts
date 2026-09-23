/**
 * Motion that CSS alone cannot express. Everything else (screen changes, sheets, the sidebar,
 * help tags) is plain CSS in theme.css, and all of it stops under "Reduce motion".
 */

const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/**
 * Segmented controls slide their selection like NSSegmentedControl instead of jumping. One
 * observer serves every `.segmented` in the app, so the controls stay plain radio buttons: the
 * container gets the active segment's position as CSS variables and draws the thumb itself.
 */
export function installSegmentThumbs(root: HTMLElement): () => void {
  let frame = 0;

  const place = () => {
    frame = 0;
    for (const group of root.querySelectorAll<HTMLElement>('.segmented')) {
      const active = group.querySelector<HTMLElement>('.segment.active');
      if (!active || active.offsetWidth === 0) {
        delete group.dataset.thumb;
        group.classList.remove('thumb-ready');
        continue;
      }
      group.style.setProperty('--thumb-x', `${active.offsetLeft}px`);
      group.style.setProperty('--thumb-w', `${active.offsetWidth}px`);
      if (group.dataset.thumb === undefined) {
        // First placement: appear in place, and only animate from the next change on.
        group.dataset.thumb = '';
        requestAnimationFrame(() => group.classList.add('thumb-ready'));
      }
    }
  };
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(place);
  };

  const mutations = new MutationObserver(schedule);
  mutations.observe(root, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class', 'aria-checked', 'hidden'],
  });
  window.addEventListener('resize', schedule);
  void document.fonts?.ready.then(schedule);
  schedule();

  return () => {
    mutations.disconnect();
    window.removeEventListener('resize', schedule);
    cancelAnimationFrame(frame);
  };
}

/** Theme changes cross-fade the whole window where WebKit/Chromium support view transitions. */
export function withViewTransition(update: () => void): void {
  const start = (document as Document & { startViewTransition?: (cb: () => void) => unknown })
    .startViewTransition;
  if (!start || reduced()) {
    update();
    return;
  }
  start.call(document, update);
}
