import { expect, test } from '@playwright/test'

import { mockDashboardAccount } from './monitoring-api'

test('preserva seleção válida e período; revalida após gestão, recarga e troca de conta', async ({ page }) => {
  await mockDashboardAccount(page)
  let secondDeviceActive = true
  const summaryRequests: string[] = []
  const historyRequests: string[] = []
  await page.route('**/api/v1/environments', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [
      { id: 'lab-refrigerado', name: 'Laboratório Refrigerado' },
      { id: 'lab-extra', name: 'Laboratório Extra' },
    ] }),
  }))
  await page.route('**/api/v1/environments/lab-extra/devices', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [
      { id: 'uuid-extra-01', environment_id: 'lab-extra', name: 'Sensor extra 1', mqtt_device_id: 'esp32-extra-01', is_active: true },
      { id: 'uuid-extra-02', environment_id: 'lab-extra', name: 'Sensor extra 2', mqtt_device_id: 'esp32-extra-02', is_active: secondDeviceActive },
    ] }),
  }))
  await page.route('**/api/v1/environments/*/rules', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: {
      min_c: 2, max_c: 8, attention_margin_c: 1,
    } }),
  }))
  await page.route('**/api/v1/monitoring/summary**', (route) => {
    const deviceId = new URL(route.request().url()).searchParams.get('device_id') ?? ''
    summaryRequests.push(deviceId)
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: {
      environment: { id: deviceId.startsWith('esp32-extra') ? 'lab-extra' : 'lab-refrigerado', name: deviceId.startsWith('esp32-extra') ? 'Laboratório Extra' : 'Laboratório Refrigerado' },
      device: { id: deviceId },
      reading: { temperature_c: deviceId === 'esp32-extra-02' ? 4 : 5, humidity_percent: 65, light_percent: 42, received_at: '2026-09-09T12:00:00Z' },
      status: 'normal', freshness: { is_stale: false, age_seconds: 2 },
      thresholds: deviceId.startsWith('esp32-extra')
        ? { min_c: -2, max_c: 4, attention_margin_c: 1 }
        : { min_c: 2, max_c: 8, attention_margin_c: 1 },
    } }) })
  })
  await page.route('**/api/v1/readings?**', (route) => {
    const query = new URL(route.request().url()).searchParams
    if (query.has('period')) historyRequests.push(`${query.get('device_id')}:${query.get('period')}`)
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      success: true, data: { readings: [] }, meta: { device_id: query.get('device_id'), start: '2026-09-09T11:00:00Z', end: '2026-09-09T12:00:00Z', count: 0, limit: 300 },
    }) })
  })
  await page.route('**/api/v1/auth/logout', (route) => route.fulfill({ status: 200 }))
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: { token: 'other-account-token', expires_at: '2099-01-01T00:00:00Z' } }),
  }))

  await page.goto('/dashboard')
  await page.getByRole('combobox', { name: 'Ambiente' }).selectOption('lab-extra')
  await page.getByRole('combobox', { name: 'Dispositivo' }).selectOption('uuid-extra-02')
  await expect(page.getByText('Laboratório Extra / esp32-extra-02', { exact: true })).toBeVisible()
  await expect(page.getByText(/limites atuais do ambiente, -2–4 °C/)).toBeVisible()
  await page.getByRole('button', { name: '24h' }).click()
  await expect(page.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'true')

  await page.getByRole('link', { name: 'Ambientes e dispositivos' }).click()
  await page.getByRole('link', { name: 'Monitoramento' }).click()
  await expect(page.getByRole('combobox', { name: 'Ambiente' })).toHaveValue('lab-extra')
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('uuid-extra-02')
  await expect(page.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'true')
  expect(summaryRequests.at(-1)).toBe('esp32-extra-02')
  expect(historyRequests.at(-1)).toBe('esp32-extra-02:24h')

  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('uuid-extra-02')
  await expect(page.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('link', { name: 'Ambientes e dispositivos' }).click()
  await expect(page).toHaveURL(/\/manage/)
  await page.getByRole('link', { name: 'Monitoramento' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
  await page.goBack()
  await expect(page).toHaveURL(/\/manage/)
  await page.goForward()
  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('uuid-extra-02')
  await page.getByRole('link', { name: 'Ambientes e dispositivos' }).click()
  secondDeviceActive = false
  await page.getByRole('link', { name: 'Monitoramento' }).click()
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('uuid-extra-01')
  await expect(page.locator('.selection-panel [role="status"]')).toContainText('dispositivo selecionado não está mais ativo')
  await expect(page.getByText('Laboratório Extra / esp32-extra-01', { exact: true })).toBeVisible()
  await expect(page.getByText('Laboratório Extra / esp32-extra-02', { exact: true })).toHaveCount(0)
  expect(summaryRequests.at(-1)).toBe('esp32-extra-01')

  await page.getByRole('button', { name: 'Sair' }).click()
  await expect(page).toHaveURL('/login')
  await page.getByLabel('Email').fill('outra@example.com')
  await page.getByLabel('Senha').fill('senha-segura')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('combobox', { name: 'Ambiente' })).toHaveValue('lab-refrigerado')
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('uuid-01')
  await expect(page.getByRole('button', { name: '1h' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText(/limites atuais do ambiente, 2–8 °C/)).toBeVisible()
})
