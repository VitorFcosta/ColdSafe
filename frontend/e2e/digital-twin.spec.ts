import { expect, test, type Page, type WebSocketRoute } from '@playwright/test'
import examples from '../../contracts/examples/aiot.valid.json' with { type: 'json' }
import { mockDashboardAccount } from './monitoring-api'

test.skip(process.env.VITE_AIOT_ENABLED !== 'true', 'Executar com VITE_AIOT_ENABLED=true para o gêmeo digital v3')

type Telemetry = {
  event_id: string; device_id: string; device_record_id: string; environment_id: string; received_at: string
  data: { equipment: { equipment_id: string; running: boolean }; measurements: Record<string, { sensor_id: string; value: number; unit: string }>
    actuators: Record<'led' | 'buzzer', { actuator_id: string; actual_state: boolean }> }
}
const telemetryFixture = examples.find((item) => item.name === 'telemetry_received')!.payload as unknown as Telemetry
const predictionFixture = examples.find((item) => item.name === 'prediction_available_zero_rul')!.payload
const otherEnvironment = '00000000-0000-4000-8000-000000000702'
const otherDevice = '00000000-0000-4000-8000-000000000701'
const rules = { health_critical: 20, health_recovery: 40, rul_critical_hours: 10, rul_recovery_hours: 30, open_count: 2, close_count: 2 }
const thresholds = { min_c: 2, max_c: 8, attention_margin_c: 1 }

async function mockTwin(page: Page) {
  await mockDashboardAccount(page)
  let telemetry = structuredClone(telemetryFixture)
  let activeAlert = false
  let noData = false
  let stale = false
  let revision = 800
  let summaryRequests = 0
  let heldSummary: { started: () => void; released: Promise<void> } | null = null
  const sockets = new Map<string, WebSocketRoute>()
  const inventory = {
    equipment_id: telemetry.data.equipment.equipment_id,
    sensors: Object.fromEntries(Object.entries(telemetry.data.measurements).map(([role, sensor]) => [role, sensor.sensor_id])),
    actuators: { led: telemetry.data.actuators.led.actuator_id, buzzer: telemetry.data.actuators.buzzer.actuator_id },
  }
  const secondIds = Array.from({ length: 9 }, (_, index) => `00000000-0000-4000-8000-${String(710 + index).padStart(12, '0')}`)
  const secondInventory = { equipment_id: secondIds[0]!,
    sensors: Object.fromEntries(Object.keys(inventory.sensors).map((role, index) => [role, secondIds[index + 1]!])),
    actuators: { led: secondIds[7]!, buzzer: secondIds[8]! } }
  await page.route('**/api/v1/environments', (route) => route.fulfill({ json: { success: true, data: [
    { id: telemetry.environment_id, name: 'Laboratório Refrigerado' }, { id: otherEnvironment, name: 'Sala sem leituras' },
  ] } }))
  await page.route('**/api/v1/environments/*/devices', (route) => {
    const second = route.request().url().includes(otherEnvironment)
    return route.fulfill({ json: { success: true, data: [{
      id: second ? otherDevice : telemetry.device_record_id,
      environment_id: second ? otherEnvironment : telemetry.environment_id,
      name: second ? 'Ventilador sem dados' : 'Ventilador do laboratório',
      mqtt_device_id: second ? 'esp32.sala-02' : telemetry.device_id, is_active: true,
    }] } })
  })
  await page.route('**/api/v3/monitoring/summary?**', async (route) => {
    summaryRequests++
    const second = new URL(route.request().url()).searchParams.get('device_id') === 'esp32.sala-02'
    const empty = second || noData
    const json = { success: true, data: {
      environment: { id: second ? otherEnvironment : telemetry.environment_id, name: second ? 'Sala sem leituras' : 'Laboratório Refrigerado' },
      device: { id: second ? 'esp32.sala-02' : telemetry.device_id }, inventory: second ? secondInventory : inventory, thresholds,
      telemetry: empty ? null : telemetry, prediction: empty ? null : predictionFixture,
      persistence: empty ? null : 'persisted', prediction_unavailable_reason: null,
      freshness: { state: empty ? 'no_data' : stale ? 'stale' : 'fresh', age_seconds: empty ? null : stale ? 35 : 1,
        last_event_id: empty ? null : telemetry.event_id, last_received_at: empty ? null : telemetry.received_at, stale_after_seconds: 30 },
      commands: { led: null, buzzer: null }, alerts: [],
    }, meta: { schema_version: 3 } }
    const held = heldSummary
    heldSummary = null
    if (held) { held.started(); await held.released }
    return route.fulfill({ json })
  })
  await page.route('**/api/v3/insights?**', (route) => {
    const second = new URL(route.request().url()).searchParams.get('device_id') === 'esp32.sala-02'
    const empty = second || noData
    return route.fulfill({ json: { success: true, data: {
      device_id: second ? 'esp32.sala-02' : telemetry.device_id, equipment_id: second ? secondInventory.equipment_id : inventory.equipment_id, rules,
      prediction: empty ? null : predictionFixture, availability: empty ? 'no_data' : stale ? 'stale' : 'available',
      age_seconds: empty ? null : stale ? 35 : 1, trend: empty || stale ? 'unknown' : 'stable',
      active_alerts: activeAlert && !second ? [{ alert_id: '00000000-0000-4000-8000-000000000700', kind: 'predictive_failure',
        opened_at: telemetry.received_at, source_event_id: telemetry.event_id, prediction_event_id: predictionFixture.event_id }] : [],
    }, meta: { schema_version: 3 } } })
  })
  await page.route('**/api/v3/readings?**', (route) => route.fulfill({ json: { success: true, data: [], meta: {
    schema_version: 3, device_id: telemetry.device_id, start: '2026-10-12T17:00:00Z', end: '2026-10-12T18:01:00Z', count: 0, limit: 300, thresholds,
  } } }))
  await page.route('**/api/v3/alerts?**', (route) => route.fulfill({ json: { success: true, data: { alerts: [] }, meta: { schema_version: 3, count: 0 } } }))
  await page.routeWebSocket('**/api/v3/events?**', (socket) => {
    sockets.set(new URL(socket.url()).searchParams.get('device_id')!, socket)
    socket.onMessage((message) => expect(JSON.parse(String(message))).toMatchObject({ ticket: expect.any(String) }))
  })
  return {
    inventory, secondInventory, sockets, requests: () => summaryRequests,
    holdNextSummary() {
      let markStarted!: () => void
      let release!: () => void
      const started = new Promise<void>((resolve) => { markStarted = resolve })
      const released = new Promise<void>((resolve) => { release = resolve })
      heldSummary = { started: markStarted, released }
      return { started, release }
    },
    async update(change: { temperature?: number; led?: boolean; alert?: boolean; empty?: boolean; stale?: boolean }) {
      telemetry = { ...telemetry, event_id: `00000000-0000-4000-8000-${String(++revision).padStart(12, '0')}`,
        data: { ...telemetry.data, measurements: { ...telemetry.data.measurements,
          ambient_temperature: { ...telemetry.data.measurements.ambient_temperature!, value: change.temperature ?? telemetry.data.measurements.ambient_temperature!.value } },
        actuators: { ...telemetry.data.actuators, led: { ...telemetry.data.actuators.led, actual_state: change.led ?? telemetry.data.actuators.led.actual_state } } } }
      activeAlert = change.alert ?? activeAlert; noData = change.empty ?? noData; stale = change.stale ?? stale
      await expect.poll(() => sockets.has(telemetry.device_id)).toBe(true)
      sockets.get(telemetry.device_id)!.send(JSON.stringify(telemetry))
    },
  }
}

const components = (page: Page) => page.getByRole('region', { name: 'Componentes do gêmeo digital', exact: true })
const details = (page: Page) => page.getByRole('region', { name: 'Detalhes do componente', exact: true })

async function recordWebGL(page: Page) {
  // Browser instrumentation stays inside the test; the product exposes no renderer internals.
  await page.addInitScript(() => {
    const contexts: WebGLRenderingContext[] = []
    Object.assign(window, { twinTestContexts: contexts })
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (...args: Parameters<typeof original>) {
      const result = original.apply(this, args)
      if (result && String(args[0]).startsWith('webgl') && !contexts.includes(result as WebGLRenderingContext)) contexts.push(result as WebGLRenderingContext)
      return result
    } as typeof original
  })
}

test('cena WebGL real identifica nove peças e atualiza valores e estados via WS → REST', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await recordWebGL(page)
  const mock = await mockTwin(page)
  await page.goto('/digital-twin')
  const list = components(page)
  await expect(list.getByRole('button')).toHaveCount(9)
  await expect(list.getByRole('button', { name: /Temperatura ambiente/ })).toContainText('6,5 °C · Normal')
  await expect.poll(() => page.evaluate(() => (window as unknown as { twinTestContexts: WebGLRenderingContext[] }).twinTestContexts.filter((context) => !context.isContextLost()).length)).toBe(1)
  const canvas = page.locator('[data-testid=twin-scene] canvas')
  await expect(canvas).toBeVisible()
  const pieces = [
    { label: 'Temperatura ambiente', x: -3, y: 1.6 }, { label: 'Umidade', x: -3, y: 0.4 },
    { label: 'Luminosidade', x: -3, y: -0.8 }, { label: 'Vibração RMS', x: 3, y: 1.6 },
    { label: 'Corrente do motor', x: 3, y: 0.4 }, { label: 'Temperatura do motor', x: 3, y: -0.8 },
    { label: 'LED', x: -1, y: -2 }, { label: 'Buzzer', x: 1, y: -2 }, { label: 'Ventilador', x: 0, y: 0.4 },
  ]
  for (const piece of pieces) {
    const bounds = (await canvas.boundingBox())!
    const halfWidth = Math.max(5, 3.2 * bounds.width / bounds.height)
    await canvas.click({ position: { x: (piece.x / halfWidth + 1) / 2 * bounds.width, y: (1 - piece.y / 3.2) / 2 * bounds.height } })
    await expect(details(page).getByRole('heading')).toHaveText(piece.label)
    await expect(list.getByRole('button', { name: new RegExp(`^${piece.label}`) })).toHaveAttribute('aria-pressed', 'true')
  }
  for (const id of [mock.inventory.equipment_id, ...Object.values(mock.inventory.sensors), ...Object.values(mock.inventory.actuators)]) await expect(list).toContainText(id)
  await mock.update({ temperature: 7.5 })
  await expect(list.getByRole('button', { name: /Temperatura ambiente/ })).toContainText('7,5 °C · Atenção')
  await mock.update({ temperature: 10, led: true, alert: true })
  await expect(list.getByRole('button', { name: /^LED/ })).toContainText('Ligado · Normal')
  await expect(list.getByRole('button', { name: /Temperatura ambiente/ })).toContainText('10 °C · Crítico')
  await expect(list.getByRole('button', { name: /^Ventilador/ })).toContainText('Crítico')
  await expect(details(page)).toContainText('Crítico')
  await page.screenshot({ path: '/tmp/coldsafe-b227/evidence/twin-desktop-critical.png', fullPage: true })
  await mock.update({ temperature: 0 })
  await expect(list.getByRole('button', { name: /Temperatura ambiente/ })).toContainText('0 °C · Crítico')
  await mock.update({ stale: true })
  await expect(list.getByRole('button', { name: /Temperatura ambiente/ })).toContainText('Sem dados atuais · Sem dados')
  await expect(list.getByRole('button', { name: /^Ventilador/ })).toContainText('Sem dados atuais · Sem dados')
  expect(mock.requests()).toBeGreaterThanOrEqual(5)
})

test('troca ambiente sem reaproveitar leitura e libera contextos ao navegar três vezes', async ({ page }) => {
  await recordWebGL(page)
  const mock = await mockTwin(page)
  await page.goto('/digital-twin')
  await expect(components(page)).toContainText('6,5 °C')
  await expect.poll(() => mock.requests()).toBeGreaterThanOrEqual(2)
  const held = mock.holdNextSummary()
  await mock.update({ temperature: 12 })
  await held.started
  await page.locator('select[name=environment]').selectOption(otherEnvironment)
  await expect(page.locator('select[name=device]')).toHaveValue(otherDevice)
  const list = components(page)
  await expect(list.getByRole('button')).toHaveCount(9)
  for (const button of await list.getByRole('button').all()) {
    await expect(button).toContainText('Sem dados atuais · Sem dados')
    await expect(button).toBeEnabled()
  }
  for (const id of [mock.secondInventory.equipment_id, ...Object.values(mock.secondInventory.sensors), ...Object.values(mock.secondInventory.actuators)]) await expect(list).toContainText(id)
  await expect(list).not.toContainText(mock.inventory.equipment_id)
  await expect(list).not.toContainText('6,5 °C')
  const oldResponse = page.waitForResponse((response) => response.url().includes('/api/v3/monitoring/summary?') && response.url().includes(telemetryFixture.device_id))
  held.release()
  await oldResponse
  await expect(list).not.toContainText('12 °C')
  await expect(list).toContainText(mock.secondInventory.equipment_id)
  await mock.update({ temperature: 6.5 })
  await page.locator('select[name=environment]').selectOption(telemetryFixture.environment_id)
  await expect(list).toContainText('6,5 °C')
  for (const path of ['/dashboard', '/insights', '/dashboard']) {
    await page.locator(`nav[aria-label="Navegação principal"] a[href="${path}"]`).click()
    await expect(page).toHaveURL(new RegExp(`${path}$`))
    await expect(page.locator('[data-testid=twin-scene] canvas')).toHaveCount(0)
    await expect.poll(() => page.evaluate(() => (window as unknown as { twinTestContexts: WebGLRenderingContext[] }).twinTestContexts.every((context) => context.isContextLost()))).toBe(true)
    await page.locator('nav a[href="/digital-twin"]').click()
    await expect(list).toContainText('6,5 °C')
    await expect(page.locator('[data-testid=twin-scene] canvas')).toBeVisible()
  }
  expect(mock.requests()).toBeGreaterThanOrEqual(5)
})

test('320px mantém seleção pelo teclado e lista acessível após perda real de contexto WebGL', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 812 })
  await recordWebGL(page)
  await mockTwin(page)
  await page.goto('/digital-twin')
  const list = components(page)
  const temperature = list.getByRole('button', { name: /Temperatura ambiente/ })
  await expect(temperature).toContainText('6,5 °C')
  await temperature.focus()
  await page.keyboard.press('Enter')
  await expect(details(page).getByRole('heading')).toHaveText('Temperatura ambiente')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Space')
  await expect(details(page).getByRole('heading')).toHaveText('Umidade')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '/tmp/coldsafe-b227/evidence/twin-mobile-320.png', fullPage: true })
  const lost = await page.evaluate(() => {
    const context = (window as unknown as { twinTestContexts: WebGLRenderingContext[] }).twinTestContexts[0]
    const extension = context?.getExtension('WEBGL_lose_context')
    extension?.loseContext()
    return Boolean(extension)
  })
  expect(lost).toBe(true)
  await expect(page.getByRole('status').filter({ hasText: '3D indisponível' })).toBeVisible()
  await expect(list.getByRole('button')).toHaveCount(9)
  const led = list.getByRole('button', { name: /^LED/ })
  await led.focus()
  await page.keyboard.press('Enter')
  await expect(details(page).getByRole('heading')).toHaveText('LED')
  await expect(details(page)).toContainText('Desligado')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
