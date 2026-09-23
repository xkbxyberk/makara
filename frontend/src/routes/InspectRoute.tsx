import { useCallback, useEffect, useRef, useState } from 'react';
import { tr } from '../i18n/tr';
import {
  ApiError,
  api,
  type AudioLanguageGroup,
  type InspectModel,
  type PlaylistModel,
  type SubtitleTrack,
  type VideoFormat,
  type VideoModel,
} from '../lib/api';
import {
  formatBitrate,
  formatBytes,
  formatCount,
  formatDuration,
  formatUploadDate,
  languageName,
  sizePrefix,
} from '../lib/format';
import { Badge, CopyButton, EmptyState, ErrorState, LoadingState, Notice, Panel, Term } from '../components/ui';

type State =
  | { phase: 'empty' }
  | { phase: 'loading'; url: string }
  | { phase: 'error'; code: string; raw: string; url: string }
  | { phase: 'ready'; model: InspectModel };

function SizeCell({ format }: { format: { filesize: number | null; filesize_kind: string; filesize_unreliable: boolean } }) {
  const text = `${sizePrefix(format.filesize_kind)}${formatBytes(format.filesize)}`;
  if (format.filesize_kind === 'exact' || format.filesize === null) {
    return <span>{text}</span>;
  }
  const term = format.filesize_unreliable ? tr.terms.manifest : tr.terms.approxSize;
  return (
    <span title={term.body}>
      <Term label={text} body={term.body} />
    </span>
  );
}

function DrmBadge({ drm }: { drm: string }) {
  if (drm === 'none') return null;
  return (
    <Badge tone="danger">
      <Term label={tr.terms.drm.label} body={tr.terms.drm.body} />
    </Badge>
  );
}

function VideoTable({ formats, title }: { formats: VideoFormat[]; title: string }) {
  return (
    <Panel title={title} count={formats.length} flush>
      {formats.length === 0 ? (
        <div className="state">{tr.inspect.noVideoFormats}</div>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>{tr.table.format}</th>
              <th>{tr.table.resolution}</th>
              <th className="num">{tr.table.fps}</th>
              <th>{tr.table.codec}</th>
              <th className="optional">
                <Term label={tr.terms.hdr.label} body={tr.terms.hdr.body} />
              </th>
              <th className="num optional">{tr.table.bitrate}</th>
              <th className="optional">{tr.table.container}</th>
              <th className="num">{tr.table.size}</th>
            </tr>
          </thead>
          <tbody>
            {formats.map((f) => (
              <tr key={f.format_id}>
                <td className="mono">
                  {f.format_id} <DrmBadge drm={f.drm} />
                  {f.has_audio && (
                    <Badge tone="accent">
                      <Term label={tr.terms.muxed.label} body={tr.terms.muxed.body} />
                    </Badge>
                  )}
                </td>
                <td>{f.resolution ?? '–'}</td>
                <td className="num">{f.fps ? Math.round(f.fps) : '–'}</td>
                <td>
                  {f.vcodec_label ?? '–'}
                  {f.has_audio && f.acodec_label ? ` + ${f.acodec_label}` : ''}
                </td>
                <td className={f.dynamic_range === 'SDR' ? 'dim optional' : 'optional'}>
                  {f.dynamic_range ?? '–'}
                </td>
                <td className="num optional">{formatBitrate(f.tbr)}</td>
                <td className="dim optional">
                  {f.ext ?? '–'}
                  {f.is_manifest ? ` · ${tr.terms.manifest.label}` : ''}
                </td>
                <td className="num">
                  <SizeCell format={f} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function AudioGroups({ groups }: { groups: AudioLanguageGroup[] }) {
  const [open, setOpen] = useState<string | null>(groups[0]?.language ?? null);
  return (
    <Panel title={tr.inspect.audioTracks} count={groups.length} flush>
      {groups.length === 0 ? (
        <div className="state">{tr.inspect.noAudioFormats}</div>
      ) : (
        groups.map((group) => {
          const key = group.language ?? 'und';
          const expanded = open === key;
          return (
            <div className="lang-group" key={key}>
              <button
                type="button"
                className="lang-head"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : key)}
              >
                <span className="disclosure" aria-hidden="true">
                  {expanded ? '▾' : '▸'}
                </span>
                <strong>{languageName(group.language)}</strong>
                <Badge tone={group.role === 'original' ? 'ok' : 'neutral'}>
                  <Term label={tr.roles[group.role]} body={tr.roleHelp[group.role]} />
                </Badge>
                <span className="dim mono">{group.language ?? '—'}</span>
                <span className="toolbar-spacer" />
                <span className="dim">{group.tracks.length}</span>
              </button>
              {expanded && (
                <table className="grid">
                  <thead>
                    <tr>
                      <th>{tr.table.format}</th>
                      <th>{tr.table.codec}</th>
                      <th className="num">{tr.table.bitrate}</th>
                      <th className="num">{tr.table.channels}</th>
                      <th className="num optional">{tr.table.sampleRate}</th>
                      <th className="optional">{tr.table.note}</th>
                      <th className="num">{tr.table.size}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.tracks.map((t) => (
                      <tr key={t.format_id}>
                        <td className="mono">
                          {t.format_id} <DrmBadge drm={t.drm} />
                        </td>
                        <td>{t.acodec_label ?? '–'}</td>
                        <td className="num">{formatBitrate(t.abr ?? t.tbr)}</td>
                        <td className="num">{t.channels ?? '–'}</td>
                        <td className="num optional">
                          {t.asr ? `${(t.asr / 1000).toFixed(1)} kHz` : '–'}
                        </td>
                        <td className="dim optional">{t.format_note ?? '–'}</td>
                        <td className="num">
                          <SizeCell format={t} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })
      )}
    </Panel>
  );
}

function SubtitleList({ rows }: { rows: SubtitleTrack[] }) {
  return (
    <table className="grid">
      <thead>
        <tr>
          <th>{tr.table.language}</th>
          <th>{tr.table.name}</th>
          <th>{tr.table.formats}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            <td>
              {languageName(row.language)} <span className="dim mono">{row.key}</span>
              {row.is_original_track && <Badge tone="ok">{tr.inspect.subOriginalTrack}</Badge>}
            </td>
            <td className="muted">
              {row.name ?? '–'}
              {row.source_language && (
                <span className="dim"> · {tr.inspect.subFrom(languageName(row.source_language))}</span>
              )}
            </td>
            <td>
              <span className="chip-row">
                {row.exts.map((ext) => (
                  <span className="chip mono" key={ext}>
                    {ext}
                  </span>
                ))}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Subtitles({ model }: { model: VideoModel }) {
  const [showTranslated, setShowTranslated] = useState(false);
  const { manual, auto, auto_translated, has_live_chat } = model.subtitles;
  const total = manual.length + auto.length + auto_translated.length;
  if (total === 0) {
    return (
      <Panel title={tr.inspect.subtitles} count={0}>
        <div className="state">{tr.inspect.noSubtitles}</div>
      </Panel>
    );
  }
  return (
    <Panel title={tr.inspect.subtitles} count={total} flush>
      {has_live_chat && (
        <div style={{ padding: 'var(--space-3) var(--space-4)' }}>
          <Notice>{tr.inspect.liveChat}</Notice>
        </div>
      )}
      {manual.length > 0 && (
        <div className="lang-group">
          <div className="lang-head" style={{ cursor: 'default' }}>
            <strong>
              <Term label={tr.inspect.subManual} body={tr.inspect.subManualHelp} />
            </strong>
            <span className="dim">{manual.length}</span>
          </div>
          <SubtitleList rows={manual} />
        </div>
      )}
      {auto.length > 0 && (
        <div className="lang-group">
          <div className="lang-head" style={{ cursor: 'default' }}>
            <strong>
              <Term label={tr.inspect.subAuto} body={tr.inspect.subAutoHelp} />
            </strong>
            <span className="dim">{auto.length}</span>
          </div>
          <SubtitleList rows={auto} />
        </div>
      )}
      {auto_translated.length > 0 && (
        <div className="lang-group">
          <button
            type="button"
            className="lang-head"
            aria-expanded={showTranslated}
            onClick={() => setShowTranslated((v) => !v)}
          >
            <span className="disclosure" aria-hidden="true">
              {showTranslated ? '▾' : '▸'}
            </span>
            <strong>
              <Term label={tr.inspect.subAutoTranslated} body={tr.inspect.subAutoTranslatedHelp} />
            </strong>
            <span className="toolbar-spacer" />
            <span className="btn btn-quiet">
              {showTranslated
                ? tr.inspect.subTranslatedHide
                : tr.inspect.subTranslatedCount(auto_translated.length)}
            </span>
          </button>
          {showTranslated && <SubtitleList rows={auto_translated} />}
        </div>
      )}
    </Panel>
  );
}

function Metadata({ model }: { model: VideoModel }) {
  const [open, setOpen] = useState(false);
  const meta = model.media;
  return (
    <Panel title={tr.inspect.metadata}>
      <div className="meta-grid">
        <div>
          {meta.thumbnail && <img className="meta-thumb" src={meta.thumbnail} alt="" loading="lazy" />}
        </div>
        <div>
          <h3 className="meta-title">{meta.title ?? '–'}</h3>
          <div className="meta-facts">
            {meta.channel && <span>{meta.channel}</span>}
            <span>{formatUploadDate(meta.upload_date)}</span>
            <span>{formatDuration(meta.duration)}</span>
            {meta.view_count ? <span>{formatCount(meta.view_count)} görüntülenme</span> : null}
            <span className="dim mono">{meta.extractor}</span>
          </div>
          {meta.description && (
            <>
              <p className={open ? 'description open' : 'description'}>{meta.description}</p>
              <button type="button" className="btn btn-quiet" onClick={() => setOpen((v) => !v)}>
                {open ? tr.app.showLess : tr.app.showMore}
              </button>
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}

function PlaylistView({ model, onInspect }: { model: PlaylistModel; onInspect: (url: string) => void }) {
  return (
    <>
      <Notice tone="warn">
        <div>
          <strong>{tr.inspect.playlistTitle}</strong>
          <div>{tr.inspect.playlistBody(model.entry_count)}</div>
        </div>
      </Notice>
      <Panel title={model.media.title ?? tr.inspect.playlistTitle} count={model.entries.length} flush>
        <table className="grid">
          <thead>
            <tr>
              <th>{tr.table.name}</th>
              <th className="num">{tr.table.duration}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {model.entries.map((entry) => (
              <tr key={entry.id ?? entry.url}>
                <td>{entry.title ?? '–'}</td>
                <td className="num">{formatDuration(entry.duration)}</td>
                <td className="num">
                  {entry.url && (
                    <button type="button" className="btn btn-quiet" onClick={() => onInspect(entry.url!)}>
                      {tr.inspect.playlistInspectEntry}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  );
}

export function InspectRoute() {
  const [url, setUrl] = useState('');
  const [state, setState] = useState<State>({ phase: 'empty' });
  const inputRef = useRef<HTMLInputElement>(null);

  const run = useCallback(async (target: string) => {
    const trimmed = target.trim();
    if (!trimmed) return;
    setUrl(trimmed);
    setState({ phase: 'loading', url: trimmed });
    try {
      const model = await api.inspect(trimmed);
      setState({ phase: 'ready', model });
    } catch (error) {
      const api_error = error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error));
      setState({ phase: 'error', code: api_error.code, raw: api_error.raw, url: trimmed });
    }
  }, []);

  // Cmd+V anywhere starts an inspect, as long as the user is not typing in a field.
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return;
      const text = event.clipboardData?.getData('text')?.trim();
      if (text && /^https?:\/\//i.test(text)) {
        event.preventDefault();
        void run(text);
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [run]);

  return (
    <div
      className="content-inner"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const text = event.dataTransfer.getData('text/uri-list') || event.dataTransfer.getData('text');
        if (text) void run(text);
      }}
    >
      <form
        className="url-row"
        onSubmit={(event) => {
          event.preventDefault();
          void run(url);
        }}
      >
        <input
          ref={inputRef}
          className="input"
          type="text"
          value={url}
          aria-label={tr.inspect.urlLabel}
          placeholder={tr.inspect.urlPlaceholder}
          onChange={(event) => setUrl(event.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={state.phase === 'loading'}>
          {tr.inspect.submit}
        </button>
      </form>
      <p className="dim" style={{ margin: 0 }}>
        {tr.inspect.pasteHint}
      </p>

      {state.phase === 'empty' && (
        <Panel title={tr.inspect.title}>
          <EmptyState glyph="⌘V" title={tr.inspect.emptyTitle} body={tr.inspect.emptyBody} />
        </Panel>
      )}
      {state.phase === 'loading' && (
        <Panel title={tr.inspect.title}>
          <LoadingState title={tr.inspect.loadingTitle} body={tr.inspect.loadingBody} />
        </Panel>
      )}
      {state.phase === 'error' && (
        <Panel title={tr.inspect.title}>
          <ErrorState code={state.code} raw={state.raw} onRetry={() => void run(state.url)} />
        </Panel>
      )}
      {state.phase === 'ready' && state.model.kind === 'playlist' && (
        <PlaylistView model={state.model} onInspect={(next) => void run(next)} />
      )}
      {state.phase === 'ready' && state.model.kind === 'video' && (
        <ResultView model={state.model} />
      )}
    </div>
  );
}

function ResultView({ model }: { model: VideoModel }) {
  const warnings = tr.warnings as Record<string, string>;
  const peak = Math.max(1, ...model.heatmap.map((p) => p.value ?? 0));
  return (
    <>
      {model.warnings.map((code) => (
        <Notice key={code} tone={code.startsWith('DRM') ? 'danger' : 'warn'}>
          {warnings[code] ?? code}
        </Notice>
      ))}
      <Metadata model={model} />
      <VideoTable formats={model.video_formats} title={tr.inspect.videoFormats} />
      {model.muxed_formats.length > 0 && (
        <VideoTable formats={model.muxed_formats} title={tr.inspect.muxedFormats} />
      )}
      <AudioGroups groups={model.audio_languages} />
      <Subtitles model={model} />
      {model.chapters.length > 0 && (
        <Panel title={tr.inspect.chapters} count={model.chapters.length}>
          {model.chapters.map((chapter, index) => (
            <div className="chapter-row" key={`${chapter.start_time}-${index}`}>
              <span className="chapter-time">{formatDuration(chapter.start_time)}</span>
              <span>{chapter.title ?? '–'}</span>
            </div>
          ))}
        </Panel>
      )}
      {model.heatmap.length > 0 && (
        <Panel title={tr.inspect.heatmap}>
          <div className="heatmap" aria-hidden="true">
            {model.heatmap.map((point, index) => (
              <div
                className="heatmap-bar"
                key={index}
                style={{ height: `${Math.round(((point.value ?? 0) / peak) * 100)}%` }}
              />
            ))}
          </div>
          <p className="dim" style={{ marginBottom: 0 }}>
            {tr.inspect.heatmapHint}
          </p>
        </Panel>
      )}
      <Panel title={tr.inspect.thumbnails} count={model.thumbnails.length}>
        <div className="thumb-grid">
          {model.thumbnails.slice(0, 12).map((thumb) => (
            <figure className="thumb-cell" key={thumb.url} style={{ margin: 0 }}>
              <img src={thumb.url} alt="" loading="lazy" />
              <figcaption className="dim mono">
                {thumb.width && thumb.height ? `${thumb.width}×${thumb.height}` : (thumb.id ?? '')}
              </figcaption>
            </figure>
          ))}
        </div>
      </Panel>
      <Panel title={tr.inspect.commands}>
        <p className="muted" style={{ marginTop: 0 }}>
          {tr.inspect.commandSuggested}
        </p>
        <div className="cmd">
          <code className="mono">{model.commands.suggested}</code>
          <CopyButton value={model.commands.suggested} />
        </div>
        <p className="muted">{tr.inspect.commandInspect}</p>
        <div className="cmd">
          <code className="mono">{model.commands.inspect}</code>
          <CopyButton value={model.commands.inspect} />
        </div>
      </Panel>
    </>
  );
}
