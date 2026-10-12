import { expect, test, type Page } from '@playwright/test';

/** The page as the native app shows it: `?embedded=1`, driven through `window.vd`. */

async function withNativeBridge(page: Page) {
  // Stands in for WKWebView's `window.webkit.messageHandlers.vd`, recording what the page says.
  await page.addInitScript(() => {
    const sent: unknown[] = [];
    (window as unknown as { sentToNative: unknown[] }).sentToNative = sent;
    (window as unknown as { webkit: unknown }).webkit = {
      messageHandlers: { vd: { postMessage: (m: unknown) => sent.push(m) } },
    };
  });
}

const sentToNative = (page: Page) =>
  page.evaluate(() => (window as unknown as { sentToNative: { type: string; route: string }[] }).sentToNative);

test('embedded: no sidebar, the requested screen, and the native window drives navigation', async ({
  page,
}) => {
  await withNativeBridge(page);
  await page.goto('/?embedded=1&route=doctor');
  await expect(page.getByRole('navigation')).toBeHidden(); // the app draws the sidebar
  await expect(page.getByText('JavaScript çalıştırıcı')).toBeVisible();
  await expect(page.getByRole('radiogroup', { name: 'Tema' })).toBeHidden();
  expect(await sentToNative(page)).toContainEqual({ type: 'route', route: 'doctor' });

  await page.evaluate(() => (window as unknown as { vd: { navigate: (r: string) => void } }).vd.navigate('library'));
  await expect(page.getByLabel('Başlık veya kanal ara')).toBeVisible(); // its toolbar items stay
  await page.evaluate(() => (window as unknown as { vd: { navigate: (r: string) => void } }).vd.navigate('nonsense'));
  await expect(page.getByLabel('Başlık veya kanal ara')).toBeVisible();

  // A link handed over by the app (URL scheme, Dock drop) is inspected right away.
  await page.evaluate(() =>
    (window as unknown as { vd: { inspect: (u: string) => void } }).vd.inspect('https://example.test/local-media'),
  );
  await expect(page.getByRole('heading', { name: 'Local test clip' })).toBeVisible();
  const routes = (await sentToNative(page)).map((m) => m.route);
  expect(routes.slice(-2)).toEqual(['library', 'inspect']);
});

test('embedded settings follow the system appearance and offer no theme choice', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vd-theme', 'dark'));
  await page.goto('/?embedded=1&route=settings');
  await expect(page.getByText('İndirme klasörü')).toBeVisible();
  await expect(page.getByRole('radiogroup', { name: 'Görünüm' })).toHaveCount(0);
  // A theme stored by the browser version is ignored inside the app.
  expect(await page.evaluate(() => document.documentElement.getAttribute('data-theme'))).toBeNull();
});
