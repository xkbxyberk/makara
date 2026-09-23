import { useCallback, useEffect, useState } from 'react';
import './theme.css';
import { tr } from './i18n/tr';
import { EmptyState, Panel } from './components/ui';
import { InspectRoute } from './routes/InspectRoute';
import { DoctorRoute } from './routes/DoctorRoute';

type RouteId = 'inspect' | 'download' | 'library' | 'studio' | 'doctor' | 'settings';

const NAV: { id: RouteId; ready: boolean }[] = [
  { id: 'inspect', ready: true },
  { id: 'download', ready: false },
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

export function App() {
  const [route, setRoute] = useState<RouteId>('inspect');
  const [, isDark, toggleTheme] = useTheme();

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
          {route === 'inspect' && <InspectRoute />}
          {route === 'doctor' && <DoctorRoute />}
          {route !== 'inspect' && route !== 'doctor' && (
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
