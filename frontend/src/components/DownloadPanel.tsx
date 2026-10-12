import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { tr } from '../i18n/tr';
import {
  ApiError,
  api,
  type AudioCodec,
  type AudioFormat,
  type AudioLanguageGroup,
  type Extras,
  type Mode,
  type AudioOffer,
  type Notice as PlanNotice,
  type OfferStep,
  type QuickRule,
  type VideoOffer,
  type Plan,
  type Selection,
  type SubtitleTrack,
  type TrackSelection,
  type VideoFormat,
  type VideoModel,
} from '../lib/api';
import { formatBitrate, formatBytes, languageName, sizePrefix } from '../lib/format';
import { Badge, CopyButton, ErrorState, Notice, Panel, Term } from './ui';
import { Icon } from './Icon';
import { saveRule } from '../lib/quickRule';

const MODES: Mode[] = ['mkv', 'compat_mp4', 'separate', 'audio'];
const CODECS: AudioCodec[] = ['mp3', 'm4a', 'opus', 'flac', 'wav'];
const LOSSY: AudioCodec[] = ['mp3', 'm4a', 'opus'];
const QUALITIES = ['320', '256', '192', '128'];
const DEFAULT_EXTRAS: Extras = {
  thumbnail: true,
  thumbnail_file: false,
  description: false,
  info_json: false,
};

function noticeText(notice: PlanNotice): string {
  const entry = tr.download.notices[notice.code];
  if (typeof entry === 'function') return entry(notice.params);
  return entry ?? notice.code;
}

function videoLabel(format: VideoFormat | undefined): string {
  if (!format) return tr.download.noVideo;
  const height = format.height ? `${format.height}p` : (format.resolution ?? format.format_id);
  return [height, format.vcodec_label].filter(Boolean).join(' · ');
}

function trackLabel(track: AudioFormat): string {
  const parts = [track.acodec_label, formatBitrate(track.abr ?? track.tbr)];
  if (track.filesize) parts.push(`${sizePrefix(track.filesize_kind)}${formatBytes(track.filesize)}`);
  return `${track.format_id} · ${parts.filter((p) => p && p !== '–').join(' · ')}`;
}

type Start = { mode: Mode; tracks: TrackSelection; audioCodec: AudioCodec } | null;

/** The quick choice the server preselected for a remembered rule, as the panel's first state. */
function startFrom(model: VideoModel, remembered: boolean): Start {
  const pre = model.offers?.preselected;
  if (!remembered || !pre) return null;
  const video = model.offers.video.find((r) => r.id === pre.offer_id);
  if (video && pre.output) {
    const { video_format_id, audio_format_ids, subtitle_keys } = video.outputs[pre.output].selection;
    return { mode: pre.output, tracks: { video_format_id, audio_format_ids, subtitle_keys }, audioCodec: 'mp3' };
  }
  const audio = model.offers.audio.find((r) => r.id === pre.offer_id);
  if (audio) {
    return {
      mode: 'audio',
      tracks: { video_format_id: null, audio_format_ids: audio.selection.audio_format_ids, subtitle_keys: [] },
      audioCodec: audio.format,
    };
  }
  return null;
}

function ruleFor(row: VideoOffer | AudioOffer, mode: Mode): QuickRule {
  return row.kind === 'video' ? { ...row.rule, output: mode === 'compat_mp4' ? 'compat_mp4' : 'mkv' } : row.rule;
}

export function DownloadPanel({
  model,
  remembered,
  active,
  onQueued,
  onReinspect,
}: {
  model: VideoModel;
  /** The inspect was asked with a remembered quick choice; start from what it preselected. */
  remembered: boolean;
  /** Whether the Inspect screen is the one on show; ⌘↵ only works there. */
  active: boolean;
  onQueued: () => void;
  onReinspect: () => void;
}) {
  const [start] = useState<Start>(() => startFrom(model, remembered));
  const [mode, setMode] = useState<Mode>(start?.mode ?? 'mkv');
  const [tracks, setTracks] = useState<Record<Mode, TrackSelection>>(() =>
    start ? { ...model.defaults, [start.mode]: start.tracks } : model.defaults,
  );
  const [audioCodec, setAudioCodec] = useState<AudioCodec>(start?.audioCodec ?? 'mp3');
  const [audioQuality, setAudioQuality] = useState('192');
  const [extras, setExtras] = useState<Extras>(DEFAULT_EXTRAS);
  const [template, setTemplate] = useState<string | null>(null);
  const [defaultTemplate, setDefaultTemplate] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  // Which selection the plan on screen was computed for. İndir stays disabled until they match,
  // so a job can never start on a selection whose warnings were not shown.
  const [planKey, setPlanKey] = useState('');
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [queued, setQueued] = useState(false);
  // A remembered choice already decided the mode; the settings' default must not override it.
  const touchedMode = useRef(start !== null);
  // Only a quick choice Berk actually made (or the remembered one he kept) becomes the rule for
  // the next video. Downloading the untouched default must not: on a site whose video happens
  // to top out at 240p, that would quietly cap every later video at 240p.
  const [chosenId, setChosenId] = useState<string | null>(() =>
    start ? (model.offers.preselected?.offer_id ?? null) : null,
  );
  const planTicket = useRef(0);

  // The user's preferred mode, unless they already picked one on this screen.
  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        setDefaultTemplate(settings.filename_template);
        if (!touchedMode.current) setMode(settings.default_mode);
      })
      .catch(() => undefined);
  }, []);

  const current = tracks[mode];
  const selection: Selection = useMemo(
    () => ({
      inspect_id: model.inspect_id,
      mode,
      ...current,
      video_format_id: mode === 'audio' ? null : current.video_format_id,
      subtitle_keys: mode === 'audio' ? [] : current.subtitle_keys,
      audio_codec: mode === 'audio' ? audioCodec : null,
      audio_quality: mode === 'audio' && LOSSY.includes(audioCodec) ? audioQuality : null,
      filename_template: template,
      extras,
    }),
    [model.inspect_id, mode, current, audioCodec, audioQuality, template, extras],
  );

  const selectionKey = useMemo(() => JSON.stringify(selection), [selection]);
  const planIsCurrent = plan !== null && planKey === selectionKey;

  useEffect(() => {
    const ticket = ++planTicket.current;
    const timer = setTimeout(() => {
      api
        .plan(selection)
        .then((next) => {
          if (ticket !== planTicket.current) return;
          setPlan(next);
          setPlanKey(selectionKey);
          setFailure(null);
        })
        .catch((error: unknown) => {
          if (ticket !== planTicket.current) return;
          setFailure(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error)));
        });
    }, 150);
    setQueued(false);
    return () => clearTimeout(timer);
  }, [selection, selectionKey]);

  const update = (patch: Partial<TrackSelection>) =>
    setTracks((all) => ({ ...all, [mode]: { ...all[mode], ...patch } }));

  const quickRows: (VideoOffer | AudioOffer)[] =
    mode === 'audio' ? (model.offers?.audio ?? []) : mode === 'separate' ? [] : (model.offers?.video ?? []);
  const activeRow = quickRows.find((row) =>
    row.kind === 'video'
      ? (mode === 'mkv' || mode === 'compat_mp4') && row.outputs[mode].video_format_id === current.video_format_id
      : row.format === audioCodec && current.audio_format_ids[0] === row.format_id,
  );
  const applyRow = (row: VideoOffer | AudioOffer) => {
    if (row.kind === 'video') {
      if (mode !== 'mkv' && mode !== 'compat_mp4') return;
      const { video_format_id, audio_format_ids } = row.outputs[mode].selection;
      update({ video_format_id, audio_format_ids }); // subtitles stay as chosen
    } else {
      update({ audio_format_ids: row.selection.audio_format_ids });
      setAudioCodec(row.format);
      if (row.selection.audio_quality) setAudioQuality(row.selection.audio_quality);
    }
    setChosenId(row.id);
  };

  const submit = useCallback(async () => {
    if (submitting || !plan || !planIsCurrent || plan.blocking) return;
    setSubmitting(true);
    try {
      await api.createJob(selection);
      setQueued(true);
      // Remember the shape of this choice for the next video from the same site.
      if (activeRow && activeRow.id === chosenId) saveRule(model.source_url, ruleFor(activeRow, mode));
    } catch (error) {
      setFailure(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error)));
    } finally {
      setSubmitting(false);
    }
  }, [plan, planIsCurrent, selection, submitting, activeRow, chosenId, mode, model.source_url]);

  // ⌘↵ downloads -- only while Inspect is on screen, and once per press (not per key repeat).
  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.repeat) {
        event.preventDefault();
        void submit();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active, submit]);

  const videos = useMemo(
    () => [...model.video_formats, ...model.muxed_formats],
    [model.video_formats, model.muxed_formats],
  );
  const video = videos.find((f) => f.format_id === current.video_format_id);
  const audioById = useMemo(() => {
    const map = new Map<string, { track: AudioFormat; group: AudioLanguageGroup }>();
    for (const group of model.audio_languages) {
      for (const track of group.tracks) map.set(track.format_id, { track, group });
    }
    return map;
  }, [model.audio_languages]);

  const summaryAudio = current.audio_format_ids
    .map((id) => audioById.get(id))
    .filter((entry): entry is { track: AudioFormat; group: AudioLanguageGroup } => !!entry)
    .map(({ group }) => `${languageName(group.language)} (${tr.roles[group.role]})`);
  const muxedSource = mode === 'audio' ? videos.find((f) => current.audio_format_ids.includes(f.format_id)) : undefined;

  if (failure?.code === 'INSPECT_EXPIRED') {
    return (
      <Panel title={tr.download.title}>
        <ErrorState code={failure.code} raw={failure.raw} />
        <div style={{ textAlign: 'center' }}>
          <button type="button" className="btn btn-primary" onClick={onReinspect}>
            {tr.download.reinspect}
          </button>
        </div>
      </Panel>
    );
  }

  return (
    <Panel title={tr.download.title}>
      <div className="download">
        <div className="segmented" role="radiogroup" aria-label={tr.download.title}>
          {MODES.map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={mode === value}
              className={mode === value ? 'segment active' : 'segment'}
              title={tr.download.modeHelp[value]}
              onClick={() => {
                touchedMode.current = true;
                setMode(value);
              }}
            >
              {tr.download.modes[value]}
            </button>
          ))}
        </div>
        <p className="muted mode-help">{tr.download.modeHelp[mode]}</p>

        {quickRows.length > 0 && (
          <QuickChoices
            rows={quickRows}
            mode={mode}
            activeId={activeRow?.id ?? null}
            rememberedId={remembered ? (model.offers.preselected?.offer_id ?? null) : null}
            onChoose={applyRow}
          />
        )}

        <div className="summary" data-testid="download-summary">
          {mode !== 'audio' && <span className="chip">{videoLabel(video)}</span>}
          {summaryAudio.length > 0 ? (
            summaryAudio.map((label) => (
              <span className="chip" key={label}>
                {label}
              </span>
            ))
          ) : muxedSource ? (
            <span className="chip">{videoLabel(muxedSource)}</span>
          ) : (
            (mode === 'audio' || !video?.has_audio) && <span className="chip">{tr.download.noAudio}</span>
          )}
          {mode !== 'audio' && (
            <span className="chip">
              {current.subtitle_keys.length
                ? tr.download.subtitlesSummary(current.subtitle_keys.map(languageName).join(', '))
                : tr.download.noSubtitles}
            </span>
          )}
          {mode === 'audio' && <span className="chip">{audioCodec.toUpperCase()}</span>}
        </div>

        <dl className="facts">
          <dt>{tr.download.estimatedSize}</dt>
          <dd data-testid="download-size">
            {plan?.size.bytes ? (
              plan.size.kind === 'exact' ? (
                formatBytes(plan.size.bytes)
              ) : (
                <Term
                  label={`${sizePrefix(plan.size.kind)}${formatBytes(plan.size.bytes)}`}
                  body={
                    plan.size.kind === 'partial'
                      ? tr.terms.partialSize.body
                      : plan.size.unreliable
                        ? tr.terms.manifest.body
                        : tr.terms.approxSize.body
                  }
                />
              )
            ) : (
              <span className="dim">{plan ? tr.download.unknownSize : tr.download.planning}</span>
            )}
          </dd>
          <dt>{tr.download.willSaveTo}</dt>
          <dd className="mono path" data-testid="download-filename">
            {plan?.filename ? (
              <>
                <span className="dim">{plan.download_dir}/</span>
                {plan.filename}
              </>
            ) : plan?.filename_error ? (
              <span className="danger-text">{tr.errors[plan.filename_error as keyof typeof tr.errors]?.title ?? plan.filename_error}</span>
            ) : (
              <span className="dim">{tr.download.planning}</span>
            )}
          </dd>
        </dl>

        {plan?.notices
          .filter((n) => n.code !== 'UNKNOWN_SELECTION' || plan.blocking)
          .map((notice) => (
            <Notice key={notice.code} tone={notice.level === 'error' ? 'danger' : notice.level === 'warn' ? 'warn' : 'neutral'}>
              {noticeText(notice)}
            </Notice>
          ))}
        {failure && failure.code !== 'INSPECT_EXPIRED' && (
          <ErrorState code={failure.code} raw={failure.raw} />
        )}
        {queued && (
          <Notice>
            <span style={{ flex: 1 }}>{tr.download.queued}</span>
            <button type="button" className="btn" onClick={onQueued}>
              {tr.download.openQueue}
            </button>
          </Notice>
        )}

        <div className="download-actions">
          <button
            type="button"
            className="btn btn-quiet"
            aria-expanded={pickerOpen}
            onClick={() => setPickerOpen((open) => !open)}
          >
            <Icon name="slider.horizontal.3" size={14} />
            {pickerOpen ? tr.download.hidePicker : tr.download.showPicker}
          </button>
          <span className="toolbar-spacer" />
          <span className="dim">{tr.download.shortcut}</span>
          <button
            type="button"
            className="btn btn-primary btn-large"
            disabled={!planIsCurrent || plan.blocking || submitting}
            onClick={() => void submit()}
          >
            {submitting ? <span className="spinner" /> : <Icon name="arrow.down.circle" size={15} />}
            {submitting ? tr.download.submitting : tr.download.submit}
          </button>
        </div>

        {pickerOpen && (
          <TrackPicker
            model={model}
            mode={mode}
            selection={current}
            videos={videos}
            update={update}
            audioCodec={audioCodec}
            setAudioCodec={setAudioCodec}
            audioQuality={audioQuality}
            setAudioQuality={setAudioQuality}
            extras={extras}
            setExtras={setExtras}
            template={template ?? defaultTemplate}
            setTemplate={(value) => setTemplate(value === defaultTemplate ? null : value)}
            resetTemplate={() => setTemplate(null)}
            command={plan?.command ?? ''}
          />
        )}
      </div>
    </Panel>
  );
}

function stepBadge(step: OfferStep) {
  if (step === 'copy') return <Badge tone="ok">{tr.download.quick.copy}</Badge>;
  if (step === 'probe') return <Badge>{tr.download.quick.probe}</Badge>;
  return <Badge tone="warn">{tr.download.quick.transcode}</Badge>;
}

/** Same honesty as the panel's own size: estimated, manifest-based and partial sizes explain
 * themselves, and "unknown until converted" is only said of a conversion. */
function OfferSize({ size, step }: { size: VideoOffer['outputs']['mkv']['size']; step: OfferStep }) {
  if (!size.bytes) {
    return <span className="dim">{step === 'transcode' ? tr.download.quick.sizeLater : tr.download.unknownSize}</span>;
  }
  const text = `${sizePrefix(size.kind)}${formatBytes(size.bytes)}`;
  if (size.kind === 'exact') return <span>{text}</span>;
  const body =
    size.kind === 'partial'
      ? tr.terms.partialSize.body
      : size.unreliable
        ? tr.terms.manifest.body
        : tr.terms.approxSize.body;
  return <Term label={text} body={body} />;
}

/** One click per quality the video really has; the full picker stays below for everything else. */
function QuickChoices({
  rows,
  mode,
  activeId,
  rememberedId,
  onChoose,
}: {
  rows: (VideoOffer | AudioOffer)[];
  mode: Mode;
  activeId: string | null;
  rememberedId: string | null;
  onChoose: (row: VideoOffer | AudioOffer) => void;
}) {
  return (
    <div className="quick" role="radiogroup" aria-label={tr.download.quick.title} data-testid="quick-choices">
      <div className="quick-head">
        <span className="quick-title">{tr.download.quick.title}</span>
        <span className="dim">{mode === 'audio' ? tr.download.quick.audioHelp : tr.download.quick.videoHelp}</span>
      </div>
      {rows.map((row) => {
        const checked = row.id === activeId;
        let label: string;
        let detail: string;
        let size: VideoOffer['outputs']['mkv']['size'];
        let step: OfferStep;
        let badges: React.ReactNode;
        if (row.kind === 'video') {
          const out = row.outputs[mode === 'compat_mp4' ? 'compat_mp4' : 'mkv'];
          label = row.height ? `${row.height}p` : tr.download.quick.unknownHeight;
          detail = [out.vcodec_label, row.fps ? tr.download.quick.fps(row.fps) : null].filter(Boolean).join(' · ');
          size = out.size;
          step = out.step;
          badges = (
            <>
              {row.dynamic_range && row.dynamic_range !== 'SDR' && <Badge tone="accent">{row.dynamic_range}</Badge>}
              {row.ai_upscaled && <Badge tone="warn">{tr.terms.aiUpscaled.label}</Badge>}
              {out.step !== 'copy' && stepBadge(out.step)}
            </>
          );
        } else {
          label = tr.download.quick.formats[row.format];
          detail = [row.source_codec_label, row.abr ? formatBitrate(row.abr) : null].filter(Boolean).join(' · ');
          size = row.size;
          step = row.step;
          badges = stepBadge(row.step);
        }
        return (
          <button
            key={row.id}
            type="button"
            role="radio"
            aria-checked={checked}
            className={checked ? 'quick-row checked' : 'quick-row'}
            data-offer-id={row.id}
            onClick={() => onChoose(row)}
          >
            <Icon name={checked ? 'checkmark.circle.fill' : 'circle'} tone={checked ? 'accent' : 'secondary'} size={16} />
            <span className="quick-label">{label}</span>
            <span className="quick-detail dim">{detail}</span>
            <span className="quick-badges">
              {badges}
              {row.id === rememberedId && <span className="dim">{tr.download.quick.remembered}</span>}
            </span>
            <span className="quick-size">
              <OfferSize size={size} step={step} />
            </span>
          </button>
        );
      })}
    </div>
  );
}

function TrackPicker(props: {
  model: VideoModel;
  mode: Mode;
  selection: TrackSelection;
  videos: VideoFormat[];
  update: (patch: Partial<TrackSelection>) => void;
  audioCodec: AudioCodec;
  setAudioCodec: (codec: AudioCodec) => void;
  audioQuality: string;
  setAudioQuality: (quality: string) => void;
  extras: Extras;
  setExtras: (extras: Extras) => void;
  template: string;
  setTemplate: (value: string) => void;
  resetTemplate: () => void;
  command: string;
}) {
  const { model, mode, selection, videos, update } = props;
  const [showTranslated, setShowTranslated] = useState(false);
  const [filter, setFilter] = useState('');
  const audioOnly = mode === 'audio';

  const toggleSubtitle = (key: string) =>
    update({
      subtitle_keys: selection.subtitle_keys.includes(key)
        ? selection.subtitle_keys.filter((k) => k !== key)
        : [...selection.subtitle_keys, key],
    });

  const groupSelected = (group: AudioLanguageGroup) =>
    group.tracks.find((t) => selection.audio_format_ids.includes(t.format_id));

  const setGroup = (group: AudioLanguageGroup, formatId: string | null) => {
    const others = selection.audio_format_ids.filter(
      (id) => !group.tracks.some((t) => t.format_id === id),
    );
    if (audioOnly) {
      update({ audio_format_ids: formatId ? [formatId] : [] });
      return;
    }
    // Keep the original (or first chosen) language first: it becomes the default track.
    const current = groupSelected(group);
    if (!formatId) {
      update({ audio_format_ids: others });
    } else if (current) {
      update({
        audio_format_ids: selection.audio_format_ids.map((id) => (id === current.format_id ? formatId : id)),
      });
    } else {
      update({ audio_format_ids: [...others, formatId] });
    }
  };

  const subtitleRow = (row: SubtitleTrack) => (
    <label className={row.shadowed_by_manual ? 'pick-row dim' : 'pick-row'} key={row.key}>
      <input
        type="checkbox"
        disabled={row.shadowed_by_manual}
        checked={selection.subtitle_keys.includes(row.key)}
        onChange={() => toggleSubtitle(row.key)}
      />
      <span>{languageName(row.language)}</span>
      <span className="dim mono">{row.key}</span>
      {row.shadowed_by_manual && <span className="dim">{tr.inspect.subShadowed}</span>}
    </label>
  );

  const translated = model.subtitles.auto_translated.filter((row) => {
    const needle = filter.trim().toLocaleLowerCase('tr');
    return !needle || row.key.includes(needle) || languageName(row.language).toLocaleLowerCase('tr').includes(needle);
  });

  return (
    <div className="picker" data-testid="track-picker">
      {!audioOnly && (
        <fieldset>
          <legend>{tr.download.sections.video}</legend>
          <div className="pick-list">
            {videos.map((format) => (
              <label className="pick-row" key={format.format_id}>
                <input
                  type="radio"
                  name="video"
                  checked={selection.video_format_id === format.format_id}
                  onChange={() => update({ video_format_id: format.format_id })}
                />
                <span className="pick-main">{videoLabel(format)}</span>
                <span className="dim">
                  {format.fps ? `${Math.round(format.fps)} ${tr.units.fps}` : ''}
                </span>
                {format.dynamic_range && format.dynamic_range !== 'SDR' && (
                  <Badge tone="accent">
                    <Term label={format.dynamic_range} body={tr.terms.hdr.body} />
                  </Badge>
                )}
                {format.ai_upscaled && (
                  <Badge tone="warn">
                    <Term label={tr.terms.aiUpscaled.label} body={tr.terms.aiUpscaled.body} />
                  </Badge>
                )}
                {format.has_audio === true && (
                  <Badge tone="accent">
                    <Term label={tr.terms.muxed.label} body={tr.terms.muxed.body} />
                  </Badge>
                )}
                <span className="toolbar-spacer" />
                <span className="dim mono">{format.format_id}</span>
                <span className="num">
                  {format.filesize ? `${sizePrefix(format.filesize_kind)}${formatBytes(format.filesize)}` : '–'}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <fieldset>
        <legend>{tr.download.sections.audio}</legend>
        <div className="pick-list">
          {model.audio_languages.map((group) => {
            const chosen = groupSelected(group);
            const key = group.language ?? 'und';
            return (
              <div className="pick-row" key={key}>
                <input
                  type={audioOnly ? 'radio' : 'checkbox'}
                  name="audio"
                  aria-label={languageName(group.language)}
                  checked={!!chosen}
                  onChange={(event) =>
                    setGroup(group, event.target.checked ? (group.tracks[0]?.format_id ?? null) : null)
                  }
                />
                <span className="pick-main">{languageName(group.language)}</span>
                <Badge tone={group.role === 'original' ? 'ok' : 'neutral'}>
                  <Term label={tr.roles[group.role]} body={tr.roleHelp[group.role]} />
                </Badge>
                <span className="toolbar-spacer" />
                <select
                  className="input select"
                  aria-label={`${languageName(group.language)} ${tr.download.variant}`}
                  value={chosen?.format_id ?? group.tracks[0]?.format_id}
                  onChange={(event) => setGroup(group, event.target.value)}
                >
                  {group.tracks.map((track) => (
                    <option key={track.format_id} value={track.format_id}>
                      {trackLabel(track)}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
          {audioOnly &&
            model.audio_languages.length === 0 &&
            model.muxed_formats.map((format) => (
              <label className="pick-row" key={format.format_id}>
                <input
                  type="radio"
                  name="audio"
                  checked={selection.audio_format_ids.includes(format.format_id)}
                  onChange={() => update({ audio_format_ids: [format.format_id] })}
                />
                <span className="pick-main">{videoLabel(format)}</span>
                <Badge tone="accent">
                  <Term label={tr.terms.muxed.label} body={tr.terms.muxed.body} />
                </Badge>
              </label>
            ))}
        </div>
      </fieldset>

      {audioOnly && (
        <fieldset>
          <legend>{tr.download.sections.audioFormat}</legend>
          <div className="pick-inline">
            <select
              className="input select"
              aria-label={tr.download.sections.audioFormat}
              value={props.audioCodec}
              onChange={(event) => props.setAudioCodec(event.target.value as AudioCodec)}
            >
              {CODECS.map((codec) => (
                <option key={codec} value={codec}>
                  {tr.download.audioCodecs[codec]}
                </option>
              ))}
            </select>
            {LOSSY.includes(props.audioCodec) && (
              <select
                className="input select"
                aria-label={tr.download.quality}
                value={props.audioQuality}
                onChange={(event) => props.setAudioQuality(event.target.value)}
              >
                {QUALITIES.map((q) => (
                  <option key={q} value={q}>
                    {q} {tr.units.kbps}
                  </option>
                ))}
              </select>
            )}
          </div>
        </fieldset>
      )}

      {!audioOnly && (
        <fieldset>
          <legend>{tr.download.sections.subtitles}</legend>
          <div className="pick-list">
            {model.subtitles.manual.length === 0 && model.subtitles.auto.length === 0 && (
              <div className="dim">{tr.inspect.noSubtitles}</div>
            )}
            {model.subtitles.manual.length > 0 && <div className="pick-group">{tr.inspect.subManual}</div>}
            {model.subtitles.manual.map(subtitleRow)}
            {model.subtitles.auto.length > 0 && <div className="pick-group">{tr.inspect.subAuto}</div>}
            {model.subtitles.auto.map(subtitleRow)}
            {model.subtitles.auto_translated.length > 0 && (
              <>
                <button
                  type="button"
                  className="btn btn-quiet pick-group"
                  aria-expanded={showTranslated}
                  onClick={() => setShowTranslated((v) => !v)}
                >
                  {showTranslated
                    ? tr.inspect.subTranslatedHide
                    : tr.inspect.subTranslatedCount(model.subtitles.auto_translated.length)}
                </button>
                {showTranslated && (
                  <>
                    <input
                      className="input"
                      type="search"
                      value={filter}
                      placeholder={tr.download.translatedFilter}
                      aria-label={tr.download.translatedFilter}
                      onChange={(event) => setFilter(event.target.value)}
                    />
                    {translated.map(subtitleRow)}
                  </>
                )}
              </>
            )}
          </div>
        </fieldset>
      )}

      <fieldset>
        <legend>{tr.download.sections.extras}</legend>
        {(Object.keys(props.extras) as (keyof Extras)[]).map((key) => (
          <label className="pick-row" key={key}>
            <input
              type="checkbox"
              checked={props.extras[key]}
              onChange={(event) => props.setExtras({ ...props.extras, [key]: event.target.checked })}
            />
            <span>{tr.download.extras[key]}</span>
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend>
          <Term label={tr.download.sections.filename} body={tr.download.templateHelp} />
        </legend>
        <div className="pick-inline">
          <input
            className="input mono"
            type="text"
            spellCheck={false}
            aria-label={tr.download.sections.filename}
            value={props.template}
            onChange={(event) => props.setTemplate(event.target.value)}
          />
          <button type="button" className="btn" onClick={props.resetTemplate}>
            {tr.download.templateReset}
          </button>
        </div>
      </fieldset>

      {props.command && (
        <fieldset>
          <legend>{tr.download.sections.command}</legend>
          <div className="cmd">
            <code className="mono">{props.command}</code>
            <CopyButton value={props.command} />
          </div>
        </fieldset>
      )}
    </div>
  );
}
