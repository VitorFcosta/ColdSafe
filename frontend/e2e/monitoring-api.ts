import { expect, type Page } from '@playwright/test'

export type DashboardStatus = 'normal' | 'attention' | 'critical' | 'stale' | 'no_data'

export async function mockMonitoringApi(
  page: Page,
  scenario: Readonly<{
    status: DashboardStatus
    temperature?: number
    ageSeconds?: number
  }>,
) {
  await page.route('**/api/v1/monitoring/summary', async (route) => {
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
    expect(['1h', '6h', '24h']).toContain(requestUrl.searchParams.get('period'))
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
