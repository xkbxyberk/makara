import { useCallback, useEffect, useRef, useState } from 'react';
import { tr } from '../i18n/tr';
import {
  ApiError,
  api,
  type LibraryItem,
  type LibraryPage,
  type LibraryQuery,
  type ScanResult,
} from '../lib/api';
import { formatBytes, formatDuration, formatUploadDate, languageName } from '../lib/format';
import {
  Badge,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  Panel,
  Term,
} from '../components/ui';

type View = 'grid' | 'list';
type State =
  | { phase: 'loading' }
  | { phase: 'error'; code: string; raw: string }
  | { phase: 'ready'; page: LibraryPage };

const EMPTY_QUERY: LibraryQuery = { search: '', site: '', kind: '', status: '', sort: 'added' };

function languages(tracks: { language: string | null }[]): string {
  const names = [...new Set(tracks.map((t) => t.language).filter((l): l is string => !!l))];
  return names.length ? names.map(languageName).join(', ') : tr.library.noTracks;
}

function Thumb({ item }: { item: LibraryItem }) {
  const [failed, setFailed] = useState(false);
  if (!item.thumbnail || failed) {
    return (
      <div className="lib-thumb lib-thumb-empty" aria-hidden="true">
        {item.kind === 'audio' ? '♪' : '▶'}
      </div>
    );
  }
  return (
    <img
      className="lib-thumb"
      src={api.thumbnailUrl(item.id)}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

function MissingBadge() {
  return (
    <Badge tone="warn">
      <Term label={tr.library.missing} body={tr.library.missingHelp} />
    </Badge>
  );
}

function Actions({
  item,
  onTrash,
  onError,
  withTrash = true,
}: {
  item: LibraryItem;
  onTrash: (item: LibraryItem) => void;
  onError: (code: string) => void;
  /** The destructive action appears only once an item is opened, never on every row. */
  withTrash?: boolean;
}) {
  const run = (action: () => Promise<unknown>) => () =>
    void action().catch((error: unknown) => onError(error instanceof ApiError ? error.code : 'UNKNOWN'));
  const missing = item.status === 'missing';
  return (
    <div className="lib-actions">
      <button
        type="button"
        className="btn btn-primary"
        disabled={missing}
        title={tr.library.playHelp}
        onClick={run(() => api.openItem(item.id))}
      >
        {tr.library.play}
      </button>
      <button type="button" className="btn" disabled={missing} onClick={run(() => api.revealItem(item.id))}>
        {tr.library.reveal}
      </button>
      {withTrash && (
        <button
          type="button"
          className="btn btn-quiet danger-text"
          disabled={missing}
          onClick={() => onTrash(item)}
        >
          {tr.library.trash}
        </button>
      )}
    </div>
  );
}

function Details({ item }: { item: LibraryItem }) {
  const video = item.tracks.video[0];
  return (
    <dl className="facts lib-details">
      {video && (
        <>
          <dt>{tr.library.video}</dt>
          <dd>
            {video.height ? `${video.height}p · ` : ''}
            {video.codec?.toUpperCase()}
          </dd>
        </>
      )}
      <dt>{tr.library.audioTracks}</dt>
      <dd>{languages(item.tracks.audio)}</dd>
      <dt>{tr.library.subtitleTracks}</dt>
      <dd>{languages(item.tracks.subtitle)}</dd>
      <dt>{tr.library.files}</dt>
      <dd className="mono path">
        {item.files.map((file) => (
          <div key={file.path}>{file.path}</div>
        ))}
      </dd>
      {item.source_url && (
        <>
          <dt>{tr.library.source}</dt>
          <dd className="mono path">{item.source_url}</dd>
        </>
      )}
      <dt>{tr.library.added}</dt>
      <dd>{new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(item.added_at * 1000)}</dd>
    </dl>
  );
}

export function LibraryRoute({ refreshKey }: { refreshKey: number }) {
  const [query, setQuery] = useState<LibraryQuery>(EMPTY_QUERY);
  const [view, setView] = useState<View>(() => (localStorage.getItem('vd-library-view') as View) || 'grid');
  const [state, setState] = useState<State>({ phase: 'loading' });
  const [selected, setSelected] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<LibraryItem | null>(null);
  const [scan, setScan] = useState<ScanResult | 'running' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const ticket = useRef(0);

  const load = useCallback(async (q: LibraryQuery) => {
    const mine = ++ticket.current;
    try {
      const page = await api.library(q);
      if (mine === ticket.current) setState({ phase: 'ready', page });
    } catch (error) {
      if (mine !== ticket.current) return;
      const failure = error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error));
      setState({ phase: 'error', code: failure.code, raw: failure.raw });
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(query), query.search ? 150 : 0);
    return () => clearTimeout(timer);
  }, [query, load, refreshKey]);

  useEffect(() => localStorage.setItem('vd-library-view', view), [view]);

  const runScan = async () => {
    setScan('running');
    try {
      setScan(await api.scanLibrary());
      await load(query);
    } catch (error) {
      setScan(null);
      setActionError(error instanceof ApiError ? error.code : 'UNKNOWN');
    }
  };

  const confirmTrash = async () => {
    const item = confirming;
    setConfirming(null);
    if (!item) return;
    try {
      await api.trashItem(item.id);
      setSelected(null);
      await load(query);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.code : 'UNKNOWN');
    }
  };

  const set = (patch: Partial<LibraryQuery>) => setQuery((q) => ({ ...q, ...patch }));
  const page = state.phase === 'ready' ? state.page : null;
  const filtered = JSON.stringify(query) !== JSON.stringify(EMPTY_QUERY);

  return (
    <div className="content-inner">
      <div className="lib-toolbar">
        <input
          className="input"
          type="search"
          value={query.search}
          placeholder={tr.library.search}
          aria-label={tr.library.search}
          onChange={(event) => set({ search: event.target.value })}
        />
        <select
          className="input select"
          aria-label={tr.library.siteLabel}
          value={query.site}
          onChange={(event) => set({ site: event.target.value })}
        >
          <option value="">{tr.library.allSites}</option>
          {page?.facets.sites.map((site) => (
            <option key={site} value={site}>
              {site}
            </option>
          ))}
        </select>
        <select
          className="input select"
          aria-label={tr.library.kindLabel}
          value={query.kind}
          onChange={(event) => set({ kind: event.target.value })}
        >
          {Object.entries(tr.library.kinds).map(([value, label]) => (
            <option key={value} value={value === 'all' ? '' : value}>
              {label}
            </option>
          ))}
        </select>
        <select
          className="input select"
          aria-label={tr.library.sortLabel}
          value={query.sort}
          onChange={(event) => set({ sort: event.target.value })}
        >
          {Object.entries(tr.library.sorts).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label className="lib-check">
          <input
            type="checkbox"
            checked={query.status === 'missing'}
            onChange={(event) => set({ status: event.target.checked ? 'missing' : '' })}
          />
          {tr.library.onlyMissing}
        </label>
        <div className="segmented" role="radiogroup" aria-label={tr.library.view}>
          {(['grid', 'list'] as View[]).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={view === value}
              className={view === value ? 'segment active' : 'segment'}
              onClick={() => setView(value)}
            >
              {tr.library[value]}
            </button>
          ))}
        </div>
      </div>

      <div className="lib-status">
        {page && (
          <span className="muted" data-testid="library-summary">
            {tr.library.summary(page.facets.count, formatBytes(page.facets.total_size), page.facets.missing)}
          </span>
        )}
        <span className="toolbar-spacer" />
        {scan && scan !== 'running' && <span className="muted">{tr.library.scanResult(scan)}</span>}
        <button
          type="button"
          className="btn"
          title={tr.library.scanHelp}
          disabled={scan === 'running'}
          onClick={() => void runScan()}
        >
          {scan === 'running' ? tr.library.scanning : tr.library.scan}
        </button>
      </div>

      {actionError && (
        <Notice tone="danger">
          {(tr.errors as Record<string, { title: string }>)[actionError]?.title ?? actionError}
        </Notice>
      )}

      <Panel title={tr.library.title} count={page?.items.length} flush>
        {state.phase === 'loading' && <LoadingState title={tr.library.loading} body="" />}
        {state.phase === 'error' && (
          <ErrorState code={state.code} raw={state.raw} onRetry={() => void load(query)} />
        )}
        {page && page.items.length === 0 && (
          filtered ? (
            <EmptyState glyph="⌕" title={tr.library.noMatchTitle} body={tr.library.noMatchBody} />
          ) : (
            <EmptyState glyph="▦" title={tr.library.emptyTitle} body={tr.library.emptyBody} />
          )
        )}
        {page && page.items.length > 0 && view === 'grid' && (
          <ul className="lib-grid">
            {page.items.map((item) => (
              <li
                key={item.id}
                className={selected === item.id ? 'lib-card selected' : 'lib-card'}
                data-testid="library-item"
                data-item-id={item.id}
              >
                <button
                  type="button"
                  className="lib-card-button"
                  aria-expanded={selected === item.id}
                  onClick={() => setSelected(selected === item.id ? null : item.id)}
                >
                  <Thumb item={item} />
                  <span className="lib-card-title">{item.title}</span>
                  <span className="muted lib-card-meta">
                    {item.channel} · {formatDuration(item.duration)} · {formatBytes(item.size)}
                  </span>
                </button>
                <div className="lib-card-badges">
                  {item.mode && (
                    <Badge>
                      <Term
                        label={tr.download.modes[item.mode] ?? item.mode}
                        body={tr.download.modeHelp[item.mode] ?? ''}
                      />
                    </Badge>
                  )}
                  {item.status === 'missing' && <MissingBadge />}
                </div>
                {selected === item.id && (
                  <div className="lib-card-more">
                    <Details item={item} />
                    <Actions item={item} onTrash={setConfirming} onError={setActionError} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {page && page.items.length > 0 && view === 'list' && (
          <table className="grid lib-table">
            <thead>
              <tr>
                <th>{tr.table.name}</th>
                <th className="optional">{tr.library.siteLabel}</th>
                <th className="optional">{tr.library.sorts.uploaded}</th>
                <th className="num">{tr.table.duration}</th>
                <th className="num">{tr.table.size}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {page.items.map((item) => (
                <tr key={item.id} data-testid="library-item" data-item-id={item.id}>
                  <td>
                    <button
                      type="button"
                      className="linklike"
                      aria-expanded={selected === item.id}
                      onClick={() => setSelected(selected === item.id ? null : item.id)}
                    >
                      {item.title}
                    </button>{' '}
                    {item.status === 'missing' && <MissingBadge />}
                    <div className="muted">{item.channel}</div>
                    {selected === item.id && (
                      <>
                        <Details item={item} />
                        <button
                          type="button"
                          className="btn btn-quiet danger-text"
                          disabled={item.status === 'missing'}
                          onClick={() => setConfirming(item)}
                        >
                          {tr.library.trash}
                        </button>
                      </>
                    )}
                  </td>
                  <td className="optional muted">{item.site}</td>
                  <td className="optional muted">{formatUploadDate(item.upload_date)}</td>
                  <td className="num">{formatDuration(item.duration)}</td>
                  <td className="num">{formatBytes(item.size)}</td>
                  <td>
                    <Actions
                      item={item}
                      onTrash={setConfirming}
                      onError={setActionError}
                      withTrash={false}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <ConfirmDialog
        open={confirming !== null}
        title={tr.library.trashTitle}
        body={tr.library.trashBody(confirming?.files.length ?? 1)}
        confirmLabel={tr.library.confirmTrash}
        cancelLabel={tr.library.cancel}
        danger
        onConfirm={() => void confirmTrash()}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}
