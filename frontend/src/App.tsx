import { useCallback, useEffect, useRef, useState } from 'react';
import './theme.css';
import { tr } from './i18n/tr';
import { Icon, type SymbolName } from './components/Icon';
import { ToolbarSlot } from './components/Toolbar';
import { installSegmentThumbs, withViewTransition } from './components/motion';
import { embedded, postToNative, requestedRoute } from './lib/embedded';
import { InspectRoute } from './routes/InspectRoute';
import { DoctorRoute } from './routes/DoctorRoute';
import { QueueRoute } from './routes/QueueRoute';
import { LibraryRoute } from './routes/LibraryRoute';
import { SettingsRoute, type Theme } from './routes/SettingsRoute';
import { StudioRoute } from './routes/StudioRoute';
import { api, type Job } from './lib/api';
import { isActive, useJobs } from './lib/jobs';

type RouteId = 'inspect' | 'download' | 'library' | 'studio' | 'doctor' | 'settings';

const MEDIA: { id: RouteId; icon: SymbolName }[] = [
  { id: 'inspect', icon: 'magnifyingglass' },
  { id: 'download', icon: 'arrow.down.circle' },
  { id: 'library', icon: 'books.vertical' },
  { id: 'studio', icon: 'scissors' },
];
const APP: { id: RouteId; icon: SymbolName }[] = [
  { id: 'doctor', icon: 'stethoscope' },
  { id: 'settings', icon: 'gearshape' },
];
const THEMES: { id: Theme; icon: SymbolName }[] = [
  { id: 'light', icon: 'sun.max.fill' },
  { id: 'dark', icon: 'moon.fill' },
  { id: 'system', icon: 'circle.lefthalf.filled' },
];


function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
}

const ROUTES: RouteId[] = ['inspect', 'download', 'library', 'studio', 'doctor', 'settings'];

function useTheme() {
  // Inside the native app the window follows the system appearance, like every Mac app.
  const [theme, setThemeState] = useState<Theme>(() =>
    embedded ? 'system' : ((localStorage.getItem('vd-theme') as Theme | null) ?? 'system'),
  );
  useEffect(() => {
    applyTheme(theme);
    if (!embedded) localStorage.setItem('vd-theme', theme);
  }, [theme]);
  // The colours change inside the view transition's callback, so the window cross-fades
  // between the old and the new appearance instead of snapping.
  const setTheme = useCallback((next: Theme) => {
    withViewTransition(() => applyTheme(next));
    setThemeState(next);
  }, []);
  return { theme, setTheme };
}

const narrow = () => window.matchMedia?.('(max-width: 720px)').matches ?? false;

export function App() {
  const [route, setRoute] = useState<RouteId>(() =>
    ROUTES.includes(requestedRoute as RouteId) ? (requestedRoute as RouteId) : 'inspect',
  );
  const { theme, setTheme } = useTheme();
  const [sidebar, setSidebar] = useState(() => !narrow());
  const [toolbarSlot, setToolbarSlot] = useState<HTMLElement | null>(null);
  const [libraryVersion, setLibraryVersion] = useState(0);
  const [clipboardUrl, setClipboardUrl] = useState<string | null>(null);
  const [catalogueFailed, setCatalogueFailed] = useState(false);
  const [inspectRequest, setInspectRequest] = useState<{ url: string; n: number } | null>(null);
  const [studioRequest, setStudioRequest] = useState<{ itemId: string; n: number } | null>(null);
  const notifications = useRef(true);

  useEffect(() => installSegmentThumbs(document.body), []);

  // The native window drives navigation (its sidebar, the URL scheme, a dropped link) and
  // follows the page when the page moves on its own ("Stüdyo'da aç", "Kuyruğu aç").
  useEffect(() => {
    if (!embedded) return;
    const bridge = {
      navigate: (next: string) => {
        if (ROUTES.includes(next as RouteId)) setRoute(next as RouteId);
      },
      inspect: (url: string) => {
        setInspectRequest((r) => ({ url, n: (r?.n ?? 0) + 1 }));
        setRoute('inspect');
      },
    };
    (window as unknown as { vd?: typeof bridge }).vd = bridge;
    // From here on the app may drive the page; calls made before this are queued natively.
    postToNative({ type: 'ready' });
  }, []);
  useEffect(() => {
    if (embedded) postToNative({ type: 'route', route });
  }, [route]);

  // Like a Mac window, shrinking below the split-view width collapses the sidebar and widening
  // brings it back; in between the toggle decides.
  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 720px)');
    if (!query) return;
    const onChange = (event: MediaQueryListEvent) => setSidebar(!event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    api
      .settings()
      .then((settings) => (notifications.current = settings.notifications))
      .catch(() => undefined);
  }, []);

  /** A finished or failed download deserves a system notification when the window is in the
   * background; when it is in front, the queue already shows it. */
  const onTransition = useCallback((job: Job, previous: Job | undefined) => {
    // The native app posts its own notifications; two of each would be noise.
    if (embedded || !previous || !notifications.current || document.hasFocus()) return;
    if (job.status === 'done') void api.notify(tr.queue.notifyDone, job.title ?? '').catch(() => undefined);
    if (job.status === 'failed') void api.notify(tr.queue.notifyFailed, job.title ?? '').catch(() => undefined);
  }, []);

  const { jobs, connection } = useJobs({
    onTransition,
    onClipboard: setClipboardUrl,
    onLibrary: () => setLibraryVersion((v) => v + 1),
    onLibraryError: () => setCatalogueFailed(true),
  });
  const active = jobs?.filter(isActive).length ?? 0;

  const go = (id: RouteId) => {
    setRoute(id);
    if (narrow()) setSidebar(false); // on a narrow window the sidebar floats; close it after a choice
  };

  const navItem = (item: { id: RouteId; icon: SymbolName }) => (
    <button
      key={item.id}
      type="button"
      className="nav-item"
      aria-current={route === item.id ? 'page' : undefined}
      onClick={() => go(item.id)}
    >
      <Icon name={item.icon} size={17} />
      <span>{tr.nav[item.id]}</span>
      {item.id === 'download' && active > 0 && (
        <span className="nav-count" data-testid="active-count">
          {tr.queue.activeCount(active)}
        </span>
      )}
    </button>
  );

  return (
    <div className={sidebar ? 'shell' : 'shell sidebar-hidden'}>
      <nav className="sidebar" aria-label={tr.app.name} aria-hidden={!sidebar}>
        <div className="sidebar-brand">{tr.app.brand}</div>
        {MEDIA.map(navItem)}
        <div className="sidebar-brand">{tr.app.systemSection}</div>
        {APP.map(navItem)}
        <div className="sidebar-footer">
          <div className="segmented icons" role="radiogroup" aria-label={tr.app.theme}>
            {THEMES.map((option) => (
              <button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={theme === option.id}
                aria-label={tr.settings.themes[option.id]}
                title={tr.settings.themes[option.id]}
                className={theme === option.id ? 'segment active' : 'segment'}
                onClick={() => setTheme(option.id)}
              >
                <Icon name={option.icon} size={14} />
              </button>
            ))}
          </div>
        </div>
      </nav>
      <main className="main">
        <header className="toolbar">
          <button
            type="button"
            className="btn-icon"
            aria-label={sidebar ? tr.app.hideSidebar : tr.app.showSidebar}
            title={sidebar ? tr.app.hideSidebar : tr.app.showSidebar}
            aria-pressed={sidebar}
            onClick={() => setSidebar((open) => !open)}
          >
            <Icon name="sidebar.left" size={18} />
          </button>
          <h1>{tr.nav[route]}</h1>
          <span className="toolbar-spacer" />
          <div className="toolbar-actions" ref={setToolbarSlot} />
        </header>
        {catalogueFailed && (
          <div className="clipboard-banner" role="alert">
            <Icon name="exclamationmark.triangle.fill" tone="yellow" />
            <span>{tr.library.catalogueFailed}</span>
            <span className="toolbar-spacer" />
            <button type="button" className="btn" onClick={() => setCatalogueFailed(false)}>
              {tr.clipboard.dismiss}
            </button>
          </div>
        )}
        {clipboardUrl && (
          <div className="clipboard-banner" role="status">
            <Icon name="link" className="sf-accent" />
            <span>{tr.clipboard.offer}</span>
            <code className="mono path">{clipboardUrl}</code>
            <span className="toolbar-spacer" />
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setInspectRequest((r) => ({ url: clipboardUrl, n: (r?.n ?? 0) + 1 }));
                setClipboardUrl(null);
                setRoute('inspect');
              }}
            >
              {tr.clipboard.inspect}
            </button>
            <button type="button" className="btn" onClick={() => setClipboardUrl(null)}>
              {tr.clipboard.dismiss}
            </button>
          </div>
        )}
        <ToolbarSlot.Provider value={toolbarSlot}>
          <div className="content">
            {/* Inspect stays mounted so a result survives a trip to another screen and back. */}
            <div hidden={route !== 'inspect'}>
              <InspectRoute
                active={route === 'inspect'}
                onOpenQueue={() => setRoute('download')}
                request={inspectRequest}
              />
            </div>
            {route === 'download' && <QueueRoute jobs={jobs} connection={connection} />}
            {route === 'library' && (
              <LibraryRoute
                refreshKey={libraryVersion}
                onOpenInStudio={(itemId) => {
                  setStudioRequest((r) => ({ itemId, n: (r?.n ?? 0) + 1 }));
                  setRoute('studio');
                }}
              />
            )}
            {route === 'doctor' && <DoctorRoute />}
            {route === 'settings' && (
              <SettingsRoute
                theme={theme}
                setTheme={setTheme}
                onSaved={(settings) => (notifications.current = settings.notifications)}
              />
            )}
            {route === 'studio' && (
              <StudioRoute onOpenQueue={() => setRoute('download')} request={studioRequest} />
            )}
          </div>
        </ToolbarSlot.Provider>
      </main>
    </div>
  );
}
