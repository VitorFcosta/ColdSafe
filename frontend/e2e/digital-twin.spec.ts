import { mkdir, writeFile } from 'node:fs/promises'
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
const commandFixture = examples.find((item) => item.name === 'led_status_pending')!.payload as unknown as {
  event_id: string; correlation_id: string; data: { command_id: string; status: string; desired_state: boolean; confirmed_state: boolean | null }
}

async function mockTwin(page: Page) {
  await mockDashboardAccount(page)
  let telemetry = structuredClone(telemetryFixture)
  let activeAlert = false
  let noData = false
  let stale = false
  let revision = 800
  let summaryRequests = 0
  let heldSummary: { started: () => void; released: Promise<void> } | null = null
  let command: typeof commandFixture | null = null
  let posts = 0
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
      commands: { led: second ? null : command, buzzer: null }, alerts: [],
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
  await page.route('**/api/v3/readings?**', (route) => route.fulfill({ json: { success: true, data: [{ telemetry, persistence: 'persisted' }], meta: {
    schema_version: 3, device_id: telemetry.device_id, start: '2026-10-12T17:46:00Z', end: '2026-10-12T18:01:00Z', count: 1, limit: 300, thresholds,
  } } }))
  await page.route('**/api/v3/devices/*/led/commands', (route) => {
    posts++
    const desired = route.request().postDataJSON().desired_state
    command = { ...structuredClone(commandFixture), event_id: `00000000-0000-4000-8000-${String(++revision).padStart(12, '0')}`,
      correlation_id: `00000000-0000-4000-8000-${String(950 + posts).padStart(12, '0')}`,
      data: { ...commandFixture.data, command_id: `00000000-0000-4000-8000-${String(950 + posts).padStart(12, '0')}`, desired_state: desired } }
    return route.fulfill({ status: 202, json: { success: true, data: command, meta: { schema_version: 3 } } })
  })
  await page.route('**/api/v3/commands/*', (route) => route.fulfill({ json: { success: true, data: command, meta: { schema_version: 3 } } }))
  await page.route('**/api/v3/alerts?**', (route) => route.fulfill({ json: { success: true, data: { alerts: [] }, meta: { schema_version: 3, count: 0 } } }))
  await page.routeWebSocket('**/api/v3/events?**', (socket) => {
    sockets.set(new URL(socket.url()).searchParams.get('device_id')!, socket)
    socket.onMessage((message) => expect(JSON.parse(String(message))).toMatchObject({ ticket: expect.any(String) }))
  })
  return {
    inventory, secondInventory, sockets, requests: () => summaryRequests, posts: () => posts,
    commandStatus(status: 'confirmed' | 'rejected' | 'unconfirmed') {
      command = { ...command!, data: { ...command!.data, status, confirmed_state: status === 'confirmed' ? command!.data.desired_state : null } }
    },
    holdNextSummary() {
      let markStarted!: () => void
      let release!: () => void
      const started = new Promise<void>((resolve) => { markStarted = resolve })
      const released = new Promise<void>((resolve) => { release = resolve })
      heldSummary = { started: markStarted, released }
      return { started, release }
    },
    async update(change: { temperature?: number; light?: number; vibration?: number; running?: boolean; led?: boolean; buzzer?: boolean; alert?: boolean; empty?: boolean; stale?: boolean }) {
      telemetry = { ...telemetry, event_id: `00000000-0000-4000-8000-${String(++revision).padStart(12, '0')}`,
        data: { ...telemetry.data, equipment: { ...telemetry.data.equipment, running: change.running ?? telemetry.data.equipment.running },
          measurements: { ...telemetry.data.measurements,
          light: { ...telemetry.data.measurements.light!, value: change.light ?? telemetry.data.measurements.light!.value },
          vibration: { ...telemetry.data.measurements.vibration!, value: change.vibration ?? telemetry.data.measurements.vibration!.value },
          ambient_temperature: { ...telemetry.data.measurements.ambient_temperature!, value: change.temperature ?? telemetry.data.measurements.ambient_temperature!.value } },
        actuators: { ...telemetry.data.actuators,
          buzzer: { ...telemetry.data.actuators.buzzer, actual_state: change.buzzer ?? telemetry.data.actuators.buzzer.actual_state },
          led: { ...telemetry.data.actuators.led, actual_state: change.led ?? telemetry.data.actuators.led.actual_state } } } }
      activeAlert = change.alert ?? activeAlert; noData = change.empty ?? noData; stale = change.stale ?? stale
      await expect.poll(() => sockets.has(telemetry.device_id)).toBe(true)
      sockets.get(telemetry.device_id)!.send(JSON.stringify(telemetry))
    },
  }
}


type SceneSnapshot = { animating: boolean; paused: boolean; hidden: boolean; reducedMotion: boolean; angle: number }
type SceneHandle = { projected: () => { id: string; key: string; x: number; y: number }[]; snapshot: () => SceneSnapshot }
async function sceneProjection(page: Page) {
  return page.getByTestId('twin-scene').evaluate((element) =>
    (element as HTMLElement & { __vueParentComponent: { exposed: SceneHandle } }).__vueParentComponent.exposed.projected())
}
async function sceneSnapshot(page: Page) {
  return page.getByTestId('twin-scene').evaluate((element) =>
    (element as HTMLElement & { __vueParentComponent: { exposed: SceneHandle } }).__vueParentComponent.exposed.snapshot())
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
  const points = await sceneProjection(page)
  expect(points).toHaveLength(9)
  for (const point of points) {
    await canvas.click({ position: { x: point.x, y: point.y } })
    await expect(list.locator('[aria-pressed="true"]')).toContainText(point.id)
    await expect(details(page)).toContainText(point.id)
    await expect(details(page).getByRole('heading', { level: 2 }).first()).not.toBeFocused()
    await expect(list.locator('[aria-pressed="true"]')).not.toBeFocused()
  }
  await list.getByRole('button', { name: /^Ventilador/ }).click()
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

test('ambiente e atuadores reagem ao WS com movimento reduzido; expiração local congela com socket aberto', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.clock.install()
  const mock = await mockTwin(page)
  await page.goto('/digital-twin')
  const list = components(page)
  await expect(list).toContainText('6,5 °C')
  await expect.poll(() => mock.requests()).toBeGreaterThanOrEqual(2)
  const canvas = page.locator('[data-testid=twin-scene] canvas')
  await expect(page.getByRole('status').filter({ hasText: 'Movimento reduzido' })).toBeVisible()
  const initial = await canvas.screenshot()
  await mock.update({ light: 0, vibration: 0, running: false, temperature: 0 })
  await expect(list.getByRole('button', { name: /Luminosidade/ })).toContainText('0 %')
  await expect(list.getByRole('button', { name: /^Ventilador/ })).toContainText('Parado')
  const dark = await canvas.screenshot()
  expect(dark.equals(initial)).toBe(false)
  await mock.update({ light: 100 })
  await expect(list.getByRole('button', { name: /Luminosidade/ })).toContainText('100 %')
  const bright = await canvas.screenshot()
  expect(bright.equals(dark)).toBe(false)
  await mock.update({ temperature: 40 })
  await expect(list.getByRole('button', { name: /Temperatura ambiente/ })).toContainText('40 °C')
  const hot = await canvas.screenshot()
  expect(hot.equals(bright)).toBe(false)
  await mock.update({ led: true, buzzer: true })
  await expect(list.getByRole('button', { name: /^LED/ })).toContainText('Ligado')
  await expect(list.getByRole('button', { name: /^Buzzer/ })).toContainText('Ligado')
  expect((await canvas.screenshot()).equals(hot)).toBe(false)
  const requests = mock.requests()
  await page.clock.fastForward(32_000)
  await expect(page.getByRole('status').filter({ hasText: 'Cena congelada' })).toBeVisible()
  await expect(list).toContainText('Sem dados atuais')
  expect(mock.requests()).toBe(requests)
  const frozen = await canvas.screenshot()
  await page.clock.fastForward(5_000)
  expect((await canvas.screenshot()).equals(frozen)).toBe(true)
  await mock.update({ temperature: 5, stale: false })
  await expect(list.getByRole('button', { name: /Temperatura ambiente/ })).toContainText('5 °C')
  await expect(page.getByRole('status').filter({ hasText: 'Cena congelada' })).toHaveCount(0)
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
    await page.locator(`nav[aria-label="Navegação da área"] a[href^="${path}?"]`).click()
    await expect(page).toHaveURL(`${path}?environment=${telemetryFixture.environment_id}&device=${telemetryFixture.device_record_id}`)
    await expect(page.locator('[data-testid=twin-scene] canvas')).toHaveCount(0)
    await expect.poll(() => page.evaluate(() => (window as unknown as { twinTestContexts: WebGLRenderingContext[] }).twinTestContexts.every((context) => context.isContextLost()))).toBe(true)
    await page.locator('nav[aria-label="Navegação da área"] a[href^="/digital-twin?"]').click()
    await expect(list).toContainText('6,5 °C')
    await expect(page.locator('[data-testid=twin-scene] canvas')).toBeVisible()
  }
  expect(mock.requests()).toBeGreaterThanOrEqual(5)
})

test('320px mantém seleção pelo teclado e lista acessível após perda real de contexto WebGL', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 812 })
  await recordWebGL(page)
  const mock = await mockTwin(page)
  await page.goto('/digital-twin')
  const list = components(page)
  const temperature = list.getByRole('button', { name: /Temperatura ambiente/ })
  await expect(temperature).toContainText('6,5 °C')
  await temperature.focus()
  await page.keyboard.press('Enter')
  await expect(details(page).getByRole('heading', { level: 2 }).first()).toHaveText('Temperatura ambiente')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Space')
  await expect(details(page).getByRole('heading', { level: 2 }).first()).toHaveText('Umidade')
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
  const jump = page.getByRole('link', { name: 'Ir para a lista de 9 componentes', exact: true })
  await jump.focus(); await page.keyboard.press('Enter')
  await expect(page.locator('#twin-components')).toBeFocused()
  const ids = [...Object.values(mock.inventory.sensors), ...Object.values(mock.inventory.actuators), mock.inventory.equipment_id]
  for (let index = 0; index < ids.length; index++) {
    await page.keyboard.press('Tab')
    const button = list.getByRole('button').nth(index)
    await expect(button).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(button).toHaveAttribute('aria-pressed', 'true')
    await expect(button).toBeFocused()
    await expect(details(page)).toContainText(ids[index]!)
  }
  expect(mock.posts()).toBe(0)
  const led = list.getByRole('button', { name: /^LED/ })
  await led.focus()
  await page.keyboard.press('Enter')
  await expect(details(page).getByRole('heading', { level: 2 }).first()).toHaveText('LED')
  await expect(details(page)).toContainText('Desligado')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('painel por ID separa previsão do equipamento e controle LED respeita ACK, rejeição e timeout', async ({ page }) => {
  await page.clock.install()
  const mock = await mockTwin(page)
  await page.goto('/digital-twin')
  const list = components(page)
  await list.getByRole('button', { name: /Temperatura ambiente/ }).click()
  const panel = details(page)
  await expect(panel).toContainText('Saúde/RUL deste item: não aplicável')
  await expect(panel).toContainText(mock.inventory.equipment_id)
  await expect(panel.getByRole('img', { name: 'Gráfico de linha da temperatura no período selecionado' })).toBeVisible()
  await expect(panel.getByRole('region', { name: 'Previsão do equipamento', exact: true })).toContainText('0 h')
  await list.getByRole('button', { name: /^LED/ }).click()
  await expect(panel).toContainText('não possui histórico próprio')
  const control = panel.getByRole('region', { name: 'Controle do LED selecionado' })
  const toggle = control.getByRole('button', { name: 'Ligar Luz' })
  await expect(toggle).toBeEnabled()
  await toggle.click()
  await expect(control).toContainText('Aguardando confirmação')
  await expect(toggle).toBeDisabled()
  await expect(list.getByRole('button', { name: /^LED/ })).toContainText('Desligado')
  expect(mock.posts()).toBe(1)
  mock.commandStatus('confirmed'); await page.clock.fastForward(1000)
  await expect(control.getByRole('button', { name: 'Desligar Luz' })).toBeEnabled()
  await expect(list.getByRole('button', { name: /^LED/ })).toContainText('Desligado')
  await mock.update({ led: true })
  await expect(list.getByRole('button', { name: /^LED/ })).toContainText('Ligado')
  await control.getByRole('button', { name: 'Desligar Luz' }).click()
  mock.commandStatus('rejected'); await page.clock.fastForward(1000)
  await expect(control).toContainText('Comando rejeitado')
  await control.getByRole('button', { name: 'Ligar Luz' }).click()
  mock.commandStatus('unconfirmed'); await page.clock.fastForward(1000)
  await expect(control.getByText('Sem confirmação', { exact: true })).toBeVisible()
  await expect(control.getByRole('button', { name: 'Ligar Luz' })).toBeEnabled()
  expect(mock.posts()).toBe(3)
  await list.getByRole('button', { name: /^Buzzer/ }).click()
  await expect(panel).toContainText('Buzzer segue a regra térmica')
  await expect(panel.getByRole('button', { name: /Ligar Luz|Desligar Luz/ })).toHaveCount(0)
  await page.screenshot({ path: '/tmp/coldsafe-b229/twin-item-desktop.png', fullPage: true })
})

test('visualizador inspeciona LED pelo teclado sem enviar comandos', async ({ page }) => {
  const mock = await mockTwin(page)
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { success: true, data: { user_id: 'test-user', email: 'test@example.com', role: 'viewer' } } }))
  await page.setViewportSize({ width: 320, height: 812 })
  await page.goto('/digital-twin')
  const led = components(page).getByRole('button', { name: /^LED/ })
  await led.focus(); await page.keyboard.press('Enter')
  const panel = details(page)
  await expect(panel).toContainText('Modo visualizador')
  await expect(panel.getByRole('button', { name: 'Ligar Luz' })).toBeDisabled()
  expect(mock.posts()).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '/tmp/coldsafe-b229/twin-item-mobile-320.png', fullPage: true })
})


test.describe('RD-09 — pausa visual na cena de produção', () => {
  test.use({ hasTouch: true })
  for (const width of [1440, 390]) {
    test(`pausa por teclado/toque conserva dados, seleção e foco (${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1024 })
      const mock = await mockTwin(page)
      await page.goto('/digital-twin')
      await expect(components(page)).toContainText('6,5 °C')
      const pause = page.getByRole('button', { name: 'Pausar animação', exact: true })
      if (width === 390) await pause.tap()
      else { await pause.focus(); await page.keyboard.press('Enter') }
      const resume = page.getByRole('button', { name: 'Retomar animação', exact: true })
      await expect(resume).toHaveAttribute('aria-pressed', 'true')
      if (width === 1440) await expect(resume).toBeFocused()
      const frozen = await sceneSnapshot(page)
      expect(frozen.paused).toBe(true)
      expect(frozen.animating).toBe(false)
      await mock.update({ temperature: 7.5, led: true })
      await expect(components(page)).toContainText('7,5 °C')
      if (width === 1440) await expect(resume).toBeFocused()
      await components(page).getByRole('button', { name: /^LED/ }).click()
      expect((await sceneSnapshot(page)).angle).toBe(frozen.angle)
      expect((await sceneSnapshot(page)).paused).toBe(true)
      expect((await sceneSnapshot(page)).animating).toBe(false)
      await expect(details(page)).toContainText('Ligado')
      await expect(page.locator('#twin-animation-reason')).toContainText('pausada')
      const evidence = new URL('../../.impeccable/review/rd-09/', import.meta.url)
      await mkdir(evidence, { recursive: true })
      const figure = page.getByRole('region', { name: 'Visualização do gêmeo digital', exact: true })
      await figure.scrollIntoViewIfNeeded()
      await page.screenshot({ path: new URL(width === 1440 ? 'desktop-viewport.png' : 'mobile-viewport.png', evidence).pathname, fullPage: false })
      await page.evaluate(() => scrollTo(0, 0))
      await page.screenshot({ path: new URL(width === 1440 ? 'desktop.png' : 'mobile.png', evidence).pathname, fullPage: true })
      await figure.locator('canvas').screenshot({ path: new URL(width === 1440 ? 'scene-desktop.png' : 'scene-mobile.png', evidence).pathname })
      if (width === 390) {
        await page.setViewportSize({ width: 320, height: 800 })
        await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
        await resume.focus()
        await expect(resume).toBeInViewport()
        const reflow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, fontSize: getComputedStyle(document.documentElement).fontSize }))
        expect(reflow.scrollWidth).toBe(320)
        await page.screenshot({ path: new URL('pause-320-text-200.png', evidence).pathname, fullPage: false })
        await writeFile(new URL('reflow.json', evidence), JSON.stringify(reflow, null, 2))
      }
      await mock.update({ stale: true })
      await expect(page.locator('#twin-animation-reason')).toContainText('sem telemetria atual')
      if (await resume.isEnabled()) await resume.click()
      expect((await sceneSnapshot(page)).animating).toBe(false)
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await mock.update({ stale: false })
      await expect(page.locator('#twin-animation-reason')).toContainText('Movimento reduzido')
      expect((await sceneSnapshot(page)).animating).toBe(false)
      if ((await sceneSnapshot(page)).paused) await page.getByRole('button', { name: 'Retomar animação', exact: true }).click()
      await page.emulateMedia({ reducedMotion: 'no-preference' })
      await expect.poll(async () => (await sceneSnapshot(page)).animating).toBe(true)
      expect(mock.posts()).toBe(0)
    })
  }
})

test.describe('RD-10 — composição e inspeção', () => {
  for (const width of [1440, 390]) {
    test(`contexto, grandezas e leitura selecionada seguem a composição (${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1024 })
      const mock = await mockTwin(page)
      await page.goto('/digital-twin')
      const list = components(page)
      await expect(list.getByRole('button')).toHaveCount(9)
      await expect(page.getByRole('navigation', { name: 'Navegação da área', exact: true })).toHaveCount(1)
      const metrics = page.getByRole('region', { name: 'Grandezas do equipamento', exact: true })
      if (width === 1440) {
        await expect(metrics).toBeVisible()
        await expect(metrics.locator('dt')).toHaveCount(6)
        for (const label of ['Temperatura ambiente', 'Umidade', 'Luminosidade', 'Vibração RMS', 'Corrente do motor', 'Temperatura do motor']) await expect(metrics).toContainText(label)
        await expect(metrics).toContainText('Leitura atual')
        await mock.update({ temperature: 0 })
        await expect(metrics).toContainText('0 °C')
      }
      await list.getByRole('button', { name: /Corrente do motor/ }).click()
      const panel = details(page)
      await expect(panel.getByRole('heading', { name: 'Histórico de corrente do motor · últimos 15 minutos', exact: true })).toBeVisible()
      await expect(panel).toContainText('1,4 A')
      await expect(panel).toContainText('Leitura atual')
      await expect(panel).toContainText('Saúde/RUL deste item: não aplicável')
      const figure = page.getByRole('region', { name: 'Visualização do gêmeo digital', exact: true })
      const preview = page.getByRole('region', { name: 'Leitura selecionada', exact: true })
      const jump = page.getByRole('link', { name: 'Ir para a lista de 9 componentes', exact: true })
      if (width === 390) {
        await expect(preview).toContainText('1,4 A')
        await expect(preview).toContainText(mock.inventory.sensors.motor_current!)
        const order = await page.evaluate(() => {
          const selectors = ['[aria-label="Visualização do gêmeo digital"]', '[aria-label="Leitura selecionada"]', '.components-jump', '[aria-label="Componentes do gêmeo digital"]', '[aria-label="Detalhes do componente"]']
          return selectors.map(selector => document.querySelector(selector)!.getBoundingClientRect().top)
        })
        expect(order).toEqual([...order].sort((a,b) => a-b))
        const originalQuery = new URL(page.url()).search
        await jump.focus(); await page.keyboard.press('Enter')
        await expect(page.locator('#twin-components')).toBeFocused()
        expect(new URL(page.url()).pathname).toBe('/digital-twin')
        expect(new URL(page.url()).search).toBe(originalQuery)
      }
      await page.getByRole('button', { name: 'Pausar animação', exact: true }).click()
      const evidence = new URL('../../.impeccable/review/rd-10/', import.meta.url)
      await mkdir(evidence, { recursive: true })
      await page.evaluate(() => scrollTo(0,0))
      await page.screenshot({ path: new URL(width===1440?'desktop.png':'mobile.png',evidence).pathname, fullPage:true })
      await page.screenshot({ path: new URL(width===1440?'desktop-viewport.png':'mobile-viewport.png',evidence).pathname })
      if (width===1440) await page.screenshot({path:new URL('hero-repro.png',evidence).pathname})
      await figure.scrollIntoViewIfNeeded()
      await page.screenshot({path:new URL(width===1440?'scene-list-desktop.png':'scene-mobile.png',evidence).pathname})
      if (width===390) {
        await page.setViewportSize({width:320,height:812})
        await page.addStyleTag({content:'html { font-size: 200% !important; }'})
        await list.getByRole('button',{name:/Corrente do motor/}).focus()
        await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(320)
        const reflow=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,fontSize:getComputedStyle(document.documentElement).fontSize,
          overflow:[...document.querySelectorAll('body *')].map(el=>({tag:el.tagName,className:el.className,id:el.id,right:el.getBoundingClientRect().right,width:el.getBoundingClientRect().width})).filter(el=>el.right>innerWidth+1)}))
        await writeFile(new URL('reflow.json',evidence),JSON.stringify(reflow,null,2))
        expect(reflow.scrollWidth).toBe(320)
        await page.screenshot({path:new URL('mobile-320-text-200.png',evidence).pathname})
      }
      expect(mock.posts()).toBe(0)
    })
  }
})

test('RD-18 C-11: LED pendente atravessa vistas e retoma o mesmo comando sem segundo POST', async ({ page }) => {
  await page.clock.install()
  const mock = await mockTwin(page)
  const commandReads: string[] = []
  page.on('request', request => {
    const path = new URL(request.url()).pathname
    if (request.method() === 'GET' && path.startsWith('/api/v3/commands/')) commandReads.push(path.split('/').at(-1)!)
  })
  await page.goto('/digital-twin')
  await components(page).getByRole('button', { name: /^LED/ }).click()
  const control = () => details(page).getByRole('region', { name: 'Controle do LED selecionado' })
  const created = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/led/commands'))
  await control().getByRole('button', { name: 'Ligar Luz' }).click()
  const commandId = (await (await created).json()).data.data.command_id as string
  await expect(control()).toContainText('Aguardando confirmação')
  await page.clock.fastForward(1000)
  await expect.poll(() => commandReads).toContain(commandId)
  const area = () => page.getByRole('navigation', { name: 'Navegação da área', exact: true })
  await area().getByRole('link', { name: 'Visão geral', exact: true }).click()
  const actuators = page.locator('details[aria-label="Estado dos atuadores"]')
  await expect(actuators.locator('summary')).toContainText('Aguardando confirmação')
  await actuators.locator('summary').click()
  await expect(actuators.getByRole('button', { name: 'Ligar Luz' })).toBeDisabled()
  const readsBeforeReturn = commandReads.length
  await area().getByRole('link', { name: 'Gêmeo digital', exact: true }).click()
  await components(page).getByRole('button', { name: /^LED/ }).click()
  await expect(control()).toContainText('Aguardando confirmação')
  await expect(control().getByRole('button', { name: 'Ligar Luz' })).toBeDisabled()
  await page.clock.fastForward(1000)
  await expect.poll(() => commandReads.length).toBeGreaterThan(readsBeforeReturn)
  expect(commandReads.every(id => id === commandId)).toBe(true)
  expect(mock.posts()).toBe(1)
  mock.commandStatus('unconfirmed')
  await page.clock.fastForward(1000)
  await expect(control()).toContainText('Sem confirmação')
  await expect(control().getByRole('button', { name: 'Ligar Luz' })).toBeEnabled()
  await expect(components(page).getByRole('button', { name: /^LED/ })).toContainText('Desligado')
  expect(mock.posts()).toBe(1)
})
