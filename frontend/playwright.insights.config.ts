import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'insights-real.spec.ts',
  workers: 1,
  timeout: 150_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: { baseURL: process.env.INSIGHTS_REAL_URL, ...devices['Desktop Chrome'], screenshot: 'only-on-failure',
    actionTimeout: 20_000, navigationTimeout: 30_000 },
})
