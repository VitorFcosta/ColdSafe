import { expect, test, type WebSocketRoute } from '@playwright/test'
import examples from '../../contracts/examples/aiot.valid.json' with { type: 'json' }
import { mockDashboardAccount } from './monitoring-api'

test.skip(process.env.VITE_AIOT_ENABLED !== 'true', 'Executar com VITE_AIOT_ENABLED=true para a fronteira AIoT v3')

for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 812 }]) {
  test(`inferência simulada atualiza versão, preserva zero e envelhece a leitura (${viewport.width}px)`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockDashboardAccount(page)
    const telemetry = structuredClone(examples.find((item) => item.name === 'telemetry_received')!.payload)
    const original = structuredClone(examples.find((item) => item.name === 'prediction_available_zero_rul')!.payload)
    const environmentId = telemetry.environment_id
    const deviceId = telemetry.device_id
    const thresholds = { min_c: 2, max_c: 8, attention_margin_c: 0.5 }
    await page.route('**/api/v1/environments', (route) => route.fulfill({ json: { success: true, data: [{ id: environmentId, name: 'Laboratório' }] } }))
    await page.route(`**/api/v1/environments/${environmentId}/devices`, (route) => route.fulfill({ json: { success: true, data: [{ id: telemetry.device_record_id, environment_id: environmentId, name: 'Sensor AIoT', mqtt_device_id: deviceId, is_active: true }] } }))
    let prediction = original
    let ageSeconds = 4
    let summaryRequests = 0
    await page.route('**/api/v3/monitoring/summary?**', (route) => {
      summaryRequests++
      return route.fulfill({ json: { success: true, data: {
        environment: { id: environmentId, name: 'Laboratório' }, device: { id: deviceId }, thresholds,
        telemetry, prediction, prediction_unavailable_reason: null, persistence: 'persisted',
        freshness: { state: ageSeconds > 30 ? 'stale' : 'fresh', age_seconds: ageSeconds, last_event_id: telemetry.event_id, last_received_at: telemetry.received_at, stale_after_seconds: 30 },
        commands: { led: null, buzzer: null }, alerts: [],
      }, meta: { schema_version: 3 } } })
    })
    await page.route('**/api/v3/readings?**', (route) => route.fulfill({ json: { success: true, data: [], meta: { schema_version: 3, device_id: deviceId, start: '2026-10-12T17:00:00Z', end: '2026-10-12T18:01:00Z', count: 0, limit: 300, thresholds } } }))
    await page.route('**/api/v3/alerts?**', (route) => route.fulfill({ json: { success: true, data: { alerts: [] }, meta: { schema_version: 3, device_id: deviceId, count: 0 } } }))
    let socket: WebSocketRoute | undefined
    await page.routeWebSocket('**/api/v3/events?**', (route) => {
      socket = route
      route.onMessage((message) => expect(JSON.parse(String(message))).toMatchObject({ ticket: expect.any(String) }))
    })
    await page.goto('/dashboard')
    const panel = page.getByRole('region', { name: 'Previsão do equipamento', exact: true })
    await expect(panel).toContainText('12 / 100')
    await expect(panel).toContainText('0 h')
    await expect(panel).toContainText('fan-model-1')
    await expect(panel).toContainText('fan-features-1')
    await expect(panel.locator('time').first()).toHaveAttribute('datetime', telemetry.received_at!)
    await expect.poll(() => Boolean(socket)).toBe(true)

    prediction = { ...original, event_id: '00000000-0000-4000-8000-000000000900', data: { ...original.data, model_version: 'fan-model-2' } }
    socket!.send(JSON.stringify(prediction))
    await expect(panel).toContainText('fan-model-2')
    await expect(panel).not.toContainText('fan-model-1')
    const requests = summaryRequests
    socket!.send(JSON.stringify({ ...original, event_id: '00000000-0000-4000-8000-000000000901', correlation_id: '00000000-0000-4000-8000-000000000999', data: { ...original.data, source_event_id: '00000000-0000-4000-8000-000000000999' } }))
    await expect(panel).toContainText('fan-model-2')
    expect(summaryRequests).toBe(requests)
    await expect(page.getByRole('region', { name: 'Diagnóstico atual', exact: true })).toContainText('6,5 °C')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

    // The sensor clock must continue aging when predictions stop arriving.
    ageSeconds = 31
    socket!.send(JSON.stringify({ ...prediction, event_id: '00000000-0000-4000-8000-000000000902' }))
    await expect(panel.getByRole('status')).toContainText('Leitura desatualizada')
    await expect(panel).not.toContainText('12 / 100')
    await expect(panel).not.toContainText('0 h')
  })
}
