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

  it('says what İncele and the download panel say', () => {
    const strings = (table: Record<string, unknown>) =>
      Object.fromEntries(Object.entries(table).filter(([, value]) => typeof value === 'string'));
    expect(family('inspect.')).toEqual({
      ...strings(tr.inspect),
      subTranslatedCount: '%d makine çevirisini göster',
      subFrom: 'kaynak: %@',
      playlistBody: tr.inspect.playlistBody(0).replace('0', '%d'),
      views: '%@ görüntülenme',
    });
    const download = Object.fromEntries(Object.entries(family('download.')).filter(([key]) => !key.includes('.')));
    // ⌘↵ is the native button's own key equivalent; the web page prints it as text.
    const plainDownload = Object.fromEntries(Object.entries(strings(tr.download)).filter(([key]) => key !== 'shortcut'));
    expect(download).toEqual({ ...plainDownload, subtitlesSummary: 'Altyazı: %@' });
    expect(family('download.quick.format.')).toEqual(tr.download.quick.formats);
    const quick = Object.fromEntries(Object.entries(family('download.quick.')).filter(([key]) => !key.includes('.')));
    expect(quick).toEqual({ ...strings(tr.download.quick), fps: '%@ fps' });
    expect(family('download.modeHelp.')).toEqual(tr.download.modeHelp);
    expect(family('download.section.')).toEqual(tr.download.sections);
    expect(family('download.extra.')).toEqual(tr.download.extras);
    expect(family('download.audioCodec.')).toEqual(tr.download.audioCodecs);
    expect(family('term.', '.label')).toEqual(Object.fromEntries(Object.entries(tr.terms).map(([k, v]) => [k, v.label])));
    expect(family('term.', '.body')).toEqual(Object.fromEntries(Object.entries(tr.terms).map(([k, v]) => [k, v.body])));
    expect(family('role.')).toEqual(tr.roles);
    expect(family('roleHelp.')).toEqual(tr.roleHelp);
    expect(family('codec.')).toEqual(tr.codecs);
    expect(family('inspectWarning.')).toEqual(tr.warnings);
    expect(family('clipboard.')).toEqual(tr.clipboard);
    expect(family('table.')).toEqual(tr.table);
    expect(tr.inspect.subTranslatedCount(7)).toBe('7 makine çevirisini göster');
    expect(tr.inspect.subFrom('X')).toBe('kaynak: X');
    expect(tr.inspect.views('X')).toBe('X görüntülenme');
    expect(tr.download.subtitlesSummary('X')).toBe('Altyazı: X');
    expect(tr.download.quick.fps(30)).toBe('30 fps');
  });

  it('says what Kütüphane says', () => {
    const strings = (table: Record<string, unknown>) =>
      Object.fromEntries(Object.entries(table).filter(([, value]) => typeof value === 'string'));
    const library = Object.fromEntries(Object.entries(family('library.')).filter(([key]) => !key.includes('.')));
    expect(library).toEqual({
      ...strings(tr.library),
      scanResult: '%d öğe denetlendi · %d dosyanın yeni yeri bulundu · %d geri geldi · %d eksik',
      summary: '%d öğe · %@',
      summaryMissing: '%d öğe · %@ · %d eksik',
    });
    expect(family('library.sort.')).toEqual(tr.library.sorts);
    expect(family('library.kind.')).toEqual(tr.library.kinds);
    const counts = { checked: 4, repaired: 1, restored: 0, missing: 2 };
    expect(tr.library.scanResult(counts)).toBe('4 öğe denetlendi · 1 dosyanın yeni yeri bulundu · 0 geri geldi · 2 eksik');
    expect(tr.library.summary(3, '1.5 MB', 0)).toBe('3 öğe · 1.5 MB');
    expect(tr.library.summary(3, '1.5 MB', 1)).toBe('3 öğe · 1.5 MB · 1 eksik');
    expect(native['libraryNative.trashBodyOne']).toBe(tr.library.trashBody(1));
    expect((native['libraryNative.trashBodyMany'] ?? '').replace('%d', '3')).toBe(tr.library.trashBody(3));
  });

  it('says what Stüdyo says', () => {
    const strings = (table: Record<string, unknown>) =>
      Object.fromEntries(Object.entries(table).filter(([, value]) => typeof value === 'string'));
    const top = (prefix: string) => Object.fromEntries(Object.entries(family(prefix)).filter(([key]) => !key.includes('.')));
    const st = tr.studio;
    expect(top('studio.')).toEqual(strings(st));
    expect(family('studio.streamKinds.')).toEqual(st.streamKinds);
    expect(family('studio.tabs.')).toEqual(st.tabs);
    expect(family('studio.outputSuffix.')).toEqual(st.outputSuffix);
    expect(family('studio.steps.')).toEqual(st.steps);
    expect(top('studio.audio.')).toEqual(st.audio);
    expect(top('studio.trim.')).toEqual(st.trim);
    expect(top('studio.remux.')).toEqual({ ...strings(st.remux), fromExtra: 'ek: %@' });
    expect(st.remux.fromExtra('x.m4a')).toBe('ek: x.m4a');
    expect(top('studio.subtitle.')).toEqual(strings(st.subtitle));
    expect(family('studio.subtitle.actions.')).toEqual(st.subtitle.actions);
    expect(family('studio.terms.', '.label')).toEqual(Object.fromEntries(Object.entries(st.terms).map(([k, v]) => [k, v.label])));
    expect(family('studio.terms.', '.body')).toEqual(Object.fromEntries(Object.entries(st.terms).map(([k, v]) => [k, v.body])));
  });

  it('says what Ayarlar says', () => {
    const strings = (table: Record<string, unknown>) =>
      Object.fromEntries(Object.entries(table).filter(([, value]) => typeof value === 'string'));
    const top = Object.fromEntries(Object.entries(family('settings.')).filter(([key]) => !key.includes('.')));
    // "unavailable" is the window's own (before the server answers); everything else is shared.
    const { unavailable: _native, ...shared } = top;
    expect(_native).toBeTruthy();
    expect(shared).toEqual(strings(tr.settings));
    expect(family('settings.sample.')).toEqual(tr.settings.sample);
  });

  it('words every Stüdyo notice as the web page does', () => {
    const render = (template: string, params: Record<string, unknown>) =>
      template.replace(/\{(\w+)(\^)?(?:\|([^}]*))?\}/g, (_, name: string, upper?: string, fallback?: string) => {
        const value = params[name];
        const text = value === undefined || value === null ? (fallback ?? '') : String(value);
        return upper ? text.toUpperCase() : text;
      });
    const notices = family('studio.notice.');
    expect(Object.keys(notices).sort()).toEqual(Object.keys(tr.studio.notices).sort());
    const full = { target: -16, codec: 'opus', start: 1.5, end: 3, count: 2, requested: 1.5, actual: 1, charset: 'cp1254' };
    for (const [code, entry] of Object.entries(tr.studio.notices)) {
      const web = typeof entry === 'function' ? entry(full) : entry;
      expect(render(notices[code] ?? '', full), code).toBe(web);
    }
  });

  /** The native templates (`{codec|Bu}`, `{target^}`) render what the web's functions do. */
  it('words every plan notice as the web page does, with and without params', () => {
    const render = (template: string, params: Record<string, unknown>) =>
      template.replace(/\{(\w+)(\^)?(?:\|([^}]*))?\}/g, (_, name: string, upper?: string, fallback?: string) => {
        const value = params[name];
        const text = value === undefined || value === null ? (fallback ?? '') : String(value);
        return upper ? text.toUpperCase() : text;
      });
    const samples: Record<string, unknown>[] = [{}, { codec: 'AV1', height: 1080, format_id: '137', target: 'mp3' }];
    const notices = family('download.notice.');
    expect(Object.keys(notices).sort()).toEqual(Object.keys(tr.download.notices).sort());
    for (const [code, entry] of Object.entries(tr.download.notices)) {
      for (const params of samples) {
        const web = typeof entry === 'function' ? entry(params) : entry;
        expect(render(notices[code] ?? '', params), code).toBe(web);
      }
    }
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
      'unit.fps': tr.units.fps,
      'unit.kbps': tr.units.kbps,
      'unit.mbps': tr.units.mbps,
      'unit.khz': tr.units.khz,
      'app.showMore': tr.app.showMore,
      'app.showLess': tr.app.showLess,
      'app.unknown': tr.app.unknown,
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
