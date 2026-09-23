import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { tr } from '../i18n/tr';

export function Panel({
  title,
  count,
  actions,
  flush,
  children,
}: {
  title: string;
  count?: number;
  actions?: ReactNode;
  flush?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {count !== undefined && <span className="panel-count">{count}</span>}
        <span className="toolbar-spacer" />
        {actions}
      </header>
      <div className={flush ? 'panel-body flush' : 'panel-body'}>{children}</div>
    </section>
  );
}

/** Every technical term in the UI can explain itself. Keyboard and pointer both work. */
export function Term({ label, body }: { label: string; body: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span
      className="term"
      tabIndex={0}
      aria-describedby={open ? id : undefined}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => event.key === 'Escape' && setOpen(false)}
    >
      {label}
      {open && (
        <span className="term-bubble" role="tooltip" id={id}>
          {body}
        </span>
      )}
    </span>
  );
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'accent' | 'ok' | 'warn' | 'danger';
}) {
  return <span className={tone === 'neutral' ? 'badge' : `badge badge-${tone}`}>{children}</span>;
}

export function EmptyState({ glyph, title, body }: { glyph: string; title: string; body: string }) {
  return (
    <div className="state">
      <div className="state-glyph" aria-hidden="true">
        {glyph}
      </div>
      <div className="state-title">{title}</div>
      <div>{body}</div>
    </div>
  );
}

export function LoadingState({ title, body }: { title: string; body: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <div className="state-glyph">
        <span className="spinner" />
      </div>
      <div className="state-title">{title}</div>
      <div>{body}</div>
    </div>
  );
}

export function ErrorState({
  code,
  raw,
  onRetry,
}: {
  code: string;
  raw: string;
  onRetry?: () => void;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const table = tr.errors as Record<string, { title: string; body: string }>;
  const copy = table[code] ?? tr.errors.UNKNOWN;
  return (
    <div className="state" role="alert">
      <div className="state-glyph" aria-hidden="true">
        ⚠︎
      </div>
      <div className="state-title">{copy.title}</div>
      <div>{copy.body}</div>
      <div style={{ marginTop: 'var(--space-3)', display: 'flex', gap: 8, justifyContent: 'center' }}>
        {onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            {tr.app.retry}
          </button>
        )}
        {raw && (
          <button type="button" className="btn btn-quiet" onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? tr.app.hideDetails : tr.app.showDetails}
          </button>
        )}
      </div>
      {showRaw && raw && (
        <pre className="mono muted" style={{ textAlign: 'left', whiteSpace: 'pre-wrap', marginTop: 12 }}>
          {raw}
        </pre>
      )}
    </div>
  );
}

export function CopyButton({ value, label }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);
  return (
    <button
      type="button"
      className="btn"
      onClick={() => {
        void navigator.clipboard?.writeText(value);
        setDone(true);
        timer.current = setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? tr.app.copied : (label ?? tr.app.copy)}
    </button>
  );
}

/** Native <dialog>: focus is trapped, Esc cancels, and the safe choice has initial focus. */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel,
  danger,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog ref={ref} className="confirm" onCancel={onCancel} aria-labelledby="confirm-title">
      <h2 id="confirm-title">{title}</h2>
      <p className="muted">{body}</p>
      <div className="confirm-actions">
        <button type="button" className="btn" onClick={onCancel} autoFocus>
          {cancelLabel}
        </button>
        <button
          type="button"
          className={danger ? 'btn btn-danger' : 'btn btn-primary'}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

export function Notice({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'warn' | 'danger';
  children: ReactNode;
}) {
  return <div className={tone === 'neutral' ? 'notice' : `notice notice-${tone}`}>{children}</div>;
}
