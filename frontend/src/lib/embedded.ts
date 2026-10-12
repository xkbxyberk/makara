/**
 * The page inside the native VideoDownloader.app (`?embedded=1`). The app draws the sidebar,
 * the title and the Settings window itself, posts the notifications, and follows the system
 * appearance; the page only shows the screen it is asked for and reports where it went.
 */
const params = new URLSearchParams(window.location.search);

export const embedded = params.get('embedded') === '1';

/** The screen the native window asked for in the URL (`?route=library`). */
export const requestedRoute = params.get('route');

type NativeMessage = { type: 'route'; route: string } | { type: 'ready' };

export function postToNative(message: NativeMessage): void {
  const bridge = (window as unknown as {
    webkit?: { messageHandlers?: { vd?: { postMessage: (m: NativeMessage) => void } } };
  }).webkit?.messageHandlers?.vd;
  bridge?.postMessage(message);
}

/** The native Settings window: only the settings screen, nothing that could move it elsewhere
 * (no banners, no navigation) and no event stream of its own. */
export const settingsWindow = embedded && requestedRoute === 'settings';

if (embedded) document.documentElement.classList.add('embedded');
