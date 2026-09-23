import { tr } from '../i18n/tr';

const UNITS = [tr.units.bytes, tr.units.kib, tr.units.mib, tr.units.gib, tr.units.tib];

/** Binary units, the way Finder and yt-dlp both report sizes. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '–';
  if (bytes < 1024) return `${bytes} ${UNITS[0]}`;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${UNITS[unit]}`;
}

/** The marker that says how much to trust a size. */
export function sizePrefix(kind: string): string {
  if (kind === 'approx') return '≈';
  if (kind === 'estimated') return '~';
  if (kind === 'partial') return '≥';
  return '';
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '–';
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

export function formatBitrate(kbps: number | null | undefined): string {
  if (!kbps || !Number.isFinite(kbps)) return '–';
  return kbps >= 1000
    ? `${(kbps / 1000).toFixed(1)} ${tr.units.mbps}`
    : `${Math.round(kbps)} ${tr.units.kbps}`;
}

/** yt-dlp gives upload_date as YYYYMMDD. */
export function formatUploadDate(value: string | null | undefined): string {
  if (!value || !/^\d{8}$/.test(value)) return '–';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(
    new Date(Number(value.slice(0, 4)), Number(value.slice(4, 6)) - 1, Number(value.slice(6, 8))),
  );
}

export function formatSampleRate(hz: number | null | undefined): string {
  if (!hz || !Number.isFinite(hz)) return '–';
  return `${(hz / 1000).toFixed(1)} ${tr.units.khz}`;
}

export function formatCount(value: number | null | undefined): string {
  if (!value || !Number.isFinite(value)) return '–';
  return new Intl.NumberFormat('tr-TR', { notation: 'compact' }).format(value);
}

const displayNames =
  typeof Intl !== 'undefined' && 'DisplayNames' in Intl
    ? new Intl.DisplayNames(['tr'], { type: 'language', fallback: 'code' })
    : null;

/**
 * Language codes into Turkish names. YouTube's audio-description tracks arrive as
 * "en-desc", which is not a real BCP-47 tag, so the suffix is peeled off first.
 */
export function languageName(code: string | null | undefined): string {
  if (!code) return tr.app.unknown;
  const base = code.endsWith('-desc') ? code.slice(0, -5) : code;
  try {
    return displayNames?.of(base) ?? base;
  } catch {
    return base;
  }
}

/** "90", "1:30", "1:02:03.5" or "12,5" -> seconds; null when it is not a time. */
export function parseTime(text: string): number | null {
  const value = text.trim().replace(',', '.');
  if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d+)?$/.test(value)) return null;
  const parts = value.split(':').map(Number);
  if (parts.slice(1).some((p) => p >= 60)) return null;
  return parts.reduce((total, part) => total * 60 + part, 0);
}

/** Seconds -> "m:ss.ms" (or "h:mm:ss.ms"), the inverse of parseTime for input fields. */
export function formatTime(seconds: number): string {
  const whole = Math.floor(seconds);
  const fraction = Math.round((seconds - whole) * 1000);
  const base = formatDuration(whole);
  return fraction ? `${base}.${String(fraction).padStart(3, '0').replace(/0+$/, '')}` : base;
}
