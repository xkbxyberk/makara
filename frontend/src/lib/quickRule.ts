import type { QuickRule } from './api';

/**
 * The last quick choice per site ("1080p · MKV" on youtube.com), so the next video from that
 * site opens with the closest choice preselected. Browser storage only: a convenience, never
 * state anything depends on -- every read and write may fail and is allowed to.
 */
const KEY = 'vd-quick-rules';

// Hosts that are the same site for this purpose: one remembered choice for all of them.
const ALIASES: Record<string, string> = { 'youtu.be': 'youtube.com', 'music.youtube.com': 'youtube.com' };

export function siteOf(url: string): string | null {
  try {
    const host = new URL(url).hostname.toLowerCase().replace(/^(www|m)\./, '');
    return ALIASES[host] ?? (host || null);
  } catch {
    return null;
  }
}

/** Only a well-formed rule is sent; anything else (an older or damaged entry) is dropped. */
function valid(rule: unknown): rule is QuickRule {
  if (!rule || typeof rule !== 'object') return false;
  const r = rule as Record<string, unknown>;
  const optionalNumber = (v: unknown, max: number) =>
    v === undefined || v === null || (typeof v === 'number' && Number.isFinite(v) && v > 0 && v <= max);
  if (r.kind === 'audio') return r.format === 'opus' || r.format === 'm4a' || r.format === 'mp3';
  return (
    r.kind === 'video' &&
    optionalNumber(r.height, 10_000) &&
    optionalNumber(r.fps, 1000) &&
    (r.hdr === undefined || typeof r.hdr === 'boolean') &&
    (r.output === undefined || r.output === null || r.output === 'mkv' || r.output === 'compat_mp4')
  );
}

function readAll(): Record<string, QuickRule> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, QuickRule>) : {};
  } catch {
    return {};
  }
}

export function loadRule(url: string): QuickRule | null {
  const site = siteOf(url);
  const rule = site ? readAll()[site] : undefined;
  return valid(rule) ? rule : null;
}

export function saveRule(url: string, rule: QuickRule): void {
  const site = siteOf(url);
  if (!site) return;
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readAll(), [site]: rule }));
  } catch {
    // Private window or blocked storage: the choice is simply not remembered.
  }
}
