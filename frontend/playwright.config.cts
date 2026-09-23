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
    command: 'uv run python -m app.main',
    cwd: '..',
    url: 'http://127.0.0.1:8787/api/health',
    reuseExistingServer: false,
    env: { VD_FIXTURE_MODE: '1', PYTHONPATH: 'backend' },
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
