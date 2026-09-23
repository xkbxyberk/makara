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
import { Icon } from '../components/Icon';
import { ToolbarItems } from '../components/Toolbar';

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
      <div className="lib-thumb lib-thumb-empty">
        <Icon name={item.kind === 'audio' ? 'music.note' : 'film'} size={30} />
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
  onStudio,
}: {
  item: LibraryItem;
  onTrash: (item: LibraryItem) => void;
  onError: (code: string) => void;
  onStudio: (itemId: string) => void;
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
        <Icon name="play.fill" size={12} />
        {tr.library.play}
      </button>
      <button type="button" className="btn" disabled={missing} onClick={run(() => api.revealItem(item.id))}>
        <Icon name="folder" size={14} />
        {tr.library.reveal}
      </button>
      <button type="button" className="btn" disabled={missing} onClick={() => onStudio(item.id)}>
        <Icon name="scissors" size={14} />
        {tr.library.openInStudio}
      </button>
      <button
        type="button"
        className="btn btn-quiet danger-text"
        disabled={missing}
        onClick={() => onTrash(item)}
      >
        <Icon name="trash" size={14} />
        {tr.library.trash}
      </button>
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

export function LibraryRoute({
  refreshKey,
  onOpenInStudio,
}: {
  refreshKey: number;
  onOpenInStudio: (itemId: string) => void;
}) {
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
  const chosen = page?.items.find((item) => item.id === selected) ?? null;
  const select = (id: string) => setSelected((current) => (current === id ? null : id));

  return (
    <div className="content-inner">
      <ToolbarItems>
        <div className="searchfield">
          <Icon name="magnifyingglass" size={14} />
          <input
            className="input"
            type="search"
            value={query.search}
            placeholder={tr.library.search}
            aria-label={tr.library.search}
            onChange={(event) => set({ search: event.target.value })}
          />
        </div>
        <div className="segmented icons" role="radiogroup" aria-label={tr.library.view}>
          {(['grid', 'list'] as View[]).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={view === value}
              aria-label={tr.library[value]}
              title={tr.library[value]}
              className={view === value ? 'segment active' : 'segment'}
              onClick={() => setView(value)}
            >
              <Icon name={value === 'grid' ? 'square.grid.2x2' : 'list.bullet'} size={15} />
            </button>
          ))}
        </div>
        <button
          type="button"
          className="btn-icon"
          aria-label={tr.library.scan}
          title={tr.library.scanHelp}
          disabled={scan === 'running'}
          onClick={() => void runScan()}
        >
          {scan === 'running' ? <span className="spinner" /> : <Icon name="arrow.clockwise" size={17} />}
        </button>
      </ToolbarItems>

      <div className="lib-toolbar">
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
        <span className="toolbar-spacer" />
        {page && (
          <span className="muted" data-testid="library-summary">
            {tr.library.summary(page.facets.count, formatBytes(page.facets.total_size), page.facets.missing)}
          </span>
        )}
      </div>

      {scan && scan !== 'running' && <Notice>{tr.library.scanResult(scan)}</Notice>}
      {actionError && (
        <Notice tone="danger">
          {(tr.errors as Record<string, { title: string }>)[actionError]?.title ?? actionError}
        </Notice>
      )}

      <div className={chosen ? 'lib-layout with-inspector' : 'lib-layout'}>
        <Panel title={tr.library.title} count={page?.items.length} flush>
          {state.phase === 'loading' && <LoadingState title={tr.library.loading} body="" />}
          {state.phase === 'error' && (
            <ErrorState code={state.code} raw={state.raw} onRetry={() => void load(query)} />
          )}
          {page && page.items.length === 0 &&
            (filtered ? (
              <EmptyState icon="magnifyingglass" title={tr.library.noMatchTitle} body={tr.library.noMatchBody} />
            ) : (
              <EmptyState icon="books.vertical" title={tr.library.emptyTitle} body={tr.library.emptyBody} />
            ))}
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
                    aria-pressed={selected === item.id}
                    onClick={() => select(item.id)}
                  >
                    <Thumb item={item} />
                    <span className="lib-card-title">{item.title}</span>
                    <span className="lib-card-meta">
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
                </tr>
              </thead>
              <tbody>
                {page.items.map((item) => (
                  <tr
                    key={item.id}
                    data-testid="library-item"
                    data-item-id={item.id}
                    className={selected === item.id ? 'selected' : undefined}
                  >
                    <td>
                      <button
                        type="button"
                        className="linklike"
                        aria-pressed={selected === item.id}
                        onClick={() => select(item.id)}
                      >
                        {item.title}
                      </button>{' '}
                      {item.status === 'missing' && <MissingBadge />}
                      <div className="muted">{item.channel}</div>
                    </td>
                    <td className="optional muted">{item.site}</td>
                    <td className="optional muted">{formatUploadDate(item.upload_date)}</td>
                    <td className="num">{formatDuration(item.duration)}</td>
                    <td className="num">{formatBytes(item.size)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        {chosen && (
          <aside className="inspector" aria-label={tr.library.details} data-testid="inspector">
            <div className="panel-body inspector-body">
              <Thumb item={chosen} />
              <div className="inspector-title">{chosen.title}</div>
              <div className="muted">{chosen.channel}</div>
              <div className="lib-card-badges">
                {chosen.mode && (
                  <Badge>
                    <Term
                      label={tr.download.modes[chosen.mode] ?? chosen.mode}
                      body={tr.download.modeHelp[chosen.mode] ?? ''}
                    />
                  </Badge>
                )}
                {chosen.status === 'missing' && <MissingBadge />}
              </div>
              <Actions
                item={chosen}
                onTrash={setConfirming}
                onError={setActionError}
                onStudio={onOpenInStudio}
              />
              <Details item={chosen} />
            </div>
          </aside>
        )}
      </div>

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
