import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/**
 * The Safari extension's popup, against the real fixture-mode backend. Safari cannot be
 * scripted, so the page is served by the test server and `browser.*` is replaced by a stand-in
 * that only carries messages: the relay's allowlist itself is tested in Swift (RelayTests).
 */
const LOCAL = 'https://example.test/local-media';
const SHOTS = '../../test-results/screenshots';
const messages = JSON.parse(
  readFileSync(path.resolve(__dirname, '../extension/_locales/tr/messages.json'), 'utf8'),
) as Record<string, { message: string }>;

interface Options {
  url?: string;
  title?: string;
  rules?: Record<string, unknown>;
  offline?: boolean;
}

async function openPopup(page: Page, { url = LOCAL, title = 'Local test clip', rules, offline = false }: Options = {}) {
  await page.addInitScript(
    ({ messages, tab, rules, offline }) => {
      const w = window as unknown as Record<string, unknown>;
      const store: Record<string, unknown> = rules ? { quickRules: rules } : {};
      const opened: string[] = [];
      const sent: unknown[] = [];
      w.__opened = opened;
      w.__sent = sent;
      w.__store = store;
      w.__offline = offline;
      w.browser = {
        runtime: {
          sendMessage: async () => undefined,  // "the menu is up", for the background page
          sendNativeMessage: async (_id: string, msg: { type: string; url?: string; path?: string; method?: string; query?: Record<string, string>; body?: unknown }) => {
            sent.push(msg);
            if (msg.type === 'open') {
              opened.push(msg.url!);
              return { ok: true };
            }
            if (w.__offline) return { ok: false, offline: true };
            const query = msg.query ? `?${new URLSearchParams(msg.query)}` : '';
            const response = await fetch(`/${msg.path}${query}`, {
              method: msg.method ?? 'GET',
              headers: { 'Content-Type': 'application/json' },
              body: msg.body ? JSON.stringify(msg.body) : undefined,
            });
            let json: unknown = null;
            try {
              json = await response.json();
            } catch {
              json = null;
            }
            // Parallel tests share the server: remember which job *this* popup queued.
            if (msg.path === 'api/quick' && response.ok) w.__jobId = (json as { job: { id: string } }).job.id;
            return { ok: response.ok, status: response.status, json };
          },
        },
        tabs: { query: async () => [tab] },
        storage: {
          local: {
            get: async (key: string) => ({ [key]: store[key] }),
            set: async (items: Record<string, unknown>) => Object.assign(store, items),
          },
        },
        i18n: {
          getMessage: (key: string, subs: string[] = []) =>
            (messages[key]?.message ?? '').replace(/\$(\d)/g, (_, i: string) => subs[Number(i) - 1] ?? ''),
        },
      };
      w.close = () => undefined;
    },
    { messages, tab: { url, title }, rules, offline },
  );
  await page.setViewportSize({ width: 380, height: 640 });
  await page.goto('/__test/extension/popup.html');
}

const row = (page: Page, id: string) => page.locator(`.row[data-offer-id="${id}"]`);

async function queuedJob(page: Page, request: APIRequestContext) {
  const id = await page.evaluate(() => (window as unknown as { __jobId: string }).__jobId);
  const jobs = (await (await request.get('/api/jobs')).json()) as {
    id: string;
    status: string;
    selection: { video_format_id: string | null; audio_format_ids: string[]; subtitle_keys: string[]; mode: string };
  }[];
  return jobs.find((job) => job.id === id)!;
}

test('popup: the video\'s own choices, one click, progress to done, the choice remembered', async ({ page, request }) => {
  await openPopup(page);
  await expect(page.getByRole('heading', { name: 'Local test clip' })).toBeVisible();
  await expect(row(page, 'v360-25-sdr')).toHaveAttribute('aria-checked', 'true'); // today's default
  await expect(row(page, 'v360-25-sdr')).toContainText('VP9');
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/extension-popup-light.png` });

  await row(page, 'v240-25-sdr').click();
  await expect(row(page, 'v240-25-sdr')).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'İndir', exact: true }).click();
  await expect(page.getByText('Tamamlandı')).toBeVisible({ timeout: 30_000 });
  const job = await queuedJob(page, request);
  expect(job.status).toBe('done');
  expect(job.selection.video_format_id).toBe('v-h264');
  expect(await page.evaluate(() => (window as unknown as { __store: Record<string, unknown> }).__store.quickRules)).toEqual({
    'example.test': { kind: 'video', height: 240, fps: 25, hdr: false, output: 'mkv' },
  });

  await page.getByRole('button', { name: 'İndirmeler’de göster' }).click();
  expect(await page.evaluate(() => (window as unknown as { __opened: string[] }).__opened)).toContain(
    'makara://show?route=download',
  );
});

test('popup: the remembered choice for the site is preselected', async ({ page }) => {
  await openPopup(page, { rules: { 'example.test': { kind: 'audio', format: 'm4a' } } });
  await expect(page.getByRole('radio', { name: 'Sadece ses' })).toHaveAttribute('aria-checked', 'true');
  await expect(row(page, 'a-m4a')).toHaveAttribute('aria-checked', 'true');
  await expect(row(page, 'a-m4a')).toContainText('bu sitede son seçimin');
  await expect(row(page, 'a-m4a')).toContainText('Yeniden kodlamasız');
  await expect(row(page, 'a-mp3')).toContainText('dönüştürünce belli olur');
});

test('popup: MP4 says which sizes are re-encoded; language and subtitles reach the job', async ({ page, request }) => {
  await openPopup(page);
  await page.getByRole('radio', { name: 'Uyumlu MP4' }).click();
  await expect(row(page, 'v360-25-sdr')).toContainText('Dönüştürülür');
  await expect(row(page, 'v240-25-sdr')).not.toContainText('Dönüştürülür');
  await page.getByLabel('Ses').selectOption({ label: 'Almanca (Dublaj)' });
  await page.getByLabel('Altyazı').selectOption({ label: 'Altyazısız' });
  await page.getByRole('button', { name: 'İndir', exact: true }).click();
  await expect(page.getByText('Tamamlandı')).toBeVisible({ timeout: 30_000 });
  const job = await queuedJob(page, request);
  expect(job.selection.mode).toBe('compat_mp4');
  expect(job.selection.audio_format_ids).toEqual(['a-de-m4a']);
  expect(job.selection.subtitle_keys).toEqual([]);
});

test('popup: an untouched default downloads but remembers nothing', async ({ page }) => {
  await openPopup(page);
  await expect(row(page, 'v360-25-sdr')).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'İndir', exact: true }).click();
  await expect(page.getByText('Tamamlandı')).toBeVisible({ timeout: 30_000 });
  expect(await page.evaluate(() => (window as unknown as { __store: Record<string, unknown> }).__store.quickRules)).toBeUndefined();
});

test('popup: when the app is closed it offers to open it, then carries on', async ({ page }) => {
  await openPopup(page, { offline: true });
  await expect(page.getByText('Makara açık değil')).toBeVisible();
  await page.evaluate(() => ((window as unknown as { __offline: boolean }).__offline = false));
  await page.getByRole('button', { name: 'Makara’yı aç' }).click();
  expect(await page.evaluate(() => (window as unknown as { __opened: string[] }).__opened)).toEqual(['makara://show']);
  await expect(page.getByRole('heading', { name: 'Local test clip' })).toBeVisible({ timeout: 10_000 });
});

test('popup: a list opens in the app; an unknown site and a non-web tab are explained', async ({ page, browser }) => {
  await openPopup(page, { url: 'https://www.youtube.com/playlist?list=PL123', title: 'A list' });
  await expect(page.getByText('Bu bir liste')).toBeVisible();
  await page.getByRole('button', { name: 'Uygulamada incele' }).click();
  expect(await page.evaluate(() => (window as unknown as { __opened: string[] }).__opened)).toEqual([
    'makara://inspect?url=https%3A%2F%2Fwww.youtube.com%2Fplaylist%3Flist%3DPL123',
  ]);

  const second = await browser.newPage();
  await openPopup(second, { url: 'https://unknown.example.com/watch', title: 'Elsewhere' });
  await expect(second.getByText('Bu site desteklenmiyor.')).toBeVisible();
  await second.close();

  const third = await browser.newPage();
  await openPopup(third, { url: 'about:blank', title: '' });
  await expect(third.getByText('Bu sekmede incelenecek bir web sayfası yok.')).toBeVisible();
  // Nothing was asked of the app for a page that is not a web page.
  expect(await third.evaluate(() => (window as unknown as { __sent: unknown[] }).__sent)).toEqual([]);
  await third.close();
});

test('screenshots: popup in dark', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await openPopup(page, { rules: { 'example.test': { kind: 'video', height: 240, output: 'compat_mp4' } } });
  await expect(row(page, 'v240-25-sdr')).toHaveAttribute('aria-checked', 'true');
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/extension-popup-dark.png` });
});

const storedRules = (page: Page) =>
  page.evaluate(() => (window as unknown as { __store: Record<string, unknown> }).__store.quickRules);
const quickCalls = (page: Page) =>
  page.evaluate(() => (window as unknown as { __sent: { path?: string }[] }).__sent.filter((m) => m.path === 'api/quick').length);

test('popup: a double click queues one download', async ({ page }) => {
  await openPopup(page);
  await expect(row(page, 'v360-25-sdr')).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'İndir', exact: true }).dblclick();
  await expect(page.getByText('Tamamlandı')).toBeVisible({ timeout: 30_000 });
  expect(await quickCalls(page)).toBe(1);
});

test('popup: a remembered choice is never lowered by a video that cannot meet it', async ({ page }) => {
  const rule = { kind: 'video', height: 1080, fps: 30, hdr: false, output: 'mkv' };
  await openPopup(page, { rules: { 'example.test': rule } });
  await expect(row(page, 'v360-25-sdr')).toHaveAttribute('aria-checked', 'true'); // the nearest it has
  await expect(row(page, 'v360-25-sdr')).not.toContainText('bu sitede son seçimin'); // not the remembered one
  await page.getByRole('button', { name: 'İndir', exact: true }).click();
  await expect(page.getByText('Tamamlandı')).toBeVisible({ timeout: 30_000 });
  expect(await storedRules(page)).toEqual({ 'example.test': rule });
});

test('popup: a click followed by another output is not remembered', async ({ page }) => {
  await openPopup(page);
  await row(page, 'v240-25-sdr').click();
  await page.getByRole('radio', { name: 'Sadece ses' }).click(); // now on the default audio row
  await page.getByRole('button', { name: 'İndir', exact: true }).click();
  await expect(page.getByText('Tamamlandı')).toBeVisible({ timeout: 30_000 });
  expect(await storedRules(page)).toBeUndefined();
});

test('popup: a page on this Mac or the local network is never sent to the app', async ({ page }) => {
  await openPopup(page, { url: 'http://192.168.1.1/admin', title: 'Router' });
  await expect(page.getByText('Bu sekmede incelenecek bir web sayfası yok.')).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __sent: unknown[] }).__sent)).toEqual([]);
});
