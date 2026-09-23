export type SizeKind = 'exact' | 'approx' | 'estimated' | 'partial' | 'unknown';
export type AudioRole = 'original' | 'default' | 'dub' | 'descriptive' | 'unknown';

export interface BaseFormat {
  format_id: string;
  ext: string | null;
  container: string | null;
  protocol: string | null;
  is_manifest: boolean;
  filesize: number | null;
  filesize_kind: SizeKind;
  filesize_unreliable: boolean;
  tbr: number | null;
  drm: 'none' | 'maybe' | 'yes';
  format_note: string | null;
  ai_upscaled: boolean;
  drc: boolean;
}

export interface VideoFormat extends BaseFormat {
  width: number | null;
  height: number | null;
  resolution: string | null;
  fps: number | null;
  vcodec: string | null;
  vcodec_label: string | null;
  vbr: number | null;
  dynamic_range: string | null;
  /** true: carries sound; false: silent; null: unknown. */
  has_audio: boolean | null;
  acodec_label: string | null;
}

export interface AudioFormat extends BaseFormat {
  language: string | null;
  language_preference: number | null;
  role: AudioRole;
  acodec: string | null;
  acodec_label: string | null;
  abr: number | null;
  asr: number | null;
  channels: number | null;
}

export interface AudioLanguageGroup {
  language: string | null;
  role: AudioRole;
  tracks: AudioFormat[];
}

export interface SubtitleTrack {
  key: string;
  language: string;
  name: string | null;
  exts: string[];
  kind: 'manual' | 'auto' | 'auto_translated';
  source_language: string | null;
  is_original_track?: boolean;
  shadowed_by_manual?: boolean;
}

export interface Chapter { start_time: number | null; end_time: number | null; title: string | null }
export interface HeatmapPoint { start_time: number | null; end_time: number | null; value: number | null }
export interface Thumbnail { id: string | null; url: string; width: number | null; height: number | null }

export interface MediaMeta {
  id: string | null;
  title: string | null;
  description: string | null;
  webpage_url: string | null;
  extractor: string | null;
  channel: string | null;
  channel_url: string | null;
  upload_date: string | null;
  duration: number | null;
  view_count: number | null;
  like_count: number | null;
  live_status: string | null;
  availability: string | null;
  thumbnail: string | null;
}

export type Mode = 'mkv' | 'compat_mp4' | 'separate' | 'audio';
export type AudioCodec = 'mp3' | 'm4a' | 'opus' | 'flac' | 'wav';

export interface TrackSelection {
  video_format_id: string | null;
  audio_format_ids: string[];
  subtitle_keys: string[];
}

export interface Extras {
  thumbnail: boolean;
  thumbnail_file: boolean;
  description: boolean;
  info_json: boolean;
}

export interface Selection extends TrackSelection {
  inspect_id: string;
  mode: Mode;
  audio_codec: AudioCodec | null;
  audio_quality: string | null;
  filename_template: string | null;
  extras: Extras;
}

export interface Notice {
  code: string;
  level: 'info' | 'warn' | 'error';
  params: Record<string, unknown>;
}

export interface Plan {
  size: { bytes: number | null; kind: SizeKind; unreliable: boolean; missing: number };
  notices: Notice[];
  plan: { video: string | null; audio: string[]; subtitles: string | null };
  blocking: boolean;
  filename: string | null;
  filename_error: string | null;
  download_dir: string;
  command: string;
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  stage: string;
  title: string | null;
  source_url: string | null;
  mode: Mode;
  progress: number;
  speed: number | null;
  eta: number | null;
  item_index: number | null;
  item_count: number | null;
  output_files: string[];
  error_code: string | null;
  error_raw: string | null;
  created_at: number;
  finished_at: number | null;
}

export interface Settings {
  download_dir: string;
  filename_template: string;
  concurrency: number;
  default_mode: Mode;
}

export interface VideoModel {
  kind: 'video';
  inspect_id: string;
  defaults: Record<Mode, TrackSelection>;
  media: MediaMeta;
  video_formats: VideoFormat[];
  muxed_formats: VideoFormat[];
  audio_languages: AudioLanguageGroup[];
  subtitles: {
    manual: SubtitleTrack[];
    auto: SubtitleTrack[];
    auto_translated: SubtitleTrack[];
    has_live_chat: boolean;
  };
  chapters: Chapter[];
  heatmap: HeatmapPoint[];
  thumbnails: Thumbnail[];
  warnings: string[];
  source_url: string;
  commands: { inspect: string; suggested: string };
}

export interface PlaylistEntry {
  id: string | null;
  title: string | null;
  url: string | null;
  duration: number | null;
  view_count: number | null;
}

export interface PlaylistModel {
  kind: 'playlist';
  media: Pick<MediaMeta, 'id' | 'title' | 'webpage_url' | 'extractor' | 'channel' | 'description'>;
  entries: PlaylistEntry[];
  entry_count: number;
  warnings: string[];
  source_url: string;
  commands: { inspect: string; suggested: string };
}

export type InspectModel = VideoModel | PlaylistModel;

export interface DoctorCheck {
  id: string;
  status: 'ok' | 'warn' | 'error';
  values: Record<string, unknown>;
  fix: { kind: 'command' | 'none'; command: string };
}

export interface DoctorReport {
  status: 'ok' | 'warn' | 'error';
  checks: DoctorCheck[];
}

/** The backend never sends prose; it sends a code the UI knows how to say in Turkish. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly raw: string,
  ) {
    super(code);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    throw new ApiError('NETWORK', String(cause));
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: { code?: string; raw?: string } } | null)?.error;
    throw new ApiError(error?.code ?? 'UNKNOWN', error?.raw ?? `HTTP ${response.status}`);
  }
  return body as T;
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export const api = {
  doctor: () => request<DoctorReport>('/api/doctor'),
  inspect: (url: string) => request<InspectModel>('/api/inspect', post({ url })),
  plan: (selection: Selection) => request<Plan>('/api/plan', post(selection)),
  createJob: (selection: Selection) => request<Job>('/api/jobs', post(selection)),
  jobs: () => request<Job[]>('/api/jobs'),
  cancel: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, post({})),
  retry: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}/retry`, post({})),
  remove: (id: string) =>
    request<{ ok: boolean }>(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  settings: () => request<Settings>('/api/settings'),
  notify: (title: string, body: string) =>
    request<{ shown: boolean }>('/api/notify', post({ title, body })),
  reveal: (path: string) => request<{ shown: boolean }>('/api/reveal', post({ path })),
};
