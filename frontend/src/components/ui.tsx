import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { tr } from '../i18n/tr';
import { Icon, type SymbolName } from './Icon';

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

/**
 * Every technical term in the UI can explain itself. Keyboard and pointer both work.
 * Like a macOS help tag, the bubble floats above the window (a portal with fixed position), so no
 * scrolling or clipped container can cut it off; it opens below the term, or above when there
 * is no room, and never leaves the viewport.
 */
export function Term({ label, body }: { label: string; body: string }) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<{ left: number; top: number; above: boolean } | null>(null);
  const anchor = useRef<HTMLSpanElement>(null);
  const bubble = useRef<HTMLSpanElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const id = useId();

  const show = (delay: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    setOpen(false);
    setPlace(null);
  };

  useLayoutEffect(() => {
    if (!open || !anchor.current || !bubble.current) return;
    const term = anchor.current.getBoundingClientRect();
    const tip = bubble.current.getBoundingClientRect();
    const margin = 8;
    const gap = 6;
    const fitsBelow = term.bottom + gap + tip.height <= window.innerHeight - margin;
    setPlace({
      left: Math.max(margin, Math.min(term.left, window.innerWidth - tip.width - margin)),
      top: fitsBelow ? term.bottom + gap : Math.max(margin, term.top - gap - tip.height),
      above: !fitsBelow,
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    // A help tag belongs to a spot on screen; once the page moves under it, it goes away.
    const close = () => hide();
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <span
      ref={anchor}
      className="term"
      tabIndex={0}
      aria-describedby={open ? id : undefined}
      onMouseEnter={() => show(250)}
      onMouseLeave={hide}
      onFocus={() => show(0)}
      onBlur={hide}
      onKeyDown={(event) => event.key === 'Escape' && hide()}
    >
      {label}
      {open &&
        createPortal(
          <span
            ref={bubble}
            className={place ? `term-bubble shown${place.above ? ' above' : ''}` : 'term-bubble'}
            role="tooltip"
            id={id}
            style={place ? { left: place.left, top: place.top } : undefined}
          >
            {body}
          </span>,
          document.body,
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

/** ContentUnavailableView: a large quiet symbol, a title, one sentence of direction. */
export function EmptyState({ icon, title, body }: { icon: SymbolName; title: string; body: string }) {
  return (
    <div className="state">
      <div className="state-glyph">
        <Icon name={icon} size={40} />
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
      <div className="state-glyph">
        <Icon name="exclamationmark.triangle.fill" size={40} tone="yellow" />
      </div>
      <div className="state-title">{copy.title}</div>
      <div>{copy.body}</div>
      <div style={{ marginTop: 'var(--s3)', display: 'flex', gap: 8, justifyContent: 'center' }}>
        {onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            <Icon name="arrow.clockwise" size={14} />
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
      <Icon name={done ? 'checkmark' : 'doc.on.doc'} size={14} />
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
      <div className="confirm-icon">
        <Icon name={danger ? 'trash' : 'info.circle'} size={40} />
      </div>
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
  const icon: SymbolName =
    tone === 'danger' ? 'xmark.octagon.fill' : tone === 'warn' ? 'exclamationmark.triangle.fill' : 'info.circle';
  return (
    <div className={tone === 'neutral' ? 'notice' : `notice notice-${tone}`}>
      <Icon name={icon} size={15} />
      <div className="notice-body">{children}</div>
    </div>
  );
}
