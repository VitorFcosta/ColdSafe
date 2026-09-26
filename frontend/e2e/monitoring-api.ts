import { expect, type Page } from '@playwright/test'

export type DashboardStatus = 'normal' | 'attention' | 'critical' | 'stale' | 'no_data'

export async function mockDashboardAccount(page: Page) {
  await page.routeWebSocket('**/api/v1/events?**', (socket) => {
    socket.onMessage(() => {})
  })
  await page.addInitScript(() => {
    sessionStorage.setItem('coldsafe-session', JSON.stringify({
      token: 'test-token', expires_at: '2099-01-01T00:00:00Z',
    }))
  })
  await page.route('**/api/v1/environments', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [{ id: 'lab-refrigerado', name: 'Laboratório Refrigerado' }] }),
  }))
  await page.route('**/api/v1/environments/lab-refrigerado/devices', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [
      { id: 'uuid-01', environment_id: 'lab-refrigerado', name: 'Sensor 1', mqtt_device_id: 'esp32-lab-01', is_active: true },
      { id: 'uuid-02', environment_id: 'lab-refrigerado', name: 'Sensor 2', mqtt_device_id: 'esp32-lab-02', is_active: true },
    ] }),
  }))
  await page.route('**/api/v1/devices/*/actuators', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: { led: null, buzzer: null }, meta: { schema_version: 2 } }),
  }))
  await page.route('**/api/v1/alerts?**', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: { alerts: [] }, meta: { schema_version: 2 } }),
  }))
}

export async function mockMonitoringApi(
  page: Page,
  scenario: Readonly<{
    status: DashboardStatus
    temperature?: number
    ageSeconds?: number
  }>,
) {
  await mockDashboardAccount(page)
  await page.route('**/api/v1/monitoring/summary**', async (route) => {
    const hasReading = scenario.status !== 'no_data'
    const receivedAt = '2026-09-09T12:00:00Z'

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          environment: { id: 'lab-refrigerado', name: 'Laboratório Refrigerado' },
          device: { id: 'esp32-lab-01' },
          reading: hasReading
            ? {
                temperature_c: scenario.temperature ?? 5,
                humidity_percent: 65,
                light_percent: 42,
                received_at: receivedAt,
              }
            : null,
          status: scenario.status,
          freshness: hasReading
            ? {
                is_stale: scenario.status === 'stale',
                age_seconds: scenario.ageSeconds ?? 2,
              }
            : null,
          thresholds: { min_c: 2, max_c: 8, attention_margin_c: 1 },
        },
      }),
    })
  })

  await page.route('**/api/v1/readings?**', async (route) => {
    const hasReading = scenario.status !== 'no_data'
    const receivedAt = '2026-09-09T12:00:00Z'
    const requestUrl = new URL(route.request().url())

    expect(requestUrl.searchParams.get('device_id')).toBe('esp32-lab-01')
    if (!requestUrl.searchParams.has('start')) {
      expect(['15m', '1h', '6h', '24h']).toContain(requestUrl.searchParams.get('period'))
    }
    expect(requestUrl.searchParams.get('limit')).toBe('300')

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          readings: hasReading
            ? [
                {
                  temperature_c: scenario.temperature ?? 5,
                  humidity_percent: 65,
                  light_percent: 42,
                  received_at: receivedAt,
                  status: scenario.status,
                },
              ]
            : [],
        },
        meta: {
          device_id: 'esp32-lab-01',
          start: '2026-09-09T11:00:00Z',
          end: '2026-09-09T12:00:00Z',
          count: hasReading ? 1 : 0,
          limit: 300,
        },
      }),
    })
  })
}
