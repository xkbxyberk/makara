// The Safari extension's shared logic (../extension/shared.js), loaded as Safari loads it: a
// plain script that installs globalThis.VD. Run with `node --test` (no dependencies).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import '../extension/shared.js';

const VD = globalThis.VD;

test('keys remembered choices by site, like the app does', () => {
  assert.equal(VD.siteOf('https://www.youtube.com/watch?v=x'), 'youtube.com');
  assert.equal(VD.siteOf('https://youtu.be/x'), 'youtube.com');
  assert.equal(VD.siteOf('https://music.youtube.com/watch?v=x'), 'youtube.com');
  assert.equal(VD.siteOf('https://m.vimeo.com/1'), 'vimeo.com');
  assert.equal(VD.siteOf('about:blank'), null);
  assert.equal(VD.siteOf('file:///etc/passwd'), null);
  assert.equal(VD.isWebPage('safari-web-extension://abc/popup.html'), false);
  // This Mac and the local network are never pages to inspect (as LocalHost.swift).
  for (const url of ['http://127.0.0.1:8787/api/jobs', 'http://localhost/', 'http://192.168.1.1/', 'http://10.1.2.3/',
    'http://172.16.0.1/', 'http://169.254.169.254/', 'http://[::1]/', 'http://nas.local/', 'http://intranet/']) {
    assert.equal(VD.isWebPage(url), false, url);
  }
  assert.equal(VD.isWebPage('https://172.32.0.1/'), true);
});

test('accepts only well-formed remembered choices', () => {
  assert.equal(VD.isRule({ kind: 'video', height: 720, output: 'compat_mp4' }), true);
  assert.equal(VD.isRule({ kind: 'audio', format: 'm4a' }), true);
  assert.equal(VD.isRule({ kind: 'audio', format: 'flac' }), false);
  assert.equal(VD.isRule({ kind: 'video', output: 'avi' }), false);
  assert.equal(VD.isRule(null), false);
  assert.equal(VD.isRule({ kind: 'video', height: -1 }), false); // would make every inspect fail
  assert.equal(VD.isRule({ kind: 'video', height: 1e9 }), false);
  assert.equal(VD.isRule({ kind: 'video', hdr: 'yes' }), false);
});

test('lights the icon for supported pages and pages with media, not for lists or nothing', () => {
  assert.equal(VD.iconState(null, true), 'offline');
  assert.equal(VD.iconState({ supported: true, kind: 'video' }, false), 'ready');
  assert.equal(VD.iconState({ supported: true, kind: 'playlist' }, false), 'list');
  assert.equal(VD.iconState({ supported: false, kind: null }, true), 'ready');
  assert.equal(VD.iconState({ supported: false, kind: null }, false), 'none');
});

test('formats like the app and names the heaviest step', () => {
  // The popup and the app (Format.bytes) show a size the same way, to the character.
  const sizes = {
    0: '0 B', 512: '512 B', 1023: '1023 B', 1024: '1.0 KB', 184_320: '180 KB', 188_621: '184 KB',
    25_366_777: '24.2 MB', 906_000_000: '864 MB', 5_400_000_000: '5.0 GB',
  };
  for (const [bytes, text] of Object.entries(sizes)) assert.equal(VD.formatBytes(Number(bytes)), text);
  assert.equal(VD.formatBytes(null), '');
  assert.equal(VD.formatDuration(1541), '25:41');
  assert.equal(VD.formatDuration(3725), '1:02:05');
  assert.equal(VD.inspectLink('https://x.test/a?b=1&c=2'), 'makara://inspect?url=https%3A%2F%2Fx.test%2Fa%3Fb%3D1%26c%3D2');
});

test('finds the one address of the post a video belongs to', () => {
  const cases = {
    'https://x.com/nasa/status/1850123456789012345/video/1': 'https://x.com/nasa/status/1850123456789012345',
    '/nasa/status/1850123456789012345/photo/1': 'https://x.com/nasa/status/1850123456789012345',
    'https://twitter.com/nasa/status/185?s=20': 'https://x.com/nasa/status/185',
    'https://www.instagram.com/reels/C9xYz12AbCd/': 'https://www.instagram.com/reel/C9xYz12AbCd/',
    'https://www.instagram.com/someone/p/C9xYz12AbCd/?img_index=1': 'https://www.instagram.com/p/C9xYz12AbCd/',
    'https://old.reddit.com/r/videos/comments/1abcde/a_title/': 'https://www.reddit.com/r/videos/comments/1abcde/',
    'https://www.tiktok.com/@some.one/video/7421234567890123456?lang=tr': 'https://www.tiktok.com/@some.one/video/7421234567890123456',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1&t=42': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ?t=1': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://m.youtube.com/shorts/dQw4w9WgXcQ': 'https://www.youtube.com/shorts/dQw4w9WgXcQ',
    'https://vimeo.com/123456#t=30s': 'https://vimeo.com/123456',
  };
  for (const [href, expected] of Object.entries(cases)) assert.equal(VD.permalink(href, 'https://x.com/home'), expected, href);
  // Links that are not a post: X's own pages, a profile, a YouTube page without a video.
  for (const href of ['https://x.com/home', 'https://x.com/nasa', 'https://www.instagram.com/someone/',
    'https://www.youtube.com/@channel', 'https://www.youtube.com/watch?v=short', 'javascript:alert(1)', 'blob:https://x.com/1']) {
    assert.equal(VD.permalink(href, 'https://x.com/home'), null, href);
  }
});
