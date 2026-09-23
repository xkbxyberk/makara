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

  // libass is missing from this ffmpeg build; the UI must say so rather than offer burn-in.
  await expect(page.locator('.check-row', { hasText: 'FFmpeg' })).toContainText(
    'altyazıyı görüntünün içine yakma özelliği kapalı',
  );
});

test('screenshots: doctor in light, dark and at a narrow width', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vd-theme', 'light'));
  await page.goto('/');
  await page.getByRole('button', { name: /Sistem/ }).click();
  await expect(page.getByText('FFmpeg', { exact: true })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/doctor-light.png` });

  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ path: `${SHOTS}/doctor-dark.png` });

  await page.setViewportSize({ width: 420, height: 900 });
  await page.screenshot({ path: `${SHOTS}/doctor-narrow.png` });
});
