import { expect, test } from '@playwright/test';

const SHOTS = '../test-results/screenshots';

async function openSettings(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'Ayarlar' }).click();
  await expect(page.getByLabel('İndirme klasörü')).toBeVisible();
}

test('the naming template previews live and rejects escaping the folder', async ({ page }) => {
  await openSettings(page);
  const template = page.getByLabel('Dosya adı şablonu');
  const preview = page.getByTestId('template-preview');
  // Other specs download in parallel with the saved template, so this one is never saved.
  await template.fill('%(channel)s/%(title)s.%(ext)s');
  await expect(preview).toContainText('Örnek Kanal/Örnek video başlığı.mkv');
  await template.fill('../%(title)s.%(ext)s');
  await expect(preview).toContainText('İndirme klasörünün dışına yazılamaz');
  await expect(page.getByText('Kaydedilmemiş değişiklikler var.')).toBeVisible();
});

test('a harmless setting saves and survives a reload', async ({ page }) => {
  await openSettings(page);
  const toggle = page.getByLabel(/Sistem bildirimleri/);
  const before = await toggle.isChecked();
  await toggle.setChecked(!before);
  await page.getByRole('button', { name: 'Kaydet' }).click();
  await expect(page.getByText('Kaydedildi.')).toBeVisible();
  await openSettings(page);
  await expect(page.getByLabel(/Sistem bildirimleri/)).toBeChecked({ checked: !before });
  await page.getByLabel(/Sistem bildirimleri/).setChecked(before);
  await page.getByRole('button', { name: 'Kaydet' }).click();
  await expect(page.getByText('Kaydedildi.')).toBeVisible();
});

test('theme switches between system, light and dark', async ({ page }) => {
  await openSettings(page);
  const theme = page.getByRole('radiogroup', { name: 'Görünüm' });
  await theme.getByRole('radio', { name: 'Koyu' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await theme.getByRole('radio', { name: 'Açık' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await theme.getByRole('radio', { name: 'Sistem' }).click();
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', /.*/);
});

test('system actions degrade clearly where they cannot run', async ({ page }) => {
  await openSettings(page);
  await page.getByRole('button', { name: 'Seç…' }).click();
  await expect(page.getByRole('alert')).toContainText('Klasör seçici açılamadı');

  await page.getByRole('navigation').getByRole('button', { name: 'Sistem' }).click();
  await page.getByRole('button', { name: 'yt-dlp’yi güncelle' }).click();
  // Other specs download in parallel, so either refusal may apply; each is unit-tested on its own
  // (test_system_actions_never_run_in_fixture_mode, test_updating_yt_dlp_is_refused_while_a_job_runs).
  await expect(page.getByRole('alert')).toContainText(
    /Güncelleme bu modda kapalı|Önce indirmelerin bitmesini bekle/,
  );
});

test('a copied link is offered for inspection', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByText('Henüz bir şey incelemedin')).toBeVisible();
  await page.getByRole('navigation').getByRole('button', { name: 'Kütüphane' }).click();
  const banner = page.getByRole('status').filter({ hasText: 'Panoya bir bağlantı kopyaladın' });
  // Re-send until it lands: the page's event stream may not be connected on the first try.
  await expect
    .poll(async () => {
      await request.post('/api/test/clipboard', { data: { url: 'https://example.test/local-media' } });
      return banner.isVisible();
    })
    .toBe(true);
  await banner.getByRole('button', { name: 'İncele' }).click();
  await expect(page.getByRole('heading', { name: 'Local test clip' })).toBeVisible();
});

test('screenshots: settings in light, dark and narrow', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vd-theme', 'light'));
  await openSettings(page);
  await expect(page.getByTestId('template-preview')).toContainText('Örnek video başlığı');
  await page.screenshot({ path: `${SHOTS}/settings-light.png` });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ path: `${SHOTS}/settings-dark.png` });
  await page.setViewportSize({ width: 420, height: 900 });
  await page.screenshot({ path: `${SHOTS}/settings-narrow.png` });
});
