import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'training-real.spec.ts',
  workers: 1,
  timeout: 300_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: { baseURL: process.env.TRAINING_REAL_URL, ...devices['Desktop Chrome'], screenshot: 'only-on-failure' },
})
