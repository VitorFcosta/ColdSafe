import { mkdir } from 'node:fs/promises'
import { expect, test, type Page, type WebSocketRoute } from '@playwright/test'
import examples from '../../contracts/examples/aiot.valid.json' with { type: 'json' }
import { mockDashboardAccount } from './monitoring-api'

test.skip(process.env.VITE_AIOT_ENABLED !== 'true', 'Ocultação integrada usa contratos AIoT v3')

const baseTelemetry = examples.find(item => item.name === 'telemetry_received')!.payload
const basePrediction = examples.find(item => item.name === 'prediction_available_zero_rul')!.payload
const baseCommand = examples.find(item => item.name === 'led_status_pending')!.payload
const environmentId = baseTelemetry.environment_id
const secondDevice = '00000000-0000-4000-8000-000000000702'
const rules = { health_critical: 20, health_recovery: 40, rul_critical_hours: 10, rul_recovery_hours: 30, open_count: 2, close_count: 2 }
const thresholds = { min_c: 2, max_c: 8, attention_margin_c: 1 }
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })

async function fixture(page: Page) {
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { success: false } }))
  await mockDashboardAccount(page)
  const state = { temperature: 6.5, health: 70, ready: 3, summaryGets: 0, insightsGets: 0, messagingGets: 0,
    commandGets: 0, commandPosts: 0, forbidden: false, confirmed: false }
  let revision = 800
  let command: typeof baseCommand | null = null
  let socket: WebSocketRoute | undefined
  function telemetry() {
    const at = new Date().toISOString()
    return { ...baseTelemetry, event_id: `00000000-0000-4000-8000-${String(revision).padStart(12, '0')}`,
      received_at: at, occurred_at: at, data: { ...baseTelemetry.data,
        measurements: { ...baseTelemetry.data.measurements,
          ambient_temperature: { ...baseTelemetry.data.measurements.ambient_temperature, value: state.temperature } },
        actuators: { ...baseTelemetry.data.actuators,
          led: { ...baseTelemetry.data.actuators.led, actual_state: state.confirmed } } } }
  }
  function prediction(source = telemetry()) {
    return { ...basePrediction, correlation_id: source.event_id, received_at: source.received_at, occurred_at: source.occurred_at,
      data: { ...basePrediction.data, source_event_id: source.event_id, input_received_at: source.received_at, health_score: state.health } }
  }
  const inventory = { equipment_id: baseTelemetry.data.equipment.equipment_id,
    sensors: Object.fromEntries(Object.entries(baseTelemetry.data.measurements).map(([role, value]) => [role, value.sensor_id])),
    actuators: { led: baseTelemetry.data.actuators.led.actuator_id, buzzer: baseTelemetry.data.actuators.buzzer.actuator_id } }
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { success: true,
    data: { user_id: 'test-user', email: 'admin@example.invalid', role: 'admin' } } }))
  await page.route('**/api/v1/environments', route => route.fulfill({ json: { success: true,
    data: [{ id: environmentId, name: 'Laboratório refrigerado' }] } }))
  await page.route(`**/api/v1/environments/${environmentId}/devices`, route => route.fulfill({ json: { success: true, data: [
    { id: baseTelemetry.device_record_id, environment_id: environmentId, mqtt_device_id: baseTelemetry.device_id, name: 'Ventilador 01', is_active: true },
    { id: secondDevice, environment_id: environmentId, mqtt_device_id: 'cold-second', name: 'Ventilador 02 sem leituras', is_active: true },
  ] } }))
  await page.route('**/api/v3/monitoring/summary?**', route => {
    state.summaryGets++
    if (state.forbidden) return route.fulfill({ status: 403, json: { success: false } })
    const second = new URL(route.request().url()).searchParams.get('device_id') === 'cold-second'
    const current = telemetry()
    return route.fulfill({ json: envelope({ environment: { id: environmentId, name: 'Laboratório refrigerado' },
      device: { id: second ? 'cold-second' : baseTelemetry.device_id }, thresholds, inventory,
      telemetry: second ? null : current, prediction: second ? null : prediction(current),
      prediction_unavailable_reason: null, persistence: second ? null : 'persisted',
      freshness: { state: second ? 'no_data' : 'fresh', age_seconds: second ? null : 0,
        last_event_id: second ? null : current.event_id, last_received_at: second ? null : current.received_at, stale_after_seconds: 30 },
      commands: { led: second ? null : command, buzzer: null }, alerts: [] }) })
  })
  await page.route('**/api/v3/insights?**', route => {
    state.insightsGets++
    if (state.forbidden) return route.fulfill({ status: 403, json: { success: false } })
    const second = new URL(route.request().url()).searchParams.get('device_id') === 'cold-second'
    return route.fulfill({ json: envelope({ device_id: second ? 'cold-second' : baseTelemetry.device_id,
      equipment_id: inventory.equipment_id, rules, prediction: second ? null : prediction(),
      availability: second ? 'no_data' : 'available', age_seconds: second ? null : 0, trend: second ? 'unknown' : 'stable', active_alerts: [] }) })
  })
  await page.route('**/api/v3/readings?**', route => route.fulfill({ json: { ...envelope([]), meta: {
    schema_version: 3, device_id: new URL(route.request().url()).searchParams.get('device_id'),
    start: new Date(Date.now() - 3_600_000).toISOString(), end: new Date().toISOString(), count: 0, limit: 300, thresholds,
  } } }))
  await page.route('**/api/v3/alerts?**', route => route.fulfill({ json: {
    ...envelope({ alerts: [] }), meta: { schema_version: 3, count: 0,
      device_id: new URL(route.request().url()).searchParams.get('device_id') },
  } }))
  await page.route('**/api/v3/devices/*/led/commands', route => {
    state.commandPosts++
    command = structuredClone(baseCommand)
    return route.fulfill({ status: 202, json: envelope(command) })
  })
  await page.route('**/api/v3/commands/*', route => {
    state.commandGets++
    if (state.confirmed && command) command = { ...command,
      data: { ...command.data, status: 'confirmed', confirmed_state: true } }
    return route.fulfill({ json: envelope(command) })
  })
  await page.route('**/api/v3/messaging**', route => {
    state.messagingGets++
    if (state.forbidden) return route.fulfill({ status: 403, json: { success: false } })
    const at = new Date().toISOString()
    return route.fulfill({ json: envelope(new URL(route.request().url()).pathname.endsWith('/messages')
      ? { sampled_at: at, connected: true, last_observed_at: at, stale: false, stale_after_seconds: 30,
        capacity_per_kind: 100, messages: [], dead_letters: [] }
      : { sampled_at: at, queues: [{ name: 'telemetry.api.q', messages: state.ready, messages_ready: state.ready,
        messages_unacknowledged: 0, consumers: 1, publish_rate: 1, deliver_rate: 1 }] }) })
  })
  await page.routeWebSocket('**/api/v3/events?**', route => { socket = route; route.onMessage(() => {}) })
  return { state, async update() {
    revision++
    if (socket) socket.send(JSON.stringify(telemetry()))
  }, async revokeSocket() {
    state.forbidden = true
    await expect.poll(() => Boolean(socket)).toBe(true)
    socket!.close({ code: 4403, reason: 'Access revoked by fixture' })
  } }
}

const cases = [
  { path: '/dashboard', label: 'Medições do ambiente', expected: '6,5 °C', updated: '8,5 °C' },
  { path: '/insights', label: 'Previsão do equipamento', expected: '70 / 100', updated: '55 / 100' },
  { path: '/digital-twin', label: 'Componentes do gêmeo digital', expected: '6,5 °C', updated: '8,5 °C' },
  { path: '/messaging', label: 'Estado das filas', expected: '3', updated: '17' },
]

for (const width of [1440, 320]) for (const scenario of cases) {
  test(`${scenario.path}: ocultar/mostrar mantém coleta, teclado e conteúdo atual (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const mock = await fixture(page)
    await page.goto(scenario.path)
    if (width === 320) await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    const region = page.getByRole('region', { name: scenario.label, exact: true })
    await expect(region).toContainText(scenario.expected)
    const control = page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true })
    await expect(control).toHaveCSS('font-size', width === 320 ? '28px' : '14px')
    await page.evaluate(() => document.fonts.ready)
    if (width === 1440 && scenario.path === '/dashboard') {
      const evidence = new URL('../../.impeccable/review/ux-03/', import.meta.url)
      await mkdir(evidence, { recursive: true })
      await page.locator('#dashboard-title').blur()
      await page.screenshot({ path: new URL('visao-geral.png', evidence).pathname })
    }
    await expect(control).toHaveAttribute('aria-expanded', 'true')
    await expect(control).toHaveAccessibleDescription('A coleta continua com os dados desta tela ocultos.')
    const id = await control.getAttribute('aria-controls')
    expect(id).toBeTruthy()
    const data = page.locator('[data-live-region]')
    await expect(data).toHaveAttribute('id', id!)
    await control.focus(); await page.keyboard.press('Enter')
    const show = page.getByRole('button', { name: 'Mostrar dados ao vivo', exact: true })
    await expect(show).toBeFocused()
    await expect(show).toHaveAttribute('aria-expanded', 'false')
    await expect(show).toHaveAccessibleDescription('Dados desta tela ocultos. A coleta e os pedidos em andamento continuam.')
    await expect(data).toBeHidden()
    await expect(data).toHaveAttribute('hidden', '')
    expect(await page.locator('main').ariaSnapshot()).not.toContain(`region "${scenario.label}"`)
    await page.keyboard.press('Tab')
    expect(await data.evaluate(el => el.contains(document.activeElement))).toBe(false)
    const before = scenario.path === '/insights' ? mock.state.insightsGets
      : scenario.path === '/messaging' ? mock.state.messagingGets : mock.state.summaryGets
    mock.state.temperature = 8.5; mock.state.health = 55; mock.state.ready = 17
    await mock.update()
    await expect.poll(() => scenario.path === '/insights' ? mock.state.insightsGets
      : scenario.path === '/messaging' ? mock.state.messagingGets : mock.state.summaryGets).toBeGreaterThan(before)
    await show.focus(); await page.keyboard.press('Space')
    await expect(region).toBeVisible()
    await expect(region).toContainText(scenario.updated)
    await expect(control).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(mock.state.commandPosts).toBe(0)
  })
}

test('LED pendente chega ao ACK durante ocultação sem desmontar nem repetir o POST', async ({ page }) => {
  const mock = await fixture(page)
  await page.goto('/dashboard')
  await page.getByRole('group', { name: 'Estado da luz e do som de aviso' }).locator('summary').click()
  await page.getByRole('button', { name: 'Ligar Luz', exact: true }).click()
  const request = page.getByRole('region', { name: 'Pedido do LED' })
  await expect(request).toContainText('Aguardando confirmação')
  await page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true }).click()
  mock.state.confirmed = true
  const before = mock.state.commandGets
  await expect.poll(() => mock.state.commandGets).toBeGreaterThan(before)
  await expect(page.locator('[data-live-region] .request')).toContainText('Confirmado por ACK')
  await mock.update()
  await page.getByRole('button', { name: 'Mostrar dados ao vivo', exact: true }).click()
  await expect(request).toBeVisible()
  await expect(request).toContainText('Confirmado por ACK · Ligado')
  await expect(page.getByRole('region', { name: 'Observação do LED' })).toContainText('Ligado')
  expect(mock.state.commandPosts).toBe(1)
})

test('troca de equipamento sai da ocultação e não reapresenta os dados anteriores', async ({ page }) => {
  await fixture(page)
  await page.goto('/dashboard')
  await expect(page.getByRole('region', { name: 'Medições do ambiente' })).toContainText('6,5 °C')
  await page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true }).click()
  await page.getByRole('combobox', { name: 'Dispositivo', exact: true }).selectOption(secondDevice)
  await expect(page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true })).toBeVisible()
  await expect(page.locator('[data-live-region]')).not.toHaveAttribute('hidden')
  await expect(page.locator('main')).not.toContainText('6,5 °C')
  await expect(page.locator('main')).toContainText('Sem dados')
})

test('revogação recebida pelo WebSocket continua ativa com dados ocultos', async ({ page }) => {
  const mock = await fixture(page)
  await page.goto('/digital-twin')
  await expect(page.getByRole('region', { name: 'Componentes do gêmeo digital' })).toBeVisible()
  await page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true }).click()
  await mock.revokeSocket()
  await expect(page.locator('main')).toContainText('Acesso ao equipamento indisponível')
  await expect(page.getByRole('region', { name: 'Componentes do gêmeo digital', includeHidden: true })).toHaveCount(0)
  await expect(page.locator('main')).not.toContainText('6,5 °C')
})

test('ocultar a cena suspende animação e preserva a pausa manual e seleção ao mostrar', async ({ page }) => {
  await fixture(page)
  await page.goto('/digital-twin')
  const components = page.getByRole('region', { name: 'Componentes do gêmeo digital' })
  await components.getByRole('button', { name: /Temperatura ambiente/ }).click()
  const scene = page.getByTestId('twin-scene')
  const paused = () => scene.evaluate(el => (el as HTMLElement & {
    __vueParentComponent: { exposed: { snapshot(): { paused: boolean } } }
  }).__vueParentComponent.exposed.snapshot().paused)
  await expect.poll(paused).toBe(false)
  await page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true }).click()
  await expect.poll(paused).toBe(true)
  await page.getByRole('button', { name: 'Mostrar dados ao vivo', exact: true }).click()
  await expect.poll(paused).toBe(false)
  await page.getByRole('button', { name: /Pausar/ }).click()
  await expect.poll(paused).toBe(true)
  await page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true }).click()
  await expect(scene).toBeHidden()
  await expect.poll(paused).toBe(true)
  await page.getByRole('button', { name: 'Mostrar dados ao vivo', exact: true }).click()
  await expect(scene).toBeVisible()
  await expect.poll(paused).toBe(true)
  await expect(components.locator('[aria-pressed="true"]')).toContainText('Temperatura ambiente')
})
