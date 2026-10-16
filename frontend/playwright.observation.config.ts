import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'messaging-observation-real.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.MESSAGING_REAL_URL,
    // Real session credentials must never be recorded in a network trace.
    trace: 'off',
    screenshot: 'only-on-failure',
  },
})
