import { beforeAll, describe, expect, it } from 'vitest';
import { formatBytes } from './lib/format';

/** The Safari extension's shared logic (macos/extension/shared.js), loaded as Safari loads it. */
interface VDShared {
  siteOf(url: string): string | null;
  isWebPage(url: string): boolean;
  isRule(rule: unknown): boolean;
  iconState(supports: { supported: boolean; kind: string | null } | null, media: boolean): string;
  formatBytes(bytes: number | null): string;
  formatDuration(seconds: number): string;
  inspectLink(url: string): string;
}

let VD: VDShared;

beforeAll(async () => {
  // @ts-expect-error -- a plain script with no types; it installs globalThis.VD
  await import('../../macos/extension/shared.js');
  VD = (globalThis as unknown as { VD: VDShared }).VD;
});

describe('extension shared logic', () => {
  it('keys remembered choices by site, like the app does', () => {
    expect(VD.siteOf('https://www.youtube.com/watch?v=x')).toBe('youtube.com');
    expect(VD.siteOf('https://youtu.be/x')).toBe('youtube.com');
    expect(VD.siteOf('https://music.youtube.com/watch?v=x')).toBe('youtube.com');
    expect(VD.siteOf('https://m.vimeo.com/1')).toBe('vimeo.com');
    expect(VD.siteOf('about:blank')).toBeNull();
    expect(VD.siteOf('file:///etc/passwd')).toBeNull();
    expect(VD.isWebPage('safari-web-extension://abc/popup.html')).toBe(false);
    // This Mac and the local network are never pages to inspect (as LocalHost.swift).
    for (const url of ['http://127.0.0.1:8787/api/jobs', 'http://localhost/', 'http://192.168.1.1/', 'http://10.1.2.3/',
      'http://172.16.0.1/', 'http://169.254.169.254/', 'http://[::1]/', 'http://nas.local/', 'http://intranet/']) {
      expect(VD.isWebPage(url)).toBe(false);
    }
    expect(VD.isWebPage('https://172.32.0.1/')).toBe(true);
  });

  it('accepts only well-formed remembered choices', () => {
    expect(VD.isRule({ kind: 'video', height: 720, output: 'compat_mp4' })).toBe(true);
    expect(VD.isRule({ kind: 'audio', format: 'm4a' })).toBe(true);
    expect(VD.isRule({ kind: 'audio', format: 'flac' })).toBe(false);
    expect(VD.isRule({ kind: 'video', output: 'avi' })).toBe(false);
    expect(VD.isRule(null)).toBe(false);
    expect(VD.isRule({ kind: 'video', height: -1 })).toBe(false); // would make every inspect fail
    expect(VD.isRule({ kind: 'video', height: 1e9 })).toBe(false);
    expect(VD.isRule({ kind: 'video', hdr: 'yes' })).toBe(false);
  });

  it('lights the icon for supported pages and pages with media, not for lists or nothing', () => {
    expect(VD.iconState(null, true)).toBe('offline');
    expect(VD.iconState({ supported: true, kind: 'video' }, false)).toBe('ready');
    expect(VD.iconState({ supported: true, kind: 'playlist' }, false)).toBe('list');
    expect(VD.iconState({ supported: false, kind: null }, true)).toBe('ready');
    expect(VD.iconState({ supported: false, kind: null }, false)).toBe('none');
  });

  it('formats like the app and names the heaviest step', () => {
    // The popup and the app show a size the same way, to the character.
    for (const bytes of [0, 512, 1023, 1024, 184_320, 188_621, 25_366_777, 906_000_000, 5_400_000_000]) {
      expect(VD.formatBytes(bytes)).toBe(formatBytes(bytes));
    }
    expect(VD.formatBytes(null)).toBe('');
    expect(VD.formatDuration(1541)).toBe('25:41');
    expect(VD.formatDuration(3725)).toBe('1:02:05');
    expect(VD.inspectLink('https://x.test/a?b=1&c=2')).toBe('videodownloader://inspect?url=https%3A%2F%2Fx.test%2Fa%3Fb%3D1%26c%3D2');
  });
});
