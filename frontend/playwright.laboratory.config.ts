import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'laboratory-real.spec.ts',
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: { baseURL: process.env.LAB_REAL_URL, ...devices['Desktop Chrome'], screenshot: 'only-on-failure' },
})
