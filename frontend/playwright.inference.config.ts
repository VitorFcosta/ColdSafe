import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'inference-real.spec.ts',
  workers: 1,
  timeout: 150_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: { baseURL: process.env.INFERENCE_REAL_URL, ...devices['Desktop Chrome'], screenshot: 'only-on-failure' },
})
