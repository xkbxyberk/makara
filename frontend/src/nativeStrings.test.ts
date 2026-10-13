import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { tr } from './i18n/tr';

/**
 * The native app's screens (macos/VideoDownloaderKit) word the same backend codes and states as
 * the web page. Its catalog is a copy of these tables; this keeps the copy equal, so a change
 * here that is not made there (or the other way round) fails.
 */
const catalog = JSON.parse(
  readFileSync(
    // vitest runs in frontend/ (jsdom's URL cannot name a file).
    resolve(process.cwd(), '../macos/VideoDownloaderKit/Sources/VideoDownloaderKit/Resources/Localizable.xcstrings'),
    'utf8',
  ),
) as { strings: Record<string, { localizations: { tr: { stringUnit: { value: string } } } }> };

const native = Object.fromEntries(
  Object.entries(catalog.strings).map(([key, entry]) => [key, entry.localizations.tr.stringUnit.value]),
);

/** Every native key under `prefix`, without the prefix. */
function family(prefix: string, suffix = ''): Record<string, string> {
  return Object.fromEntries(
    Object.entries(native)
      .filter(([key]) => key.startsWith(prefix) && key.endsWith(suffix))
      .map(([key, value]) => [key.slice(prefix.length, key.length - suffix.length), value]),
  );
}

describe('the native catalog', () => {
  it('words every error code exactly as the web page does', () => {
    const titles = Object.fromEntries(Object.entries(tr.errors).map(([code, copy]) => [code, copy.title]));
    const bodies = Object.fromEntries(Object.entries(tr.errors).map(([code, copy]) => [code, copy.body]));
    expect(family('error.', '.title')).toEqual(titles);
    expect(family('error.', '.body')).toEqual(bodies);
  });

  it('names job states, stages and modes as the web page does', () => {
    expect(family('queue.status.')).toEqual(tr.queue.statuses);
    expect(family('queue.stage.')).toEqual(tr.queue.stages);
    expect(family('mode.')).toEqual(tr.download.modes);
  });

  it('says the same about each system check', () => {
    expect(family('doctor.check.')).toEqual(tr.doctor.checks);
    expect(family('doctor.checkHelp.')).toEqual(tr.doctor.checkHelp);
    expect(family('doctor.session.')).toEqual(tr.doctor.sessionStates);
    expect(family('doctor.label.')).toEqual(tr.doctor.labels);
    expect(family('doctor.capability.')).toEqual(tr.doctor.capabilities);
    expect(family('doctor.missing.')).toEqual(tr.doctor.missingExplained);
  });

  it('names the buttons and states of both screens as the web page does', () => {
    const same: Record<string, string> = {
      'app.retry': tr.app.retry,
      'app.copy': tr.app.copy,
      'app.copied': tr.app.copied,
      'app.showDetails': tr.app.showDetails,
      'app.hideDetails': tr.app.hideDetails,
      'queue.loading': tr.queue.loading,
      'queue.emptyTitle': tr.queue.emptyTitle,
      'queue.emptyBody': tr.queue.emptyBody,
      'queue.reconnecting': tr.queue.reconnecting,
      'queue.cancel': tr.queue.cancel,
      'queue.retry': tr.queue.retry,
      'queue.remove': tr.queue.remove,
      'queue.removeHelp': tr.queue.removeHelp,
      'queue.reveal': tr.queue.reveal,
      'queue.usedSession': tr.queue.usedSession,
      'queue.usedSessionHelp': tr.queue.usedSessionHelp,
      'doctor.refresh': tr.doctor.refresh,
      'doctor.subtitle': tr.doctor.subtitle,
      'doctor.status.ok': tr.doctor.statusOk,
      'doctor.status.warn': tr.doctor.statusWarn,
      'doctor.status.error': tr.doctor.statusError,
      'doctor.checkStatus.ok': tr.doctor.checkOk,
      'doctor.checkStatus.warn': tr.doctor.checkWarn,
      'doctor.checkStatus.error': tr.doctor.checkError,
      'doctor.openFullDiskAccess': tr.doctor.openFullDiskAccess,
      'doctor.fixHint': tr.doctor.fixHint,
      'doctor.updateYtdlp': tr.doctor.updateYtdlp,
      'doctor.updating': tr.doctor.updating,
      'doctor.updateHelp': tr.doctor.updateHelp,
      'unit.bytes': tr.units.bytes,
      'unit.kib': tr.units.kib,
      'unit.mib': tr.units.mib,
      'unit.gib': tr.units.gib,
      'unit.tib': tr.units.tib,
    };
    expect(Object.fromEntries(Object.keys(same).map((key) => [key, native[key]]))).toEqual(same);
  });

  it('formats the same sentences', () => {
    expect((native['queue.eta'] ?? '').replace('%@', '3:00')).toBe(tr.queue.eta('3:00'));
    expect((native['queue.speed'] ?? '').replace('%@', '2 MB')).toBe(tr.queue.speed('2 MB'));
    expect((native['doctor.updated'] ?? '').replace('%@', 'a').replace('%@', 'b')).toBe(tr.doctor.updated('a', 'b'));
    expect((native['doctor.upToDate'] ?? '').replace('%@', 'a')).toBe(tr.doctor.upToDate('a'));
    expect((native['queue.warning.SUBTITLE_SKIPPED'] ?? '').replace('%@', 'tr')).toBe(tr.queue.warnings.SUBTITLE_SKIPPED?.('tr'));
    expect(Object.keys(family('queue.warning.'))).toEqual(Object.keys(tr.queue.warnings));
  });
});
