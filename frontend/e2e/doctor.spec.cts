import { expect, test } from '@playwright/test';

const SHOTS = '../test-results/screenshots';

test('the doctor reports every dependency and this build ffmpeg capabilities', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Sistem/ }).click();

  await expect(page.getByText('yt-dlp', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('JavaScript çalıştırıcı')).toBeVisible();
  await expect(page.getByText('FFmpeg', { exact: true })).toBeVisible();

  // deno is installed on this machine, so the JS runtime check must be green.
  await expect(page.locator('.check-row', { hasText: 'JavaScript çalıştırıcı' })).toContainText('deno');

  // The UI tells the truth about this machine's build: without libass it says burn-in is off
  // (and how to get it); with Homebrew's ffmpeg-full it says nothing is missing.
  const report = (await (await page.request.get('/api/doctor')).json()) as {
    checks: { id: string; status: string; values: { capabilities: Record<string, boolean>; ffmpeg_path?: string } }[];
  };
  const ffmpeg = report.checks.find((c) => c.id === 'ffmpeg')!;
  const row = page.locator('.check-row', { hasText: 'FFmpeg' });
  await expect(row).toContainText(ffmpeg.values.ffmpeg_path!);
  if (ffmpeg.values.capabilities.subtitles_filter) {
    expect(ffmpeg.status).toBe('ok');
    await expect(row).toContainText('Hazır');
    await expect(row).not.toContainText('altyazıyı görüntünün içine yakma özelliği kapalı');
  } else {
    await expect(row).toContainText('altyazıyı görüntünün içine yakma özelliği kapalı');
    await expect(row).toContainText('brew install ffmpeg-full');
  }
});

test('screenshots: doctor in light, dark and at a narrow width', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vd-theme', 'light'));
  await page.goto('/');
  await page.getByRole('button', { name: /Sistem/ }).click();
  await expect(page.getByText('FFmpeg', { exact: true })).toBeVisible();
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/doctor-light.png` });

  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/doctor-dark.png` });

  await page.setViewportSize({ width: 420, height: 900 });
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/doctor-narrow.png` });
});
