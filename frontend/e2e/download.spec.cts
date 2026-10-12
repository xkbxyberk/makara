import { execFileSync } from 'node:child_process';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/** Served by the app itself in fixture mode: real yt-dlp, real FFmpeg, no internet. */
const LOCAL = 'https://example.test/local-media';
const SHOTS = '../test-results/screenshots';

interface Stream {
  codec_type: string;
  codec_name: string;
  codec_tag_string?: string;
  tags?: { language?: string };
  disposition?: { default?: number; attached_pic?: number };
}

function ffprobe(file: string): Stream[] {
  const out = execFileSync('ffprobe', ['-v', 'error', '-print_format', 'json', '-show_streams', file]);
  return (JSON.parse(out.toString()) as { streams: Stream[] }).streams;
}

const of = (streams: Stream[], type: string) =>
  streams.filter((s) => s.codec_type === type && !s.disposition?.attached_pic);

async function inspectLocal(page: Page) {
  await page.goto('/');
  await page.getByLabel('Bağlantı').fill(LOCAL);
  await page.getByRole('main').getByRole('button', { name: 'İncele', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Local test clip' })).toBeVisible();
}

async function startDownload(page: Page): Promise<string> {
  const button = page.getByRole('button', { name: 'İndir', exact: true });
  await expect(button).toBeEnabled();
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/jobs') && r.request().method() === 'POST'),
    button.click(),
  ]);
  expect(response.status()).toBe(200);
  return ((await response.json()) as { id: string }).id;
}

async function waitDone(request: APIRequestContext, id: string): Promise<string[]> {
  let last = '';
  for (let i = 0; i < 300; i++) {
    const jobs = (await (await request.get('/api/jobs')).json()) as {
      id: string;
      status: string;
      output_files: string[];
      error_code: string | null;
    }[];
    const job = jobs.find((j) => j.id === id);
    last = JSON.stringify(job);
    if (job?.status === 'done') return job.output_files;
    if (job?.status === 'failed') throw new Error(`job failed: ${last}`);
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`job did not finish: ${last}`);
}

test('two clicks: paste, then Download, gives the archive default', async ({ page, request }) => {
  await inspectLocal(page);
  const summary = page.getByTestId('download-summary');
  await expect(summary).toContainText('360p · VP9');
  await expect(summary).toContainText('İngilizce (Orijinal)');
  await expect(summary).toContainText('Altyazı: Türkçe, İngilizce');
  await expect(page.getByTestId('download-filename')).toContainText(
    'Generic/VD Test Channel/2026-09-01 - Local test clip [localclip01].mkv',
  );
  await expect(page.getByTestId('download-size')).not.toContainText('Hesaplanıyor');

  const id = await startDownload(page);
  await expect(page.getByText('Kuyruğa eklendi.')).toBeVisible();
  const [file] = await waitDone(request, id);
  const streams = ffprobe(file!);
  expect(of(streams, 'video').map((s) => s.codec_name)).toEqual(['vp9']);
  expect(of(streams, 'audio').map((s) => s.tags?.language)).toEqual(['eng']);
  expect(of(streams, 'subtitle').map((s) => s.tags?.language)).toEqual(['tur', 'eng']);
});

test('quick choices: the video\'s own qualities, one click each, remembered per site', async ({
  page,
  request,
}) => {
  await inspectLocal(page);
  const quick = page.getByTestId('quick-choices');
  const row = (id: string) => quick.locator(`[data-offer-id="${id}"]`);
  // One row per quality the clip really has; today's default is the one checked.
  await expect(quick.getByRole('radio')).toHaveCount(2);
  await expect(row('v360-25-sdr')).toHaveAttribute('aria-checked', 'true');
  await expect(row('v360-25-sdr')).toContainText('VP9');

  // MP4 resolves each size for itself and says when one must be re-encoded.
  await page.getByRole('radio', { name: 'Uyumlu MP4' }).click();
  await expect(row('v360-25-sdr')).toContainText('Dönüştürülür');
  await expect(row('v240-25-sdr')).toContainText('H.264');
  await expect(row('v240-25-sdr')).not.toContainText('Dönüştürülür');

  // Audio only: the source's own streams are copied, MP3 is a conversion with no guessed size.
  await page.getByRole('radio', { name: 'Sadece ses' }).click();
  await expect(row('a-mp3')).toHaveAttribute('aria-checked', 'true'); // today's audio default
  await expect(row('a-m4a')).toContainText('Yeniden kodlamasız');
  await expect(row('a-opus')).toContainText('Yeniden kodlamasız');
  await expect(row('a-mp3')).toContainText('Dönüştürülür');
  await expect(row('a-mp3')).toContainText('boyut dönüştürünce belli olur');
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/quick-audio-light.png` });

  // One click sets the selection, and the plan follows.
  await page.getByRole('radio', { name: 'Arşiv MKV' }).click();
  await row('v240-25-sdr').click();
  await expect(row('v240-25-sdr')).toHaveAttribute('aria-checked', 'true');
  const summary = page.getByTestId('download-summary');
  await expect(summary).toContainText('240p · H.264');
  await expect(summary).toContainText('İngilizce (Orijinal)'); // still the original audio
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/quick-video-light.png` });
  const id = await startDownload(page);
  const [file] = await waitDone(request, id);
  expect(of(ffprobe(file!), 'video').map((s) => s.codec_name)).toEqual(['h264']);

  // The next video from this site opens on the same choice.
  await page.getByRole('main').getByRole('button', { name: 'İncele', exact: true }).click();
  await expect(row('v240-25-sdr')).toHaveAttribute('aria-checked', 'true');
  await expect(row('v240-25-sdr')).toContainText('bu sitede son seçimin');
  await expect(summary).toContainText('240p · H.264');
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/quick-video-dark.png` });
});

test('downloading the untouched default remembers nothing', async ({ page, request }) => {
  await inspectLocal(page);
  const id = await startDownload(page);
  await waitDone(request, id);
  await page.getByRole('main').getByRole('button', { name: 'İncele', exact: true }).click();
  const quick = page.getByTestId('quick-choices');
  await expect(quick.locator('[data-offer-id="v360-25-sdr"]')).toHaveAttribute('aria-checked', 'true');
  await expect(quick).not.toContainText('bu sitede son seçimin');
  expect(await page.evaluate(() => localStorage.getItem('vd-quick-rules'))).toBeNull();
});

test('track picker: 1 video + 2 audio languages + 2 subtitles into one tagged MKV', async ({
  page,
  request,
}) => {
  await inspectLocal(page);
  await page.getByRole('button', { name: 'Parçaları seç' }).click();
  const picker = page.getByTestId('track-picker');
  await picker.locator('label.pick-row', { hasText: 'v-vp9' }).locator('input').check();
  await picker.getByRole('checkbox', { name: 'Türkçe', exact: true }).check();
  await expect(page.getByTestId('download-summary')).toContainText('Türkçe (Dublaj)');

  const id = await startDownload(page);
  const [file] = await waitDone(request, id);
  const streams = ffprobe(file!);
  const audio = of(streams, 'audio');
  expect(audio.map((s) => s.tags?.language)).toEqual(['eng', 'tur']);
  expect(audio.map((s) => s.disposition?.default)).toEqual([1, 0]);
  expect(of(streams, 'subtitle').map((s) => s.tags?.language).sort()).toEqual(['eng', 'tur']);
});

test('compatible MP4: a VP9 pick is flagged, then re-encoded to H.264/AAC', async ({
  page,
  request,
}) => {
  await inspectLocal(page);
  await page.getByRole('radio', { name: 'Uyumlu MP4' }).click();
  // The default is already the H.264 format, so nothing needs converting.
  await expect(page.getByTestId('download-summary')).toContainText('240p · H.264');
  await expect(page.getByText('yeniden kodlanacak')).toHaveCount(0);

  await page.getByRole('button', { name: 'Parçaları seç' }).click();
  await page.getByTestId('track-picker').locator('label.pick-row', { hasText: 'v-vp9' }).locator('input').check();
  await expect(page.getByText(/VP9 görüntü QuickTime’da oynamaz; H.264’e yeniden kodlanacak/)).toBeVisible();
  await expect(page.getByText(/240p H.264 sürümünü seçebilirsin/)).toBeVisible();

  const id = await startDownload(page);
  const [file] = await waitDone(request, id);
  expect(file).toMatch(/\.mp4$/);
  const streams = ffprobe(file!);
  const [video] = of(streams, 'video');
  expect(video?.codec_name).toBe('h264');
  expect(video?.codec_tag_string).toBe('avc1');
  expect(of(streams, 'audio').map((s) => s.codec_name)).toEqual(['aac']);
});

test('audio only: MP3 with embedded cover art', async ({ page, request }) => {
  await inspectLocal(page);
  await page.getByRole('radio', { name: 'Sadece ses' }).click();
  await expect(page.getByTestId('download-filename')).toContainText('.mp3');
  const id = await startDownload(page);
  const [file] = await waitDone(request, id);
  const streams = ffprobe(file!);
  expect(of(streams, 'audio').map((s) => s.codec_name)).toEqual(['mp3']);
  expect(streams.filter((s) => s.disposition?.attached_pic === 1)).toHaveLength(1);
});

test('a template that escapes the download folder blocks the download', async ({ page }) => {
  await inspectLocal(page);
  await page.getByRole('button', { name: 'Parçaları seç' }).click();
  await page.getByLabel('Dosya adı', { exact: true }).fill('../../%(title)s.%(ext)s');
  await expect(page.getByTestId('download-filename')).toContainText('İndirme klasörünün dışına yazılamaz');
  await expect(page.getByRole('button', { name: 'İndir', exact: true })).toBeDisabled();
});

test('the queue shows the finished job, its file, and removes it without touching media', async ({
  page,
  request,
}) => {
  await inspectLocal(page);
  await page.getByRole('radio', { name: 'Sadece ses' }).click();
  const id = await startDownload(page);
  const [file] = await waitDone(request, id);
  await page.getByRole('button', { name: 'İndirmeleri aç' }).click();
  const row = page.getByTestId('job').filter({ has: page.locator(`text=${file!.split('/').pop()}`) });
  await expect(row).toContainText('Tamamlandı');
  await expect(row.getByRole('button', { name: 'Finder’da göster' })).toBeVisible();
  await row.getByRole('button', { name: 'Listeden kaldır' }).click();
  await expect(row).toHaveCount(0);
  expect(ffprobe(file!).length).toBeGreaterThan(0); // the file itself is untouched
});

test('screenshots: download panel and queue in light, dark and narrow', async ({ page, request }) => {
  await page.addInitScript(() => localStorage.setItem('vd-theme', 'light'));
  await inspectLocal(page);
  await page.getByRole('button', { name: 'Parçaları seç' }).click();
  await page.getByRole('radio', { name: 'Uyumlu MP4' }).click();
  await page.getByTestId('track-picker').locator('label.pick-row', { hasText: 'v-vp9' }).locator('input').check();
  await expect(page.getByText(/yeniden kodlanacak/)).toBeVisible();
  const panel = page.locator('section.panel', { hasText: 'Kaydedileceği yer' });
  const shoot = async (name: string) => {
    await panel.evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await page.screenshot({ animations: 'disabled', path: `${SHOTS}/${name}.png` });
  };
  await shoot('download-light');
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await shoot('download-dark');
  await page.setViewportSize({ width: 420, height: 900 });
  await shoot('download-narrow');

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
  const id = await startDownload(page);
  await waitDone(request, id);
  await page.getByRole('navigation').getByRole('button', { name: /^İndirmeler/ }).click();
  await expect(page.getByTestId('job').first()).toBeVisible();
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/queue-light.png` });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/queue-dark.png` });
  await page.setViewportSize({ width: 420, height: 900 });
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/queue-narrow.png` });
});

test('⌘↵ downloads from Inspect only, once per press', async ({ page }) => {
  const posts: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/api/jobs')) posts.push(r.url());
  });
  await inspectLocal(page);
  await expect(page.getByRole('button', { name: 'İndir', exact: true })).toBeEnabled();
  await page.keyboard.press('Meta+Enter');
  await expect.poll(() => posts.length).toBe(1);

  // On another screen the shortcut must do nothing.
  await page.getByRole('navigation').getByRole('button', { name: 'Kütüphane' }).click();
  await page.keyboard.press('Meta+Enter');
  await page.waitForTimeout(500);
  expect(posts).toHaveLength(1);
});
