import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { tr } from '../i18n/tr';
import {
  ApiError,
  api,
  type LibraryItem,
  type Notice as PlanNotice,
  type StudioOp,
  type StudioPlan,
  type StudioRequest,
  type StudioSource,
  type StudioStream,
} from '../lib/api';
import { formatBytes, formatDuration, formatTime, languageName, parseTime } from '../lib/format';
import { CopyButton, EmptyState, ErrorState, LoadingState, Notice, Panel, Term } from '../components/ui';
import { Icon, type SymbolName } from '../components/Icon';

type SourceState =
  | { phase: 'empty' }
  | { phase: 'probing' }
  | { phase: 'error'; code: string; raw: string }
  | { phase: 'ready'; source: StudioSource };

interface Segment {
  start: string;
  end: string;
}

interface Track {
  input: number;
  stream: number;
  keep: boolean;
  language: string;
  title: string;
  default: boolean;
  meta: StudioStream;
  from: string;
}

const OPS: StudioOp[] = ['audio', 'trim', 'remux', 'subtitle'];
const OP_ICONS: Record<StudioOp, SymbolName> = {
  audio: 'waveform',
  trim: 'scissors',
  remux: 'slider.horizontal.3',
  subtitle: 'captions',
};
const CODECS = ['mp3', 'm4a', 'opus', 'flac', 'wav'];
const LOSSY = ['mp3', 'm4a', 'opus'];

function noticeText(notice: PlanNotice): string {
  const entry = tr.studio.notices[notice.code];
  if (typeof entry === 'function') return entry(notice.params);
  return entry ?? notice.code;
}

function stem(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(0, dot) : name;
}

function hasMedia(source: StudioSource): boolean {
  return source.streams.some((s) => s.type === 'video' || s.type === 'audio');
}

function tracksFor(source: StudioSource, input: number, from: string): Track[] {
  return source.streams
    .filter((s) => ['video', 'audio', 'subtitle'].includes(s.type))
    .map((s) => ({
      input,
      stream: s.index,
      keep: true,
      language: s.language && s.language !== 'und' ? s.language : '',
      title: s.title ?? '',
      default: s.default,
      meta: s,
      from,
    }));
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="studio-field">
      <span className="setting-label">{label}</span>
      {children}
    </label>
  );
}

export function StudioRoute({
  onOpenQueue,
  request,
}: {
  onOpenQueue: () => void;
  /** Opened from the library ("Stüdyo'da aç"). */
  request: { itemId: string; n: number } | null;
}) {
  const [path, setPath] = useState('');
  const [state, setState] = useState<SourceState>({ phase: 'empty' });
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [op, setOp] = useState<StudioOp>('trim');
  const [outputName, setOutputName] = useState('');
  const nameTouched = useRef(false);

  // per-operation options
  const [codec, setCodec] = useState('mp3');
  const [bitrate, setBitrate] = useState('192');
  const [sampleRate, setSampleRate] = useState('');
  const [channels, setChannels] = useState('');
  const [audioIndex, setAudioIndex] = useState(0);
  const [loudnorm, setLoudnorm] = useState(false);
  const [trimMode, setTrimMode] = useState<'lossless' | 'accurate'>('lossless');
  const [segments, setSegments] = useState<Segment[]>([]);
  const [join, setJoin] = useState(false);
  const [container, setContainer] = useState('mkv');
  const [tracks, setTracks] = useState<Track[]>([]);
  const [extras, setExtras] = useState<StudioSource[]>([]);
  const [extraPath, setExtraPath] = useState('');
  const [subAction, setSubAction] = useState('convert');
  const [subTarget, setSubTarget] = useState('srt');
  const [offset, setOffset] = useState('0');

  const [plan, setPlan] = useState<StudioPlan | null>(null);
  const [planKey, setPlanKey] = useState('');
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [queued, setQueued] = useState(false);
  const ticket = useRef(0);

  useEffect(() => {
    api
      .library({ search: '', site: '', kind: '', status: 'ok', sort: 'added' })
      .then((page) => setLibrary(page.items))
      .catch(() => undefined);
  }, []);

  const open = useCallback(async (body: { path?: string; item_id?: string }) => {
    setState({ phase: 'probing' });
    setPlan(null);
    setQueued(false);
    try {
      const source = await api.studioProbe(body);
      setPath(source.path);
      setState({ phase: 'ready', source });
      const media = hasMedia(source);
      setOp(media ? 'trim' : 'subtitle');
      setSegments([{ start: '0', end: formatTime(source.duration ?? 0) }]);
      setTracks(tracksFor(source, 0, source.name));
      setExtras([]);
      setAudioIndex(0);
      setSubAction(source.youtube_auto_captions ? 'clean' : 'convert');
      nameTouched.current = false;
    } catch (error) {
      const f = error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error));
      setState({ phase: 'error', code: f.code, raw: f.raw });
    }
  }, []);

  useEffect(() => {
    if (request) void open({ item_id: request.itemId });
  }, [request, open]);

  const source = state.phase === 'ready' ? state.source : null;

  // The default output name follows the operation until Berk types his own.
  useEffect(() => {
    if (source && !nameTouched.current) {
      setOutputName(`${stem(source.name)} ${tr.studio.outputSuffix[op]}`);
    }
  }, [source, op]);

  const parsedSegments = segments.map((s) => ({ start: parseTime(s.start), end: parseTime(s.end) }));
  const offsetSeconds = /^-?\d+([.,]\d+)?$/.test(offset.trim()) ? Number(offset.trim().replace(',', '.')) : null;
  const segmentsValid = parsedSegments.every((s) => s.start !== null && s.end !== null);

  const body: StudioRequest | null = useMemo(() => {
    if (!source || !outputName.trim()) return null;
    let options: Record<string, unknown>;
    if (op === 'audio') {
      options = {
        codec,
        bitrate: LOSSY.includes(codec) ? bitrate : null,
        sample_rate: sampleRate ? Number(sampleRate) : null,
        channels: channels ? Number(channels) : null,
        audio_index: audioIndex,
        loudnorm,
      };
    } else if (op === 'trim') {
      if (!segmentsValid) return null;
      options = { mode: trimMode, join, segments: parsedSegments };
    } else if (op === 'remux') {
      options = {
        container,
        tracks: tracks.map((t) => ({
          input: t.input,
          stream: t.stream,
          keep: t.keep,
          language: t.language || null,
          title: t.title || null,
          default: t.default,
        })),
      };
    } else {
      if (offsetSeconds === null) return null;
      options = { action: subAction, target: subTarget, offset: offsetSeconds };
    }
    return {
      source_path: source.path,
      op,
      options,
      output_name: outputName.trim(),
      extra_paths: op === 'remux' ? extras.map((e) => e.path) : [],
    };
  }, [source, op, outputName, codec, bitrate, sampleRate, channels, audioIndex, loudnorm, trimMode, join, segments, segmentsValid, container, tracks, extras, subAction, subTarget, offsetSeconds]);

  const key = useMemo(() => JSON.stringify(body), [body]);

  useEffect(() => {
    if (!body) {
      setPlan(null);
      return;
    }
    const mine = ++ticket.current;
    const timer = setTimeout(() => {
      api
        .studioPlan(body)
        .then((next) => {
          if (mine !== ticket.current) return;
          setPlan(next);
          setPlanKey(key);
          setFailure(null);
        })
        .catch((error: unknown) => {
          if (mine !== ticket.current) return;
          setFailure(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error)));
        });
    }, 200);
    setQueued(false);
    return () => clearTimeout(timer);
  }, [body, key]);

  const current = plan !== null && planKey === key;

  const run = async () => {
    if (!body || !current || plan.blocking || queued) return;
    try {
      await api.studioJob(body);
      setQueued(true);
    } catch (error) {
      setFailure(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error)));
    }
  };

  const addExtra = async () => {
    try {
      const extra = await api.studioProbe({ path: extraPath });
      setExtras((list) => {
        const index = list.length + 1; // inputs: 0 is the source, extras follow in order
        setTracks((current) => [...current, ...tracksFor(extra, index, extra.name)]);
        return [...list, extra];
      });
      setExtraPath('');
    } catch (error) {
      setFailure(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error)));
    }
  };

  const move = (index: number, by: number) =>
    setTracks((list) => {
      const next = [...list];
      const target = index + by;
      if (target < 0 || target >= next.length) return list;
      [next[index], next[target]] = [next[target]!, next[index]!];
      return next;
    });
  const editTrack = (index: number, patch: Partial<Track>) =>
    setTracks((list) => list.map((t, i) => (i === index ? { ...t, ...patch } : t)));

  const audioStreams = source?.streams.filter((s) => s.type === 'audio') ?? [];
  const streamSummary = source
    ? Object.entries(
        source.streams.reduce<Record<string, number>>((acc, s) => {
          if (tr.studio.streamKinds[s.type] && !s.attached_pic) acc[s.type] = (acc[s.type] ?? 0) + 1;
          return acc;
        }, {}),
      )
        .map(([kind, n]) => `${n} ${tr.studio.streamKinds[kind]}`)
        .join(', ')
    : '';

  return (
    <div className="content-inner">
      <Panel title={tr.studio.source}>
        <div className="studio-source">
          <select
            className="input select"
            aria-label={tr.studio.fromLibrary}
            value=""
            onChange={(event) => event.target.value && void open({ item_id: event.target.value })}
          >
            <option value="">{tr.studio.fromLibrary}</option>
            {library.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
          <form
            className="pick-inline"
            onSubmit={(event) => {
              event.preventDefault();
              if (path.trim()) void open({ path: path.trim() });
            }}
          >
            <input
              className="input mono"
              aria-label={tr.studio.pathLabel}
              placeholder={tr.studio.pathPlaceholder}
              value={path}
              spellCheck={false}
              onChange={(event) => setPath(event.target.value)}
            />
            <button type="submit" className="btn">
              {tr.studio.open}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() =>
                void api
                  .pickFile(tr.studio.choosePrompt)
                  .then((r) => {
                    if (r.path) void open({ path: r.path });
                  })
                  .catch((error: unknown) =>
                    setState({
                      phase: 'error',
                      code: error instanceof ApiError ? error.code : 'UNKNOWN',
                      raw: '',
                    }),
                  )
              }
            >
              <Icon name="folder" size={14} />
              {tr.studio.chooseFile}
            </button>
          </form>
        </div>
        {state.phase === 'empty' && <EmptyState icon="scissors" title={tr.studio.emptyTitle} body={tr.studio.emptyBody} />}
        {state.phase === 'probing' && <LoadingState title={tr.studio.probing} body="" />}
        {state.phase === 'error' && <ErrorState code={state.code} raw={state.raw} />}
        {source && (
          <p className="muted" data-testid="studio-source">
            <strong>{source.name}</strong> · {tr.studio.sourceSummary(formatDuration(source.duration), streamSummary)} ·{' '}
            {formatBytes(source.size)}
          </p>
        )}
      </Panel>

      {source && (
        <Panel title={tr.studio.operation}>
          <div className="download">
            <div className="segmented" role="radiogroup" aria-label={tr.studio.operation}>
              {OPS.map((value) => {
                const allowed = value === 'subtitle' ? !hasMedia(source) : hasMedia(source);
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={op === value}
                    disabled={!allowed}
                    className={op === value ? 'segment active' : 'segment'}
                    onClick={() => setOp(value)}
                  >
                    <Icon name={OP_ICONS[value]} size={14} />
                    {tr.studio.tabs[value]}
                  </button>
                );
              })}
            </div>

            {op === 'audio' && (
              <div className="studio-grid">
                {audioStreams.length > 1 && (
                  <Field label={tr.studio.audio.track}>
                    <select className="input select" value={audioIndex} onChange={(e) => setAudioIndex(Number(e.target.value))}>
                      {audioStreams.map((s, i) => (
                        <option key={s.index} value={i}>
                          {i + 1}. {languageName(s.language)} · {s.codec}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label={tr.studio.audio.codec}>
                  <select className="input select" value={codec} onChange={(e) => setCodec(e.target.value)}>
                    {CODECS.map((c) => (
                      <option key={c} value={c}>
                        {tr.download.audioCodecs[c as keyof typeof tr.download.audioCodecs]}
                      </option>
                    ))}
                  </select>
                </Field>
                {LOSSY.includes(codec) && (
                  <Field label={<Term label={tr.terms.bitrate.label} body={tr.terms.bitrate.body} />}>
                    <select className="input select" value={bitrate} onChange={(e) => setBitrate(e.target.value)}>
                      {['320', '256', '192', '128', '96'].map((b) => (
                        <option key={b} value={b}>
                          {b} {tr.units.kbps}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label={<Term label={tr.terms.sampleRate.label} body={tr.terms.sampleRate.body} />}>
                  <select className="input select" value={sampleRate} onChange={(e) => setSampleRate(e.target.value)}>
                    <option value="">{tr.studio.audio.auto}</option>
                    {codec !== 'opus' && <option value="44100">44,1 {tr.units.khz}</option>}
                    <option value="48000">48 {tr.units.khz}</option>
                  </select>
                </Field>
                <Field label={<Term label={tr.terms.channels.label} body={tr.terms.channels.body} />}>
                  <select className="input select" value={channels} onChange={(e) => setChannels(e.target.value)}>
                    <option value="">{tr.studio.audio.auto}</option>
                    <option value="1">{tr.studio.audio.mono}</option>
                    <option value="2">{tr.studio.audio.stereo}</option>
                  </select>
                </Field>
                <label className="setting-toggle">
                  <input type="checkbox" checked={loudnorm} onChange={(e) => setLoudnorm(e.target.checked)} />
                  <span>
                    {tr.studio.audio.loudnorm} (<Term label={tr.studio.terms.loudnorm.label} body={tr.studio.terms.loudnorm.body} />)
                  </span>
                </label>
              </div>
            )}

            {op === 'trim' && (
              <div className="studio-grid">
                <div className="segmented" role="radiogroup" aria-label={tr.studio.trim.mode}>
                  {(['lossless', 'accurate'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      role="radio"
                      aria-checked={trimMode === mode}
                      className={trimMode === mode ? 'segment active' : 'segment'}
                      onClick={() => setTrimMode(mode)}
                      title={tr.studio.terms[mode].body}
                    >
                      {tr.studio.trim[mode]}
                    </button>
                  ))}
                </div>
                <p className="dim studio-help">
                  <Term label={tr.studio.terms[trimMode].label} body={tr.studio.terms[trimMode].body} /> ·{' '}
                  <Term label={tr.studio.terms.keyframe.label} body={tr.studio.terms.keyframe.body} /> · {tr.studio.trim.timeHelp}
                </p>
                {segments.map((segment, index) => {
                  const parsed = parsedSegments[index]!;
                  return (
                    <div className="pick-inline studio-segment" key={index} data-testid="segment">
                      <input
                        className={parsed.start === null ? 'input mono invalid' : 'input mono'}
                        aria-label={`${tr.studio.trim.start} ${index + 1}`}
                        value={segment.start}
                        onChange={(e) =>
                          setSegments((list) => list.map((s, i) => (i === index ? { ...s, start: e.target.value } : s)))
                        }
                      />
                      <span className="dim">→</span>
                      <input
                        className={parsed.end === null ? 'input mono invalid' : 'input mono'}
                        aria-label={`${tr.studio.trim.end} ${index + 1}`}
                        value={segment.end}
                        onChange={(e) =>
                          setSegments((list) => list.map((s, i) => (i === index ? { ...s, end: e.target.value } : s)))
                        }
                      />
                      {segments.length > 1 && (
                        <button type="button" className="btn btn-quiet" onClick={() => setSegments((l) => l.filter((_, i) => i !== index))}>
                          {tr.studio.trim.removeSegment}
                        </button>
                      )}
                    </div>
                  );
                })}
                <div className="pick-inline">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setSegments((l) => [...l, { start: '0', end: formatTime(source.duration ?? 0) }])}
                  >
                    {tr.studio.trim.addSegment}
                  </button>
                  {segments.length > 1 && (
                    <label className="setting-toggle">
                      <input type="checkbox" checked={join} onChange={(e) => setJoin(e.target.checked)} />
                      <span>{tr.studio.trim.join}</span>
                    </label>
                  )}
                </div>
                {source.chapters.length > 0 && (
                  <div className="chip-row">
                    <span className="dim">{tr.studio.trim.chapters}:</span>
                    {source.chapters.map((chapter) => (
                      <button
                        key={chapter.start}
                        type="button"
                        className="btn btn-quiet"
                        onClick={() =>
                          setSegments((list) => [
                            ...list.filter((s) => !(s.start === '0' && list.length === 1)),
                            { start: formatTime(chapter.start), end: formatTime(chapter.end) },
                          ])
                        }
                      >
                        {chapter.title ?? formatTime(chapter.start)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {op === 'remux' && (
              <div className="studio-grid">
                <p className="dim studio-help">
                  <Term label={tr.studio.terms.remux.label} body={tr.studio.terms.remux.body} />
                </p>
                <Field label={<Term label={tr.studio.terms.container.label} body={tr.studio.terms.container.body} />}>
                  <div className="segmented" role="radiogroup" aria-label={tr.studio.remux.container}>
                    {['mkv', 'mp4', 'mov'].map((c) => (
                      <button
                        key={c}
                        type="button"
                        role="radio"
                        aria-checked={container === c}
                        className={container === c ? 'segment active' : 'segment'}
                        onClick={() => setContainer(c)}
                      >
                        {c.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </Field>
                <table className="grid studio-tracks">
                  <thead>
                    <tr>
                      <th>{tr.studio.remux.keep}</th>
                      <th>{tr.studio.remux.kind}</th>
                      <th>
                        <Term label={tr.terms.codec.label} body={tr.terms.codec.body} />
                      </th>
                      <th>{tr.studio.remux.language}</th>
                      <th className="optional">{tr.studio.remux.title}</th>
                      <th>{tr.studio.remux.isDefault}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {tracks.map((track, index) => (
                      <tr key={`${track.input}-${track.stream}`} className={track.keep ? undefined : 'dim'}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`${tr.studio.remux.keep} ${index + 1}`}
                            checked={track.keep}
                            onChange={(e) => editTrack(index, { keep: e.target.checked })}
                          />
                        </td>
                        <td>
                          {tr.studio.streamKinds[track.meta.type] ?? track.meta.type}
                          {track.input > 0 && <div className="dim">{tr.studio.remux.fromExtra(track.from)}</div>}
                        </td>
                        <td className="mono">{track.meta.codec}</td>
                        <td>
                          <input
                            className="input mono narrow"
                            aria-label={`${tr.studio.remux.language} ${index + 1}`}
                            value={track.language}
                            placeholder={tr.studio.remux.languagePlaceholder}
                            onChange={(e) => editTrack(index, { language: e.target.value.trim() })}
                          />
                        </td>
                        <td className="optional">
                          <input className="input" value={track.title} onChange={(e) => editTrack(index, { title: e.target.value })} />
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`${tr.studio.remux.isDefault} ${index + 1}`}
                            checked={track.default}
                            onChange={(e) => editTrack(index, { default: e.target.checked })}
                          />
                        </td>
                        <td className="studio-move">
                          <button type="button" className="btn-icon" aria-label={tr.studio.remux.moveUp} title={tr.studio.remux.moveUp} onClick={() => move(index, -1)}>
                            <Icon name="chevron.up" size={14} />
                          </button>
                          <button type="button" className="btn-icon" aria-label={tr.studio.remux.moveDown} title={tr.studio.remux.moveDown} onClick={() => move(index, 1)}>
                            <Icon name="chevron.down" size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <form
                  className="pick-inline"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (extraPath.trim()) void addExtra();
                  }}
                >
                  <input
                    className="input mono"
                    aria-label={tr.studio.remux.addPath}
                    placeholder={tr.studio.remux.addFile}
                    value={extraPath}
                    onChange={(e) => setExtraPath(e.target.value)}
                  />
                  <button type="submit" className="btn">
                    {tr.studio.remux.add}
                  </button>
                </form>
              </div>
            )}

            {op === 'subtitle' && (
              <div className="studio-grid">
                {source.youtube_auto_captions && <Notice>{tr.studio.subtitle.looksAuto}</Notice>}
                <Field label={tr.studio.subtitle.action}>
                  <select className="input select" value={subAction} onChange={(e) => setSubAction(e.target.value)}>
                    {Object.entries(tr.studio.subtitle.actions).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={tr.studio.subtitle.target}>
                  <select className="input select" value={subTarget} onChange={(e) => setSubTarget(e.target.value)}>
                    {['srt', 'vtt', 'ass'].map((f) => (
                      <option key={f} value={f}>
                        {f.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </Field>
                {subAction === 'shift' && (
                  <Field label={tr.studio.subtitle.offset}>
                    <input
                      className={offsetSeconds === null ? 'input mono narrow invalid' : 'input mono narrow'}
                      value={offset}
                      aria-invalid={offsetSeconds === null}
                      onChange={(e) => setOffset(e.target.value)}
                    />
                    {offsetSeconds === null && <span className="danger-text">{tr.studio.subtitle.offsetInvalid}</span>}
                  </Field>
                )}
              </div>
            )}

            <Field label={tr.studio.output}>
              <input
                className="input"
                aria-label={tr.studio.output}
                value={outputName}
                onChange={(e) => {
                  nameTouched.current = true;
                  setOutputName(e.target.value);
                }}
              />
            </Field>
          </div>
        </Panel>
      )}

      {source && (
        <Panel title={tr.studio.commands}>
          <div className="download">
            {!current && <span className="dim">{tr.studio.planning}</span>}
            {plan?.notices.map((notice) => (
              <Notice
                key={`${notice.code}-${JSON.stringify(notice.params)}`}
                tone={notice.level === 'error' ? 'danger' : notice.level === 'warn' ? 'warn' : 'neutral'}
              >
                {noticeText(notice)}
              </Notice>
            ))}
            {plan && (
              <dl className="facts">
                <dt>{tr.studio.willWrite}</dt>
                <dd className="mono path" data-testid="studio-output">
                  {plan.outputs.map((o) => (
                    <div key={o}>{o}</div>
                  ))}
                </dd>
              </dl>
            )}
            {plan?.steps.map((step, index) =>
              step.kind === 'ffmpeg' ? (
                <div className="cmd" key={index} data-testid="studio-command">
                  <code className="mono">{step.command}</code>
                  <CopyButton value={step.command} />
                </div>
              ) : (
                <p className="muted" key={index}>
                  {tr.studio.steps[step.action] ?? step.action}
                </p>
              ),
            )}
            {plan?.steps
              .filter((s) => s.kind === 'ffmpeg' && tr.studio.steps[s.action])
              .map((s) => (
                <p className="dim" key={`note-${s.action}`}>
                  {tr.studio.steps[s.action]}
                </p>
              ))}
            {failure && <ErrorState code={failure.code} raw={failure.raw} />}
            {queued && (
              <Notice>
                <span style={{ flex: 1 }}>{tr.studio.queued}</span>
                <button type="button" className="btn" onClick={onOpenQueue}>
                  {tr.studio.openQueue}
                </button>
              </Notice>
            )}
            <div className="download-actions">
              <span className="toolbar-spacer" />
              <button
                type="button"
                className="btn btn-primary btn-large"
                disabled={!current || plan.blocking || queued}
                onClick={() => void run()}
              >
                <Icon name="play.fill" size={13} />
                {tr.studio.run}
              </button>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
