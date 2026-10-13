import { useCallback, useEffect, useState } from 'react';
import { tr } from '../i18n/tr';
import { ApiError, api, type DoctorCheck, type DoctorReport } from '../lib/api';
import { Badge, CopyButton, ErrorState, LoadingState, Notice, Panel, Term } from '../components/ui';
import { Icon } from '../components/Icon';
import { ToolbarItems } from '../components/Toolbar';

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
          <Icon name={available ? 'checkmark.circle.fill' : 'xmark.circle'} tone={available ? 'green' : 'secondary'} size={14} />
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
        {state.phase === 'running' ? <span className="spinner" /> : <Icon name="arrow.down.circle" size={14} />}
        {state.phase === 'running' ? tr.doctor.updating : tr.doctor.updateYtdlp}
      </button>
      <span className="dim">{tr.doctor.updateHelp}</span>
      {state.phase === 'done' && <Notice>{state.text}</Notice>}
      {state.phase === 'error' && <ErrorState code={state.code} raw={state.raw} />}
    </div>
  );
}

/** What the Safari session means for age-restricted videos, and the one step that fixes it. */
function SafariSession({ state, fix }: { state: string; fix: string }) {
  const [failed, setFailed] = useState<string | null>(null);
  const text = tr.doctor.sessionStates[state];
  return (
    <div style={{ marginTop: 'var(--s2)', display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
      {text && <Notice tone={state === 'signed_in' || state === 'off' || state === 'unknown' ? 'neutral' : 'warn'}>{text}</Notice>}
      {fix === 'full_disk_access' && (
        <div>
          <button
            type="button"
            className="btn"
            onClick={() =>
              void api.openFullDiskAccess().catch((error: unknown) => setFailed(error instanceof ApiError ? error.code : 'UNKNOWN'))
            }
          >
            <Icon name="gearshape" size={14} />
            {tr.doctor.openFullDiskAccess}
          </button>
        </div>
      )}
      {failed && <ErrorState code={failed} raw="" />}
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
      <Icon
        name={check.status === 'ok' ? 'checkmark.circle.fill' : check.status === 'warn' ? 'exclamationmark.triangle.fill' : 'xmark.octagon.fill'}
        tone={check.status === 'ok' ? 'green' : check.status === 'warn' ? 'yellow' : 'red'}
        size={22}
      />
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
            .filter(([key]) => !['capabilities', 'found', 'missing_optional', 'state'].includes(key))
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
          <div style={{ marginTop: 'var(--s2)' }} key={key}>
            <Notice tone="warn">{explained[key] ?? key}</Notice>
          </div>
        ))}
        {check.id === 'yt_dlp' && <UpdateYtdlp onDone={onReload} />}
        {check.id === 'safari_session' && <SafariSession state={String(values.state ?? '')} fix={check.fix.kind} />}
        {check.status !== 'ok' && check.fix.kind === 'command' && (
          <div style={{ marginTop: 'var(--s2)' }}>
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
      <ToolbarItems>
        <button
          type="button"
          className="btn-icon"
          aria-label={tr.doctor.refresh}
          title={tr.doctor.refresh}
          onClick={() => void load()}
        >
          <Icon name="arrow.clockwise" size={17} />
        </button>
      </ToolbarItems>
      <Panel title={tr.doctor.title} flush>
        <div style={{ padding: 'var(--s3) var(--s4)' }} className="muted">
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
