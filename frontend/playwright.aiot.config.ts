import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'aiot-real.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.DASHBOARD_REAL_URL,
    // Real credentials/tokens must never be recorded in a network trace.
    trace: 'off',
    screenshot: 'only-on-failure',
  },
})
