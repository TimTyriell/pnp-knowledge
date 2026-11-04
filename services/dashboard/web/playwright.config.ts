import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  failOnFlakyTests: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000, toHaveScreenshot: { animations: 'disabled' } },
  outputDir: './test-results',
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
    ['json', { outputFile: process.env.PLAYWRIGHT_JSON_OUTPUT_FILE ?? 'test-results/results.json' }],
  ],
  snapshotPathTemplate: '{testDir}/__screenshots__/{arg}{ext}',
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 900 },
    locale: 'en-GB',
    timezoneId: 'Europe/Berlin',
    colorScheme: 'light',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    serviceWorkers: 'block',
  },
  projects: [
    { name: 'chromium', testIgnore: '**/*.visual.spec.ts' },
    { name: 'visual-chromium', testMatch: '**/*.visual.spec.ts' },
  ],
})
