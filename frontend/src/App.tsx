import { useCallback, useEffect, useState } from 'react';
import './theme.css';
import { tr } from './i18n/tr';
import { EmptyState, Panel } from './components/ui';
import { InspectRoute } from './routes/InspectRoute';
import { DoctorRoute } from './routes/DoctorRoute';
import { QueueRoute } from './routes/QueueRoute';
import { api, type Job } from './lib/api';
import { isActive, useJobs } from './lib/jobs';

type RouteId = 'inspect' | 'download' | 'library' | 'studio' | 'doctor' | 'settings';

const NAV: { id: RouteId; ready: boolean }[] = [
  { id: 'inspect', ready: true },
  { id: 'download', ready: true },
  { id: 'library', ready: false },
  { id: 'studio', ready: false },
  { id: 'doctor', ready: true },
  { id: 'settings', ready: false },
];

type Theme = 'system' | 'light' | 'dark';

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

function useTheme(): [Theme, boolean, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('vd-theme') as Theme | null) ?? 'system',
  );
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    localStorage.setItem('vd-theme', theme);
  }, [theme]);
  const effectiveDark = theme === 'dark' || (theme === 'system' && systemPrefersDark());
  const toggle = useCallback(
    () => setTheme(() => (effectiveDark ? 'light' : 'dark')),
    [effectiveDark],
  );
  return [theme, effectiveDark, toggle];
}

/** A finished or failed download deserves a system notification when the window is in the
 * background; when it is in front, the queue already shows it. */
function notifyTransition(job: Job, previous: Job | undefined) {
  if (!previous || document.hasFocus()) return;
  if (job.status === 'done') void api.notify(tr.queue.notifyDone, job.title ?? '').catch(() => undefined);
  if (job.status === 'failed') void api.notify(tr.queue.notifyFailed, job.title ?? '').catch(() => undefined);
}

export function App() {
  const [route, setRoute] = useState<RouteId>('inspect');
  const [, isDark, toggleTheme] = useTheme();
  const { jobs, connection } = useJobs(notifyTransition);
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
          <button type="button" className="btn" onClick={toggleTheme} aria-label={tr.app.themeToggle}>
            {isDark ? tr.app.themeLight : tr.app.themeDark}
          </button>
        </div>
      </nav>
      <main className="main">
        <header className="toolbar">
          <h1>{tr.nav[route]}</h1>
          <span className="toolbar-spacer" />
        </header>
        <div className="content">
          {/* Inspect stays mounted so a result survives a trip to the queue and back. */}
          <div hidden={route !== 'inspect'}>
            <InspectRoute onOpenQueue={() => setRoute('download')} />
          </div>
          {route === 'download' && <QueueRoute jobs={jobs} connection={connection} />}
          {route === 'doctor' && <DoctorRoute />}
          {(route === 'library' || route === 'studio' || route === 'settings') && (
            <div className="content-inner">
              <Panel title={tr.nav[route]}>
                <EmptyState
                  glyph="→"
                  title={tr.placeholder.title(tr.nav[route])}
                  body={tr.placeholder.body}
                />
              </Panel>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
