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

test('embedded: the copied-link offer is left to the app (one banner, not two)', async ({ page, context, request }) => {
  await withNativeBridge(page);
  await page.goto('/?embedded=1&route=library');
  await expect(page.getByLabel('Başlık veya kanal ara')).toBeVisible();
  // A normal page on the same server proves the event really went out.
  const browserPage = await context.newPage();
  await browserPage.goto('/');
  const offer = (p: Page) => p.getByRole('status').filter({ hasText: 'Panoya bir bağlantı kopyaladın' });
  await expect
    .poll(async () => {
      await request.post('/api/test/clipboard', { data: { url: 'https://example.test/local-media' } });
      return offer(browserPage).isVisible();
    })
    .toBe(true);
  await request.post('/api/test/clipboard', { data: { url: 'https://example.test/local-media' } });
  await browserPage.waitForTimeout(500);
  await expect(offer(page)).toHaveCount(0);
});

test('embedded: the native Kütüphane hands an item to Stüdyo', async ({ page, request }) => {
  // A finished download in the library, queued the way the extension does it.
  const quick = await request.post('/api/quick', { data: { url: 'https://example.test/local-media', rule: { kind: 'video' } } });
  const jobId = ((await quick.json()) as { job: { id: string } }).job.id;
  let item: { id: string; primary_path: string } | undefined;
  await expect
    .poll(async () => {
      const jobs = (await (await request.get('/api/jobs')).json()) as { id: string; status: string; output_files: string[] }[];
      const job = jobs.find((j) => j.id === jobId);
      if (job?.status !== 'done') return false;
      const { items } = (await (await request.get('/api/library')).json()) as { items: { id: string; primary_path: string }[] };
      item = items.find((it) => it.primary_path === job.output_files[0]);
      return item !== undefined;
    }, { timeout: 60_000 })
    .toBe(true);
  await withNativeBridge(page);
  await page.goto('/?embedded=1&route=inspect');
  await page.evaluate(
    (id) => (window as unknown as { vd: { openInStudio: (i: string) => void } }).vd.openInStudio(id),
    item!.id,
  );
  await expect(page.getByTestId('studio-source')).toContainText(item!.primary_path.split('/').pop()!);
  expect(await sentToNative(page)).toContainEqual({ type: 'route', route: 'studio' });
});
