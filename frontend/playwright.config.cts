import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

/** The e2e suite drives the real server in fixture mode: realistic URLs, zero network. Its own
 * port keeps it clear of the real app, which may be open on 8787. */
const PORT = 8788;
export default defineConfig({
  testDir: './e2e',
  outputDir: '../test-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    // Zero network for the browser too: every request but this Mac's goes to a closed port.
    // A recorded YouTube answer points its thumbnails at i.ytimg.com, which the page fetched
    // for real during the suite until 13 Oct. Chromium never proxies loopback.
    proxy: { server: 'http://127.0.0.1:9', bypass: '127.0.0.1,localhost' },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    // Fresh database and download folder for every run; test media is generated, not fetched.
    command:
      'rm -rf test-results/e2e-data test-results/e2e-downloads test-results/e2e-server.log && ' +
      'mkdir -p test-results && ' +
      'uv run python scripts/make_test_media.py && ' +
      // Everything the server logs is kept, so check.sh can fail the run on a hidden traceback.
      'uv run python -m app.main 2>&1 | tee test-results/e2e-server.log',
    cwd: '..',
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      VD_FIXTURE_MODE: '1',
      VD_PORT: String(PORT),
      PYTHONPATH: 'backend',
      VD_DATA_DIR: path.resolve(__dirname, '../test-results/e2e-data'),
      VD_DOWNLOAD_DIR: path.resolve(__dirname, '../test-results/e2e-downloads'),
    },
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
