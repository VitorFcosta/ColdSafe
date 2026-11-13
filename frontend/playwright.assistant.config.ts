import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'assistant-real.spec.ts',
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  reporter: [['list']],
  use: { baseURL: process.env.ASSISTANT_REAL_URL, ...devices['Desktop Chrome'],
    screenshot: 'only-on-failure', actionTimeout: 12_000, navigationTimeout: 30_000 },
})
