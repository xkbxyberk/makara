import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

/** The e2e suite drives the real server in fixture mode: realistic URLs, zero network. */
export default defineConfig({
  testDir: './e2e',
  outputDir: '../test-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8787',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    // Fresh database and download folder for every run; test media is generated, not fetched.
    command:
      'rm -rf test-results/e2e-data test-results/e2e-downloads && ' +
      'uv run python scripts/make_test_media.py && uv run python -m app.main',
    cwd: '..',
    url: 'http://127.0.0.1:8787/api/health',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      VD_FIXTURE_MODE: '1',
      PYTHONPATH: 'backend',
      VD_DATA_DIR: path.resolve(__dirname, '../test-results/e2e-data'),
      VD_DOWNLOAD_DIR: path.resolve(__dirname, '../test-results/e2e-downloads'),
    },
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
