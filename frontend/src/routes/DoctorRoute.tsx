import { useCallback, useEffect, useState } from 'react';
import { tr } from '../i18n/tr';
import { ApiError, api, type DoctorCheck, type DoctorReport } from '../lib/api';
import { Badge, CopyButton, ErrorState, LoadingState, Notice, Panel, Term } from '../components/ui';

type State =
  | { phase: 'loading' }
  | { phase: 'error'; code: string; raw: string }
  | { phase: 'ready'; report: DoctorReport };

function Capabilities({ capabilities }: { capabilities: Record<string, boolean> }) {
  const labels = tr.doctor.capabilities as Record<string, string>;
  return (
    <div className="cap-grid">
      {Object.entries(capabilities).map(([key, available]) => (
        <div key={key}>
          <span style={{ color: available ? 'var(--ok)' : 'var(--text-tertiary)' }}>
            {available ? '✓' : '✕'}
          </span>{' '}
          <span className={available ? '' : 'dim'}>{labels[key] ?? key}</span>
        </div>
      ))}
    </div>
  );
}

function UpdateYtdlp({ onDone }: { onDone: () => void }) {
  const [state, setState] = useState<
    { phase: 'idle' } | { phase: 'running' } | { phase: 'done'; text: string } | { phase: 'error'; code: string; raw: string }
  >({ phase: 'idle' });
  const run = async () => {
    setState({ phase: 'running' });
    try {
      const result = await api.updateYtdlp();
      setState({
        phase: 'done',
        text: result.changed
          ? tr.doctor.updated(result.before.version, result.after.version)
          : tr.doctor.upToDate(result.after.version),
      });
      onDone();
    } catch (error) {
      const failure = error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error));
      setState({ phase: 'error', code: failure.code, raw: failure.raw });
    }
  };
  return (
    <div className="update-row">
      <button type="button" className="btn" disabled={state.phase === 'running'} onClick={() => void run()}>
        {state.phase === 'running' ? tr.doctor.updating : tr.doctor.updateYtdlp}
      </button>
      <span className="dim">{tr.doctor.updateHelp}</span>
      {state.phase === 'done' && <Notice>{state.text}</Notice>}
      {state.phase === 'error' && <ErrorState code={state.code} raw={state.raw} />}
    </div>
  );
}

function CheckRow({ check, onReload }: { check: DoctorCheck; onReload: () => void }) {
  const names = tr.doctor.checks as Record<string, string>;
  const help = tr.doctor.checkHelp as Record<string, string>;
  const labels = tr.doctor.labels as Record<string, string>;
  const explained = tr.doctor.missingExplained as Record<string, string>;
  const values = check.values;
  const capabilities = values.capabilities as Record<string, boolean> | undefined;
  const found = values.found as { name: string; version: string; path: string }[] | undefined;
  const missing = (values.missing_optional as string[] | undefined) ?? [];

  return (
    <div className="check-row">
      <span className={`check-dot ${check.status}`} aria-hidden="true" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div>
          <strong>
            <Term label={names[check.id] ?? check.id} body={help[check.id] ?? ''} />
          </strong>{' '}
          {check.status === 'ok' && <Badge tone="ok">{tr.doctor.checkOk}</Badge>}
          {check.status === 'warn' && <Badge tone="warn">{tr.doctor.checkWarn}</Badge>}
          {check.status === 'error' && <Badge tone="danger">{tr.doctor.checkError}</Badge>}
        </div>
        <div className="kv muted mono">
          {Object.entries(values)
            .filter(([key]) => !['capabilities', 'found', 'missing_optional'].includes(key))
            .map(([key, value]) => (
              <span key={key} style={{ display: 'contents' }}>
                <span className="dim">{labels[key] ?? key}</span>
                <span>{String(value ?? '–')}</span>
              </span>
            ))}
          {found?.map((runtime) => (
            <span key={runtime.name} style={{ display: 'contents' }}>
              <span className="dim">{runtime.name}</span>
              <span>{runtime.version}</span>
            </span>
          ))}
        </div>
        {capabilities && <Capabilities capabilities={capabilities} />}
        {missing.map((key) => (
          <div style={{ marginTop: 'var(--space-2)' }} key={key}>
            <Notice tone="warn">{explained[key] ?? key}</Notice>
          </div>
        ))}
        {check.id === 'yt_dlp' && <UpdateYtdlp onDone={onReload} />}
        {check.status !== 'ok' && check.fix.kind === 'command' && (
          <div style={{ marginTop: 'var(--space-2)' }}>
            <div className="muted">{tr.doctor.fixHint}</div>
            <div className="cmd">
              <code className="mono">{check.fix.command}</code>
              <CopyButton value={check.fix.command} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function DoctorRoute() {
  const [state, setState] = useState<State>({ phase: 'loading' });

  // A refresh after an update keeps the report on screen (and the update message with it).
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setState({ phase: 'loading' });
    try {
      setState({ phase: 'ready', report: await api.doctor() });
    } catch (error) {
      const failure = error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error));
      setState({ phase: 'error', code: failure.code, raw: failure.raw });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="content-inner">
      <Panel
        title={tr.doctor.title}
        actions={
          <button type="button" className="btn" onClick={() => void load()}>
            {tr.doctor.refresh}
          </button>
        }
        flush
      >
        <div style={{ padding: 'var(--space-3) var(--space-4)' }} className="muted">
          {tr.doctor.subtitle}
        </div>
        {state.phase === 'loading' && <LoadingState title={tr.doctor.title} body={tr.doctor.subtitle} />}
        {state.phase === 'error' && (
          <ErrorState code={state.code} raw={state.raw} onRetry={() => void load()} />
        )}
        {state.phase === 'ready' &&
          state.report.checks.map((check) => (
            <CheckRow key={check.id} check={check} onReload={() => void load(true)} />
          ))}
      </Panel>
    </div>
  );
}
