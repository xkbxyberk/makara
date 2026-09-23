import { useCallback, useEffect, useRef, useState } from 'react';
import './theme.css';
import { tr } from './i18n/tr';
import { EmptyState, Panel } from './components/ui';
import { InspectRoute } from './routes/InspectRoute';
import { DoctorRoute } from './routes/DoctorRoute';
import { QueueRoute } from './routes/QueueRoute';
import { LibraryRoute } from './routes/LibraryRoute';
import { SettingsRoute, type Theme } from './routes/SettingsRoute';
import { api, type Job } from './lib/api';
import { isActive, useJobs } from './lib/jobs';

type RouteId = 'inspect' | 'download' | 'library' | 'studio' | 'doctor' | 'settings';

const NAV: { id: RouteId; ready: boolean }[] = [
  { id: 'inspect', ready: true },
  { id: 'download', ready: true },
  { id: 'library', ready: true },
  { id: 'studio', ready: false },
  { id: 'doctor', ready: true },
  { id: 'settings', ready: true },
];

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('vd-theme') as Theme | null) ?? 'system',
  );
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    localStorage.setItem('vd-theme', theme);
  }, [theme]);
  const isDark = theme === 'dark' || (theme === 'system' && systemPrefersDark());
  const toggle = useCallback(() => setTheme(isDark ? 'light' : 'dark'), [isDark]);
  return { theme, setTheme, isDark, toggle };
}

export function App() {
  const [route, setRoute] = useState<RouteId>('inspect');
  const { theme, setTheme, isDark, toggle } = useTheme();
  const [libraryVersion, setLibraryVersion] = useState(0);
  const [clipboardUrl, setClipboardUrl] = useState<string | null>(null);
  const [inspectRequest, setInspectRequest] = useState<{ url: string; n: number } | null>(null);
  const notifications = useRef(true);

  useEffect(() => {
    api
      .settings()
      .then((settings) => (notifications.current = settings.notifications))
      .catch(() => undefined);
  }, []);

  /** A finished or failed download deserves a system notification when the window is in the
   * background; when it is in front, the queue already shows it. */
  const onTransition = useCallback((job: Job, previous: Job | undefined) => {
    if (!previous || !notifications.current || document.hasFocus()) return;
    if (job.status === 'done') void api.notify(tr.queue.notifyDone, job.title ?? '').catch(() => undefined);
    if (job.status === 'failed') void api.notify(tr.queue.notifyFailed, job.title ?? '').catch(() => undefined);
  }, []);

  const { jobs, connection } = useJobs({
    onTransition,
    onClipboard: setClipboardUrl,
    onLibrary: () => setLibraryVersion((v) => v + 1),
  });
  const active = jobs?.filter(isActive).length ?? 0;

  return (
    <div className="shell">
      <nav className="sidebar" aria-label={tr.app.name}>
        <div className="sidebar-brand">{tr.app.brand}</div>
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className="nav-item"
            aria-current={route === item.id ? 'page' : undefined}
            disabled={!item.ready}
            onClick={() => setRoute(item.id)}
          >
            {tr.nav[item.id]}
            {!item.ready && <span className="dim"> · {tr.app.soon}</span>}
            {item.id === 'download' && active > 0 && (
              <span className="nav-count" data-testid="active-count">
                {tr.queue.activeCount(active)}
              </span>
            )}
          </button>
        ))}
        <div className="sidebar-footer">
          <button type="button" className="btn" onClick={toggle} aria-label={tr.app.themeToggle}>
            {isDark ? tr.app.themeLight : tr.app.themeDark}
          </button>
        </div>
      </nav>
      <main className="main">
        <header className="toolbar">
          <h1>{tr.nav[route]}</h1>
          <span className="toolbar-spacer" />
        </header>
        {clipboardUrl && (
          <div className="clipboard-banner" role="status">
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
          {route === 'library' && <LibraryRoute refreshKey={libraryVersion} />}
          {route === 'doctor' && <DoctorRoute />}
          {route === 'settings' && (
            <SettingsRoute
              theme={theme}
              setTheme={setTheme}
              onSaved={(settings) => (notifications.current = settings.notifications)}
            />
          )}
          {route === 'studio' && (
            <div className="content-inner">
              <Panel title={tr.nav[route]}>
                <EmptyState glyph="→" title={tr.placeholder.title(tr.nav[route])} body={tr.placeholder.body} />
              </Panel>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
