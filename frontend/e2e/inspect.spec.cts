import { expect, test, type Page } from '@playwright/test';

const MULTI_AUDIO = 'https://www.youtube.com/watch?v=0e3GPea1Tyg';
const MANY_SUBS = 'https://www.youtube.com/watch?v=iG9CE55wbtY';
const PLAYLIST = 'https://www.youtube.com/@TED/videos';

const SHOTS = '../test-results/screenshots';

async function setTheme(page: Page, theme: 'light' | 'dark') {
  await page.addInitScript((value) => localStorage.setItem('vd-theme', value), theme);
}

async function inspect(page: Page, url: string) {
  await page.getByLabel('Bağlantı').fill(url);
  await page.getByRole('main').getByRole('button', { name: 'İncele', exact: true }).click();
}

/** Hover only once the download plan has arrived: it grows the panel and shifts the page, which
 * would slide the term out from under a pointer that got there first. */
async function settled(page: Page) {
  await expect(page.getByRole('button', { name: 'İndir', exact: true })).toBeEnabled();
}

test('empty state invites a paste', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Henüz bir şey incelemedin')).toBeVisible();
  await expect(page.getByPlaceholder('Bir video, playlist veya kanal bağlantısı yapıştır')).toBeVisible();
});

test('inspecting a multi-audio video shows every track group', async ({ page }) => {
  await page.goto('/');
  await inspect(page, MULTI_AUDIO);

  await expect(page.getByRole('heading', { name: /Squid Game/ })).toBeVisible();

  // Video qualities, with the best first.
  const videoPanel = page.locator('section.panel', { hasText: 'Video kaliteleri' }).first();
  await expect(videoPanel.locator('tbody tr').first()).toContainText('1920x1080');

  // 24 audio languages, the original one badged and listed first.
  const audioPanel = page.locator('section.panel', { hasText: 'Ses parçaları' }).first();
  await expect(audioPanel.locator('.panel-count')).toHaveText('24');
  const firstGroup = audioPanel.locator('.lang-group').first();
  await expect(firstGroup).toContainText('İngilizce');
  await expect(firstGroup).toContainText('Orijinal');
  // A dub must never claim to be an auto-dub: yt-dlp cannot tell them apart.
  await expect(audioPanel).not.toContainText('auto-dub');

  await expect(page.locator('section.panel', { hasText: 'Bölümler' }).first()).toContainText('Bölümler');
  await expect(page.locator('.heatmap .heatmap-bar')).toHaveCount(100);
  await expect(page.locator('section.panel', { hasText: 'Eşdeğer yt-dlp komutu' })).toContainText(
    'yt-dlp -f',
  );
});

test('subtitles are split into manual, automatic and machine-translated', async ({ page }) => {
  await page.goto('/');
  await inspect(page, MANY_SUBS);

  const panel = page.locator('section.panel', { hasText: 'Altyazılar' }).first();
  await expect(panel).toContainText('İnsan yazımı');
  await expect(panel).toContainText('Otomatik oluşturulmuş');
  await expect(panel).toContainText('Otomatik çeviri');

  // Machine translations stay collapsed until asked for.
  const toggle = panel.getByRole('button', { name: /makine çevirisini göster/ });
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(panel.getByRole('button', { name: 'Makine çevirilerini gizle' })).toBeVisible();

  // The original-language ASR track is called out.
  await expect(panel).toContainText('videonun kendi dili');
});

test('a technical term explains itself on hover', async ({ page }) => {
  await page.goto('/');
  await inspect(page, MULTI_AUDIO);
  await settled(page);
  await page.locator('.term', { hasText: 'HDR' }).first().hover();
  await expect(page.getByRole('tooltip')).toContainText('Yüksek dinamik aralık');
});

test('a help tag is never clipped by its panel, even at the bottom edge of a narrow window', async ({ page }) => {
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto('/');
  await inspect(page, MULTI_AUDIO);
  await settled(page);
  // A term inside a table panel that clips its overflow, scrolled to the very bottom of the window.
  const term = page.locator('tbody .term', { hasText: 'VP9' }).first();
  await term.evaluate((el) => el.scrollIntoView({ block: 'end' }));
  await term.hover();
  const tip = page.getByRole('tooltip');
  await expect(tip).toContainText('QuickTime');
  expect(await tip.evaluate((el) => el.parentElement === document.body)).toBe(true);
  const box = (await tip.boundingBox())!;
  const termBox = (await term.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(420);
  expect(box.y + box.height).toBeLessThanOrEqual(900);
  expect(box.y + box.height).toBeLessThanOrEqual(termBox.y); // no room below, so it opens above
});

test('every technical column header and codec explains itself', async ({ page }) => {
  await page.goto('/');
  await inspect(page, MULTI_AUDIO);
  const videoHead = page.locator('section.panel', { hasText: 'Video kaliteleri' }).first().locator('thead');
  // Format, FPS, Kodek, HDR, Bit hızı, Kap -- plain words (Çözünürlük, Boyut) need no tooltip.
  await expect(videoHead.locator('.term')).toHaveCount(6);

  const audioHead = page.locator('section.panel', { hasText: 'Ses parçaları' }).first().locator('thead');
  await expect(audioHead.locator('.term')).toHaveCount(5);

  await settled(page);
  await page.locator('tbody .term', { hasText: 'VP9' }).first().hover();
  await expect(page.getByRole('tooltip')).toContainText('QuickTime');
});

test('AI-upscaled variants are labelled, and shadowed auto captions explained', async ({ page }) => {
  await page.goto('/');
  await inspect(page, MANY_SUBS);
  await expect(page.getByText('YZ ile büyütülmüş').first()).toBeVisible();
  const auto = page.locator('section.panel', { hasText: 'Altyazılar' }).first();
  await expect(auto.locator('tr.dim', { hasText: 'en' }).first()).toBeVisible();
});

test('a playlist is shown as a list, and says why tracks are missing', async ({ page }) => {
  await page.goto('/');
  await inspect(page, PLAYLIST);
  await expect(page.getByText('Bu bir liste')).toBeVisible();
  await expect(page.locator('table.grid tbody tr')).toHaveCount(12);
});

test('a bad url produces a Turkish error with the raw log one click away', async ({ page }) => {
  await page.goto('/');
  await inspect(page, 'kesinlikle-bir-url-degil');
  await expect(page.getByRole('alert')).toContainText('Bu bir bağlantı değil');
  await page.getByRole('button', { name: 'Ayrıntıları göster' }).click();
  await expect(page.locator('pre')).toBeVisible();
});

test('screenshots: inspect in light, dark and at a narrow width', async ({ page }) => {
  await setTheme(page, 'light');
  await page.goto('/');
  await inspect(page, MULTI_AUDIO);
  await expect(page.getByRole('heading', { name: /Squid Game/ })).toBeVisible();
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/inspect-light.png`, fullPage: false });

  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/inspect-dark.png`, fullPage: false });

  await page.setViewportSize({ width: 420, height: 900 });
  await page.screenshot({ animations: 'disabled', path: `${SHOTS}/inspect-narrow.png`, fullPage: false });
});
