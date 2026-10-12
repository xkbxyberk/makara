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
  mode: Mode | 'studio';
  progress: number;
  speed: number | null;
  eta: number | null;
  item_index: number | null;
  item_count: number | null;
  output_files: string[];
  warnings: { code: string; key?: string }[];
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
  clipboard_watch: boolean;
  notifications: boolean;
  /** Read-only: the app's built-in template, for "Varsayılana dön". */
  default_filename_template?: string;
}

export interface LibraryTrack {
  codec: string | null;
  language: string | null;
  default: boolean;
  width: number | null;
  height: number | null;
  channels: number | null;
}

export interface LibraryItem {
  id: string;
  job_id: string | null;
  title: string | null;
  source_url: string | null;
  site: string | null;
  channel: string | null;
  upload_date: string | null;
  mode: Mode | 'studio' | null;
  kind: 'video' | 'audio';
  status: 'ok' | 'missing' | 'trashed';
  primary_path: string;
  size: number | null;
  duration: number | null;
  files: { path: string; size: number | null; role: string }[];
  tracks: { video: LibraryTrack[]; audio: LibraryTrack[]; subtitle: LibraryTrack[] };
  thumbnail: string | null;
  added_at: number;
}

export interface LibraryPage {
  items: LibraryItem[];
  facets: { sites: string[]; count: number; total_size: number; missing: number };
}

export interface LibraryQuery {
  search: string;
  site: string;
  kind: string;
  status: string;
  sort: string;
}

export interface ScanResult {
  checked: number;
  missing: number;
  repaired: number;
  restored: number;
}

export interface UpdateResult {
  before: { version: string };
  after: { version: string };
  changed: boolean;
  log: string;
}

/** The remembered shape of a quick choice ("1080p, MKV"), carried over to the next video. */
export interface QuickRule {
  kind: 'video' | 'audio';
  height?: number | null;
  fps?: number | null;
  hdr?: boolean;
  output?: 'mkv' | 'compat_mp4' | null;
  format?: 'opus' | 'm4a' | 'mp3' | null;
}

export type OfferStep = 'copy' | 'transcode' | 'probe';
export type OfferOutput = 'mkv' | 'compat_mp4';

export interface OfferSelection extends TrackSelection {
  mode: Mode;
  audio_codec: AudioCodec | null;
  audio_quality: string | null;
}

export interface VideoOffer {
  id: string;
  kind: 'video';
  height: number | null;
  fps: number | null;
  dynamic_range: string | null;
  ai_upscaled: boolean;
  outputs: Record<
    OfferOutput,
    {
      selection: OfferSelection;
      video_format_id: string;
      vcodec_label: string | null;
      size: Plan['size'];
      video_step: OfferStep;
      audio_steps: OfferStep[];
      /** The heaviest step of any track: what the row's badge says. */
      step: OfferStep;
      /** Today's two-click default in this output. */
      recommended: boolean;
      hdr_tonemap: boolean;
    }
  >;
  rule: QuickRule;
}

export interface AudioOffer {
  id: string;
  kind: 'audio';
  format: 'opus' | 'm4a' | 'mp3';
  format_id: string;
  source_codec_label: string | null;
  abr: number | null;
  step: OfferStep;
  size: Plan['size'];
  rule: QuickRule;
  selection: OfferSelection;
}

export interface Offers {
  video: VideoOffer[];
  audio: AudioOffer[];
  preselected: { offer_id: string; output: OfferOutput | null } | null;
}

export interface VideoModel {
  kind: 'video';
  inspect_id: string;
  defaults: Record<Mode, TrackSelection>;
  offers: Offers;
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

export type StudioOp = 'audio' | 'trim' | 'remux' | 'subtitle';

export interface StudioStream {
  index: number;
  type: 'video' | 'audio' | 'subtitle' | string;
  codec: string | null;
  language: string | null;
  title: string | null;
  default: boolean;
  attached_pic: boolean;
  width: number | null;
  height: number | null;
  channels: number | null;
}

export interface StudioSource {
  youtube_auto_captions: boolean;
  path: string;
  name: string;
  ext: string;
  size: number;
  duration: number | null;
  streams: StudioStream[];
  chapters: { start: number; end: number; title: string | null }[];
}

export interface StudioRequest {
  source_path: string;
  op: StudioOp;
  options: Record<string, unknown>;
  output_name: string;
  extra_paths: string[];
}

export interface StudioPlan {
  steps: { kind: 'ffmpeg' | 'python'; action: string; command: string }[];
  notices: Notice[];
  blocking: boolean;
  outputs: string[];
  ext: string;
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export const api = {
  doctor: () => request<DoctorReport>('/api/doctor'),
  inspect: (url: string, rule?: QuickRule | null) =>
    request<InspectModel>('/api/inspect', post({ url, rule: rule ?? null })),
  plan: (selection: Selection) => request<Plan>('/api/plan', post(selection)),
  createJob: (selection: Selection) => request<Job>('/api/jobs', post(selection)),
  jobs: () => request<Job[]>('/api/jobs'),
  cancel: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, post({})),
  retry: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}/retry`, post({})),
  remove: (id: string) =>
    request<{ ok: boolean }>(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  settings: () => request<Settings>('/api/settings'),
  saveSettings: (settings: Settings) =>
    request<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(settings) }),
  previewTemplate: (template: string, sample: Record<string, string>) =>
    request<{ filename: string }>('/api/settings/preview-template', post({ template, sample })),
  pickFolder: (prompt: string) =>
    request<{ path: string | null }>('/api/system/pick-folder', post({ prompt })),
  updateYtdlp: () => request<UpdateResult>('/api/system/update-ytdlp', post({})),
  library: (query: LibraryQuery) => {
    const params = new URLSearchParams(
      Object.entries(query).filter(([, value]) => value !== '') as [string, string][],
    );
    return request<LibraryPage>(`/api/library?${params.toString()}`);
  },
  scanLibrary: () => request<ScanResult>('/api/library/scan', post({})),
  openItem: (id: string) =>
    request<{ opened: boolean }>(`/api/library/${encodeURIComponent(id)}/open`, post({})),
  revealItem: (id: string) =>
    request<{ shown: boolean }>(`/api/library/${encodeURIComponent(id)}/reveal`, post({})),
  trashItem: (id: string) =>
    request<LibraryItem>(`/api/library/${encodeURIComponent(id)}/trash`, post({})),
  studioProbe: (body: { path?: string; item_id?: string }) =>
    request<StudioSource>('/api/studio/probe', post(body)),
  studioPlan: (body: StudioRequest) => request<StudioPlan>('/api/studio/plan', post(body)),
  studioJob: (body: StudioRequest) => request<Job>('/api/studio/jobs', post(body)),
  pickFile: (prompt: string) =>
    request<{ path: string | null }>('/api/system/pick-file', post({ prompt })),
  thumbnailUrl: (id: string) => `/api/library/${encodeURIComponent(id)}/thumbnail`,
  notify: (title: string, body: string) =>
    request<{ shown: boolean }>('/api/notify', post({ title, body })),
  revealJobFile: (id: string, index: number) =>
    request<{ shown: boolean }>(`/api/jobs/${encodeURIComponent(id)}/reveal`, post({ index })),
};
