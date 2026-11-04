import { expect, test } from '@playwright/test'

import { mockDashboardAccount } from './monitoring-api'

test('preserva seleção e período; invalidação pede escolha, gestão e conta mantêm seus escopos', async ({ page }) => {
  await mockDashboardAccount(page)
  let secondDeviceActive = true
  const summaryRequests: string[] = []
  const historyRequests: string[] = []
  await page.route('**/api/v1/environments', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [
      { id: '00000000-0000-4000-8000-000000000001', name: 'Laboratório Refrigerado' },
      { id: '00000000-0000-4000-8000-000000000002', name: 'Laboratório Extra' },
    ] }),
  }))
  await page.route('**/api/v1/environments/00000000-0000-4000-8000-000000000001/devices', (route) => route.fulfill({ json: {
    success: true, data: [{ id: '00000000-0000-4000-8000-000000000011', environment_id: '00000000-0000-4000-8000-000000000001', name: 'Sensor 1', mqtt_device_id: 'esp32-lab-01', is_active: true }],
  } }))
  await page.route('**/api/v1/environments/00000000-0000-4000-8000-000000000002/devices', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [
      { id: '00000000-0000-4000-8000-000000000021', environment_id: '00000000-0000-4000-8000-000000000002', name: 'Sensor extra 1', mqtt_device_id: 'esp32-extra-01', is_active: true },
      { id: '00000000-0000-4000-8000-000000000022', environment_id: '00000000-0000-4000-8000-000000000002', name: 'Sensor extra 2', mqtt_device_id: 'esp32-extra-02', is_active: secondDeviceActive },
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
      environment: { id: deviceId.startsWith('esp32-extra') ? '00000000-0000-4000-8000-000000000002' : '00000000-0000-4000-8000-000000000001', name: deviceId.startsWith('esp32-extra') ? 'Laboratório Extra' : 'Laboratório Refrigerado' },
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
  await page.getByRole('combobox', { name: 'Ambiente' }).selectOption('00000000-0000-4000-8000-000000000002')
  await page.getByRole('combobox', { name: 'Dispositivo' }).selectOption('00000000-0000-4000-8000-000000000022')
  await expect(page.getByText('Laboratório Extra / esp32-extra-02', { exact: true })).toBeVisible()
  await expect(page.getByText(/limites atuais do ambiente, -2–4 °C/)).toBeVisible()
  await page.getByRole('button', { name: '24h' }).click()
  await expect(page.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'true')

  await page.getByRole('link', { name: 'Ambientes e dispositivos' }).click()
  await page.getByRole('link', { name: 'Monitoramento' }).click()
  await expect(page.getByRole('combobox', { name: 'Ambiente' })).toHaveValue('00000000-0000-4000-8000-000000000002')
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('00000000-0000-4000-8000-000000000022')
  await expect(page.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'true')
  expect(summaryRequests.at(-1)).toBe('esp32-extra-02')
  expect(historyRequests.at(-1)).toBe('esp32-extra-02:24h')

  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('00000000-0000-4000-8000-000000000022')
  await expect(page.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('link', { name: 'Ambientes e dispositivos' }).click()
  await expect(page).toHaveURL(/\/manage/)
  await page.getByRole('link', { name: 'Monitoramento' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
  await page.goBack()
  await expect(page).toHaveURL(/\/manage/)
  await page.goForward()
  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('00000000-0000-4000-8000-000000000022')
  await page.getByRole('link', { name: 'Ambientes e dispositivos' }).click()
  secondDeviceActive = false
  await page.getByRole('link', { name: 'Monitoramento' }).click()
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('')
  await expect(page.locator('.selection-panel [role="status"]')).toContainText(/selecione|escolha/i)
  await expect(page.getByText('Laboratório Extra / esp32-extra-02', { exact: true })).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Dispositivo' }).selectOption('00000000-0000-4000-8000-000000000021')
  await expect(page.getByText('Laboratório Extra / esp32-extra-01', { exact: true })).toBeVisible()
  await expect(page.getByText('Laboratório Extra / esp32-extra-02', { exact: true })).toHaveCount(0)
  expect(summaryRequests.at(-1)).toBe('esp32-extra-01')

  await page.getByRole('button', { name: 'Sair' }).click()
  await expect(page).toHaveURL('/login')
  await page.getByLabel('Email').fill('outra@example.com')
  await page.getByLabel('Senha').fill('senha-segura')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('combobox', { name: 'Ambiente' })).toHaveValue('00000000-0000-4000-8000-000000000001')
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toHaveValue('00000000-0000-4000-8000-000000000011')
  await expect(page.getByRole('button', { name: '1h' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText(/limites atuais do ambiente, 2–8 °C/)).toBeVisible()
})
