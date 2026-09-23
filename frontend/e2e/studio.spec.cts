import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const MEDIA = path.resolve(__dirname, '../../tests/fixtures/media');
const SHOTS = '../test-results/screenshots';

/** A private folder per test, outside the download folder: outputs must land next to the source. */
function workspace(name: string): string {
  const dir = path.resolve(__dirname, `../../test-results/e2e-studio/${name}-${Date.now()}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

function probe(file: string): { duration: number; streams: { codec_type: string; codec_name: string; tags?: { language?: string } }[] } {
  const out = execFileSync('ffprobe', ['-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', file]);
  const data = JSON.parse(out.toString()) as { format: { duration: string }; streams: never[] };
  return { duration: Number(data.format.duration), streams: data.streams };
}

async function openFile(page: Page, file: string) {
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'Stüdyo' }).click();
  await page.getByLabel('Dosya yolu').fill(file);
  await page.getByRole('button', { name: 'Aç', exact: true }).click();
  await expect(page.getByTestId('studio-source')).toContainText(path.basename(file));
}

async function runAndWait(page: Page, request: APIRequestContext): Promise<string[]> {
  const button = page.getByRole('button', { name: 'Çalıştır' });
  await expect(button).toBeEnabled();
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/studio/jobs') && r.request().method() === 'POST'),
    button.click(),
  ]);
  const { id } = (await response.json()) as { id: string };
  await expect(page.getByText('Kuyruğa eklendi.')).toBeVisible();
  for (let i = 0; i < 300; i++) {
    const jobs = (await (await request.get('/api/jobs')).json()) as { id: string; status: string; output_files: string[]; error_raw: string }[];
    const job = jobs.find((j) => j.id === id);
    if (job?.status === 'failed') throw new Error(`studio job failed: ${job.error_raw}`);
    if (job?.status === 'done') return job.output_files;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('studio job did not finish');
}

test('lossless trim of a local file, verified with ffprobe', async ({ page, request }) => {
  const dir = workspace('trim');
  const clip = path.join(dir, 'clip.mp4');
  copyFileSync(path.join(MEDIA, 'video_h264.mp4'), clip);
  await openFile(page, clip);

  // "Kes" is the default for a video; lossless is the default mode.
  await page.getByLabel('Başlangıç 1').fill('1.5');
  await page.getByLabel('Bitiş 1').fill('3');
  // The keyframe shift is predicted before anything runs.
  await expect(page.getByText('Başlangıç 1.5 sn yerine 1 sn olacak')).toBeVisible();
  await expect(page.getByTestId('studio-command')).toContainText('-c copy');
  await page.getByLabel('Başlangıç 1').fill('1');
  await expect(page.getByTestId('studio-output')).toContainText(`${dir}/clip (kesit).mp4`);

  const [output] = await runAndWait(page, request);
  expect(output).toBe(path.join(dir, 'clip (kesit).mp4'));
  const result = probe(output!);
  // Stream copy: never shorter than asked, at most a few frames longer (B-frames).
  expect(result.duration).toBeGreaterThanOrEqual(2.0);
  expect(result.duration).toBeLessThanOrEqual(2.12);
  expect(result.streams.map((s) => s.codec_name)).toEqual(['h264']);
  expect(existsSync(clip)).toBe(true); // the source is untouched
});

test('frame-accurate trim is exact, and says it re-encodes', async ({ page, request }) => {
  const dir = workspace('accurate');
  const clip = path.join(dir, 'clip.mp4');
  copyFileSync(path.join(MEDIA, 'video_h264.mp4'), clip);
  await openFile(page, clip);
  await page.getByRole('radio', { name: 'Kare hassas' }).click();
  await page.getByLabel('Başlangıç 1').fill('0:01.5');
  await page.getByLabel('Bitiş 1').fill('0:03.2');
  await expect(page.getByText(/görüntüyü yeniden kodlar/)).toBeVisible();
  const [output] = await runAndWait(page, request);
  expect(Math.abs(probe(output!).duration - 1.7)).toBeLessThanOrEqual(0.041);
});

test('remux: drop a track, retag a language, convert to MP4', async ({ page, request }) => {
  const dir = workspace('remux');
  const multi = path.join(dir, 'multi.mkv');
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-i', path.join(MEDIA, 'video_h264.mp4'),
    '-i', path.join(MEDIA, 'audio_en.m4a'), '-i', path.join(MEDIA, 'audio_tr.m4a'), '-map', '0', '-map', '1',
    '-map', '2', '-c', 'copy', multi]);
  await openFile(page, multi);
  await page.getByRole('radio', { name: 'Remux ve izler' }).click();
  await page.getByRole('radio', { name: 'MP4' }).click();
  await page.getByLabel('Tut 2').uncheck(); // the first audio track
  await page.getByLabel('Dil 3').fill('tr');
  await expect(page.getByText(/Remux yeniden kodlamaz/)).toBeVisible();
  const [output] = await runAndWait(page, request);
  const kinds = probe(output!).streams.map((s) => [s.codec_type, s.tags?.language]);
  expect(kinds).toEqual([['video', 'und'], ['audio', 'tur']]);
});

test('loudness normalisation runs in two passes', async ({ page, request }) => {
  const dir = workspace('audio');
  const song = path.join(dir, 'song.m4a');
  copyFileSync(path.join(MEDIA, 'audio_en.m4a'), song);
  await openFile(page, song);
  await page.getByRole('radio', { name: 'Ses', exact: true }).click();
  await page.getByLabel(/Ses seviyesini eşitle/).check();
  await expect(page.getByText(/iki geçişte -16 LUFS/)).toBeVisible();
  await expect(page.getByTestId('studio-command')).toHaveCount(2);
  const [output] = await runAndWait(page, request);
  expect(output).toMatch(/song \(ses\)\.mp3$/);
});

test('YouTube auto captions are recognised and cleaned', async ({ page, request }) => {
  const dir = workspace('subs');
  const vtt = path.join(dir, 'talk.en.vtt');
  writeFileSync(vtt, [
    'WEBVTT', '', '00:00:00.000 --> 00:00:02.500 align:start position:0%', ' ',
    'hello<00:00:00.500><c> world</c>', '', '00:00:02.500 --> 00:00:02.510 align:start position:0%',
    'hello world', ' ', '', '00:00:02.510 --> 00:00:05.000 align:start position:0%', 'hello world',
    'again<00:00:03.000><c> here</c>', '',
  ].join('\n'));
  await openFile(page, vtt);
  await expect(page.getByText(/YouTube otomatik altyazısına benziyor/)).toBeVisible();
  const [output] = await runAndWait(page, request);
  const text = readFileSync(output!, 'utf8');
  expect(text.match(/hello world/g)).toHaveLength(1);
  expect(text).not.toContain('<c>');
});

test('screenshots: studio in light, dark and narrow', async ({ page }) => {
  const dir = workspace('shots');
  const clip = path.join(dir, 'clip.mp4');
  copyFileSync(path.join(MEDIA, 'video_h264.mp4'), clip);
  await page.addInitScript(() => localStorage.setItem('vd-theme', 'light'));
  await openFile(page, clip);
  await page.getByLabel('Başlangıç 1').fill('1.5');
  await expect(page.getByText('Başlangıç 1.5 sn yerine 1 sn olacak')).toBeVisible();
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/studio-light.png`, fullPage: true });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/studio-dark.png`, fullPage: true });
  // The content area scrolls inside the window: bring the command preview into view too.
  await page.getByTestId('studio-command').scrollIntoViewIfNeeded();
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/studio-commands-dark.png` });
  await page.setViewportSize({ width: 420, height: 900 });
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/studio-narrow.png`, fullPage: true });
});
