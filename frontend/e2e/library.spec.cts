import { existsSync, unlinkSync } from 'node:fs';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const LOCAL = 'https://example.test/local-media';
const SHOTS = '../test-results/screenshots';

interface Item {
  id: string;
  primary_path: string;
  status: string;
}

/** Download through the real UI, then return this test's own library item. */
async function downloadToLibrary(page: Page, request: APIRequestContext, mode = 'Arşiv MKV'): Promise<Item> {
  await page.goto('/');
  await page.getByLabel('Bağlantı').fill(LOCAL);
  await page.getByRole('main').getByRole('button', { name: 'İncele', exact: true }).click();
  await page.getByRole('radio', { name: mode }).click();
  const button = page.getByRole('button', { name: 'İndir', exact: true });
  await expect(button).toBeEnabled();
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/jobs') && r.request().method() === 'POST'),
    button.click(),
  ]);
  const { id } = (await response.json()) as { id: string };
  for (let i = 0; i < 300; i++) {
    const jobs = (await (await request.get('/api/jobs')).json()) as { id: string; status: string; output_files: string[] }[];
    const job = jobs.find((j) => j.id === id);
    if (job?.status === 'failed') throw new Error('download failed');
    if (job?.status === 'done') {
      const { items } = (await (await request.get('/api/library')).json()) as { items: Item[] };
      const item = items.find((it) => it.primary_path === job.output_files[0]);
      if (item) return item;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('item never reached the library');
}

async function openLibrary(page: Page) {
  await page.getByRole('navigation').getByRole('button', { name: 'Kütüphane' }).click();
}

test('a finished download shows up in the library with its tracks and a thumbnail', async ({ page, request }) => {
  const item = await downloadToLibrary(page, request);
  await openLibrary(page);
  const card = page.locator(`[data-item-id="${item.id}"]`);
  await expect(card).toContainText('Local test clip');
  await expect(card).toContainText('Arşiv MKV');
  const thumb = card.locator('img.lib-thumb');
  await expect(thumb).toBeVisible();
  await expect.poll(() => thumb.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);

  await card.locator('.lib-card-button').click();
  await expect(card).toContainText('İngilizce'); // audio track language, from ffprobe
  await expect(card).toContainText('Türkçe'); // subtitle languages
  await expect(card.getByRole('button', { name: 'Oynat' })).toBeEnabled();
  await expect(card.getByRole('button', { name: 'Finder’da göster' })).toBeEnabled();
});

test('list view, search and the kind filter', async ({ page, request }) => {
  const item = await downloadToLibrary(page, request, 'Sadece ses');
  await openLibrary(page);
  await page.getByRole('radio', { name: 'Liste' }).click();
  await expect(page.locator(`tr[data-item-id="${item.id}"]`)).toBeVisible();

  await page.getByLabel('Tür').selectOption({ label: 'Video' });
  await expect(page.locator(`[data-item-id="${item.id}"]`)).toHaveCount(0);
  await page.getByLabel('Tür').selectOption({ label: 'Ses' });
  await expect(page.locator(`[data-item-id="${item.id}"]`)).toBeVisible();

  await page.getByLabel('Başlık veya kanal ara').fill('bu başlık yok');
  await expect(page.getByText('Eşleşen öğe yok')).toBeVisible();
  await page.getByLabel('Başlık veya kanal ara').fill('local test');
  await expect(page.locator(`[data-item-id="${item.id}"]`)).toBeVisible();
});

test('move to Trash asks first, and Cancel really cancels', async ({ page, request }) => {
  const item = await downloadToLibrary(page, request);
  await openLibrary(page);
  const card = page.locator(`[data-item-id="${item.id}"]`);
  await card.locator('.lib-card-button').click();

  await card.getByRole('button', { name: 'Çöp Kutusu’na taşı' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Çöp Kutusu’na taşınsın mı?');
  await expect(dialog.getByRole('button', { name: 'Vazgeç' })).toBeFocused(); // the safe choice
  await dialog.getByRole('button', { name: 'Vazgeç' }).click();
  await expect(dialog).toBeHidden();
  expect(existsSync(item.primary_path)).toBe(true);

  await card.getByRole('button', { name: 'Çöp Kutusu’na taşı' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Çöp Kutusu’na taşı' }).click();
  await expect(card).toHaveCount(0);
  expect(existsSync(item.primary_path)).toBe(false);
});

test('a file deleted in Finder is marked missing, not forgotten', async ({ page, request }) => {
  const item = await downloadToLibrary(page, request, 'Sadece ses');
  unlinkSync(item.primary_path);
  await openLibrary(page);
  await page.getByRole('button', { name: 'Dosyaları denetle' }).click();
  const card = page.locator(`[data-item-id="${item.id}"]`);
  await expect(card).toContainText('Eksik');
  await card.locator('.lib-card-button').click();
  await expect(card.getByRole('button', { name: 'Oynat' })).toBeDisabled();
  await page.getByLabel('Yalnızca eksikler').check();
  await expect(card).toBeVisible();
});

test('screenshots: library grid and list in light, dark and narrow', async ({ page, request }) => {
  await page.addInitScript(() => localStorage.setItem('vd-theme', 'light'));
  await downloadToLibrary(page, request);
  await openLibrary(page);
  await page.getByRole('radio', { name: 'Izgara' }).click();
  await expect(page.getByTestId('library-item').first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/library-grid-light.png` });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ path: `${SHOTS}/library-grid-dark.png` });
  await page.getByRole('radio', { name: 'Liste' }).click();
  await page.screenshot({ path: `${SHOTS}/library-list-dark.png` });
  await page.setViewportSize({ width: 420, height: 900 });
  await page.getByRole('radio', { name: 'Izgara' }).click();
  await page.screenshot({ path: `${SHOTS}/library-narrow.png` });
});
