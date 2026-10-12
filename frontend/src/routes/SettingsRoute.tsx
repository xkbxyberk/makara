import { useEffect, useRef, useState } from 'react';
import { tr } from '../i18n/tr';
import { ApiError, api, type Mode, type Settings } from '../lib/api';
import { ErrorState, LoadingState, Notice, Panel, Term } from '../components/ui';
import { Icon, type SymbolName } from '../components/Icon';
import { embedded } from '../lib/embedded';

export type Theme = 'system' | 'light' | 'dark';
const MODES: Mode[] = ['mkv', 'compat_mp4', 'separate', 'audio'];
const THEMES: Theme[] = ['system', 'light', 'dark'];
const THEME_ICONS: Record<string, SymbolName> = {
  system: 'circle.lefthalf.filled',
  light: 'sun.max.fill',
  dark: 'moon.fill',
};

type State =
  | { phase: 'loading' }
  | { phase: 'error'; code: string; raw: string }
  | { phase: 'ready'; saved: Settings; draft: Settings };

function Segmented<T extends string>({
  label,
  value,
  options,
  labels,
  icons,
  onChange,
}: {
  label: string;
  value: T;
  options: T[];
  labels: Record<string, string>;
  icons?: Record<string, SymbolName>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={value === option}
          className={value === option ? 'segment active' : 'segment'}
          onClick={() => onChange(option)}
        >
          {icons?.[option] && <Icon name={icons[option]} size={13} />}
          {labels[option]}
        </button>
      ))}
    </div>
  );
}

export function SettingsRoute({
  theme,
  setTheme,
  onSaved,
}: {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  onSaved: (settings: Settings) => void;
}) {
  const [state, setState] = useState<State>({ phase: 'loading' });
  const [preview, setPreview] = useState<{ filename?: string; error?: string }>({});
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const [defaultTemplate, setDefaultTemplate] = useState('');
  const previewTicket = useRef(0);

  const load = () => {
    setState({ phase: 'loading' });
    api
      .settings()
      .then((settings) => {
        setState({ phase: 'ready', saved: settings, draft: settings });
        setDefaultTemplate(settings.default_filename_template ?? settings.filename_template);
      })
      .catch((error: unknown) => {
        const f = error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error));
        setState({ phase: 'error', code: f.code, raw: f.raw });
      });
  };
  useEffect(load, []);

  const draft = state.phase === 'ready' ? state.draft : null;
  const template = draft?.filename_template;

  useEffect(() => {
    if (!template) return;
    const ticket = ++previewTicket.current;
    const timer = setTimeout(() => {
      api
        .previewTemplate(template, tr.settings.sample)
        .then((result) => ticket === previewTicket.current && setPreview({ filename: result.filename }))
        .catch(
          (error: unknown) =>
            ticket === previewTicket.current &&
            setPreview({ error: error instanceof ApiError ? error.code : 'UNKNOWN' }),
        );
    }, 150);
    return () => clearTimeout(timer);
  }, [template]);

  if (state.phase === 'loading') {
    return (
      <div className="content-inner">
        <Panel title={tr.settings.title}>
          <LoadingState title={tr.settings.loading} body="" />
        </Panel>
      </div>
    );
  }
  if (state.phase === 'error') {
    return (
      <div className="content-inner">
        <Panel title={tr.settings.title}>
          <ErrorState code={state.code} raw={state.raw} onRetry={load} />
        </Panel>
      </div>
    );
  }

  const { saved } = state;
  // Functional updates: a folder picked (or a save finishing) after further edits must not
  // overwrite those edits with a stale copy of the form.
  const edit = (patch: Partial<Settings>) => {
    setJustSaved(false);
    setState((current) =>
      current.phase === 'ready' ? { ...current, draft: { ...current.draft, ...patch } } : current,
    );
  };
  const dirty = JSON.stringify(saved) !== JSON.stringify(state.draft);

  const save = async () => {
    setFailure(null);
    const submitted = state.draft;
    try {
      const stored = await api.saveSettings(submitted);
      setState((current) =>
        current.phase === 'ready'
          ? {
              phase: 'ready',
              saved: stored,
              // Keep anything typed while the save was in flight.
              draft: JSON.stringify(current.draft) === JSON.stringify(submitted) ? stored : current.draft,
            }
          : current,
      );
      setJustSaved(true);
      onSaved(stored);
    } catch (error) {
      setFailure(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error)));
    }
  };

  const chooseFolder = async () => {
    setFailure(null);
    try {
      const { path } = await api.pickFolder(tr.settings.choosePrompt);
      if (path) edit({ download_dir: path });
    } catch (error) {
      setFailure(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error)));
    }
  };

  return (
    <div className="content-inner">
      <Panel title={tr.settings.title}>
        <form
          className="settings"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="setting">
            <label htmlFor="download-dir">{tr.settings.downloadDir}</label>
            <div className="pick-inline">
              <input
                id="download-dir"
                className="input mono"
                value={state.draft.download_dir}
                spellCheck={false}
                onChange={(event) => edit({ download_dir: event.target.value })}
              />
              <button type="button" className="btn" onClick={() => void chooseFolder()}>
                <Icon name="folder" size={14} />
                {tr.settings.chooseFolder}
              </button>
            </div>
            <p className="dim">{tr.settings.downloadDirHelp}</p>
          </div>

          <div className="setting">
            <label htmlFor="template">
              <Term label={tr.settings.template} body={tr.download.templateHelp} />
            </label>
            <div className="pick-inline">
              <input
                id="template"
                className="input mono"
                value={state.draft.filename_template}
                spellCheck={false}
                onChange={(event) => edit({ filename_template: event.target.value })}
              />
              <button
                type="button"
                className="btn"
                disabled={!defaultTemplate}
                onClick={() => edit({ filename_template: defaultTemplate })}
              >
                {tr.settings.templateReset}
              </button>
            </div>
            <p className="mono muted path" data-testid="template-preview">
              {tr.settings.templatePreview}:{' '}
              {preview.error ? (
                <span className="danger-text">
                  {(tr.errors as Record<string, { title: string }>)[preview.error]?.title ?? preview.error}
                </span>
              ) : (
                preview.filename
              )}
            </p>
          </div>

          <div className="setting">
            <label htmlFor="concurrency">
              <Term label={tr.settings.concurrency} body={tr.settings.concurrencyHelp} />
            </label>
            <input
              id="concurrency"
              className="input narrow"
              type="number"
              min={1}
              max={6}
              value={state.draft.concurrency}
              onChange={(event) => edit({ concurrency: Math.max(1, Math.min(6, Number(event.target.value) || 1)) })}
            />
          </div>

          <div className="setting">
            <span className="setting-label">{tr.settings.defaultMode}</span>
            <Segmented
              label={tr.settings.defaultMode}
              value={state.draft.default_mode}
              options={MODES}
              labels={tr.download.modes}
              onChange={(mode) => edit({ default_mode: mode })}
            />
          </div>

          {/* The native app follows the system appearance; the choice exists only in a browser. */}
          {!embedded && (
            <div className="setting">
              <span className="setting-label">{tr.settings.theme}</span>
              <Segmented label={tr.settings.theme} value={theme} options={THEMES} labels={tr.settings.themes} icons={THEME_ICONS} onChange={setTheme} />
            </div>
          )}

          <label className="setting setting-toggle">
            <input
              type="checkbox"
              checked={state.draft.clipboard_watch}
              onChange={(event) => edit({ clipboard_watch: event.target.checked })}
            />
            <span>
              <strong>{tr.settings.clipboard}</strong>
              <span className="dim"> — {tr.settings.clipboardHelp}</span>
            </span>
          </label>

          <label className="setting setting-toggle">
            <input
              type="checkbox"
              checked={state.draft.notifications}
              onChange={(event) => edit({ notifications: event.target.checked })}
            />
            <span>
              <strong>{tr.settings.notifications}</strong>
              <span className="dim"> — {tr.settings.notificationsHelp}</span>
            </span>
          </label>

          {failure && <ErrorState code={failure.code} raw={failure.raw} />}
          <div className="download-actions">
            {dirty && <span className="muted">{tr.settings.unsaved}</span>}
            {justSaved && !dirty && <Notice>{tr.settings.saved}</Notice>}
            <span className="toolbar-spacer" />
            <button type="submit" className="btn btn-primary" disabled={!dirty}>
              {tr.settings.save}
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
