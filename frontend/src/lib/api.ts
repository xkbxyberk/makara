export type SizeKind = 'exact' | 'approx' | 'estimated' | 'unknown';
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
  has_audio: boolean;
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

export interface VideoModel {
  kind: 'video';
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

export const api = {
  doctor: () => request<DoctorReport>('/api/doctor'),
  inspect: (url: string) =>
    request<InspectModel>('/api/inspect', { method: 'POST', body: JSON.stringify({ url }) }),
};
