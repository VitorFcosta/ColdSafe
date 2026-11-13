import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page, type WebSocketRoute } from '@playwright/test'
import examples from '../../contracts/examples/aiot.valid.json' with { type: 'json' }
import { mockDashboardAccount } from './monitoring-api'

test.skip(process.env.VITE_AIOT_ENABLED !== 'true', 'RD-07: executar com AIoT v3')
const evidence = new URL('../../.impeccable/review/rd-07/', import.meta.url)

async function mockOverview(page: Page, viewer = false) {
  await mockDashboardAccount(page)
  if (viewer) await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
    success: true, data: { user_id: 'test-user', email: 'test@example.com', role: 'viewer' },
  } }))
  let telemetry = structuredClone(examples.find((item) => item.name === 'telemetry_received')!.payload)
  const original = structuredClone(examples.find((item) => item.name === 'prediction_available_zero_rul')!.payload)
  const environmentId = telemetry.environment_id, deviceId = telemetry.device_id
  const thresholds = { min_c: 2, max_c: 8, attention_margin_c: 0.5 }
  let age = 4, historyError = false, requests = 0
  let socket: WebSocketRoute | undefined
  const posts: string[] = []
  page.on('request', (request) => { if (request.method() === 'POST' && !request.url().includes('/auth/ws-ticket')) posts.push(request.url()) })
  await page.route('**/api/v1/environments', (route) => route.fulfill({ json: { success: true, data: [{ id: environmentId, name: 'Laboratório refrigerado' }] } }))
  await page.route(`**/api/v1/environments/${environmentId}/devices`, (route) => route.fulfill({ json: { success: true, data: [{ id: telemetry.device_record_id, environment_id: environmentId, name: 'Ventilador 01', mqtt_device_id: deviceId, is_active: true }] } }))
  await page.route('**/api/v3/monitoring/summary?**', (route) => {
    requests++
    return route.fulfill({ json: { success: true, data: {
      environment: { id: environmentId, name: 'Laboratório refrigerado' }, device: { id: deviceId }, thresholds,
      telemetry, prediction: original, prediction_unavailable_reason: null, persistence: 'persisted',
      freshness: { state: age > 30 ? 'stale' : 'fresh', age_seconds: age, last_event_id: telemetry.event_id, last_received_at: telemetry.received_at, stale_after_seconds: 30 },
      commands: { led: null, buzzer: null }, alerts: [],
    }, meta: { schema_version: 3 } } })
  })
  await page.route('**/api/v3/readings?**', (route) => {
    if (historyError) return route.fulfill({ status: 503, json: { success: false } })
    const url = new URL(route.request().url())
    const start = url.searchParams.get('start') ?? '2026-10-12T17:00:00Z'
    const end = url.searchParams.get('end') ?? '2026-10-12T18:01:00Z'
    const rows = [0, 20, 90].map((seconds, index) => {
      const timestamp = new Date(Date.parse(end) - 120_000 + seconds * 1000).toISOString()
      return { persistence: 'persisted', telemetry: { ...telemetry, event_id: `00000000-0000-4000-8000-00000000090${index}`,
        occurred_at: timestamp, received_at: timestamp, data: { ...telemetry.data,
          measurements: { ...telemetry.data.measurements, motor_current: { ...telemetry.data.measurements.motor_current, value: index === 0 ? 0 : 1.8 } } } } }
    })
    return route.fulfill({ json: { success: true, data: rows, meta: { schema_version: 3, device_id: deviceId, start, end, count: rows.length, limit: 300, thresholds } } })
  })
  await page.route('**/api/v3/alerts?**', (route) => route.fulfill({ json: { success: true, data: { alerts: [] }, meta: { schema_version: 3, device_id: deviceId, count: 0 } } }))
  await page.routeWebSocket('**/api/v3/events?**', (route) => { socket = route; route.onMessage(() => {}) })
  return { posts, get requests() { return requests }, stale: () => { age = 45 }, failHistory: () => { historyError = true },
    refresh: () => socket!.send(JSON.stringify({ ...original, event_id: '00000000-0000-4000-8000-000000000999' })),
    newReading: () => {
      telemetry = { ...telemetry, event_id: '00000000-0000-4000-8000-000000000998', occurred_at: '2026-10-12T18:01:00Z', received_at: '2026-10-12T18:01:00Z' }
      socket!.send(JSON.stringify(telemetry))
    } }
}

for (const width of [1440, 390]) {
  test(`hierarquia, grandezas, períodos, tabela e LED (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1024 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const mock = await mockOverview(page)
    await page.goto(width === 390 ? '/dashboard/' : '/dashboard')
    await expect(page.getByRole('navigation', { name: 'Navegação da área', exact: true })).toHaveCount(1)
    const metrics = page.getByRole('region', { name: 'Medições do ambiente', exact: true })
    await expect(metrics.getByRole('article')).toHaveCount(6)
    const history = page.getByRole('region', { name: /^Histórico ·/ })
    await page.getByRole('combobox', { name: 'Medição do gráfico' }).selectOption('motor_current_a')
    await expect(history.getByRole('heading')).toHaveText('Histórico · corrente do motor')
    for (const period of ['15m', '1h', '6h', '24h']) await expect(page.getByRole('button', { name: period, exact: true })).toBeVisible()
    await expect(history.getByRole('img')).toBeVisible()
    await expect(history).toContainText('1 lacuna')
    const summary = history.locator('details summary')
    await summary.focus(); await page.keyboard.press('Enter')
    await expect(history.getByRole('table')).toBeVisible()
    await expect(history.getByRole('cell', { name: '0 A', exact: true })).toBeVisible()
    await page.keyboard.press('Tab')
    await expect(history.getByRole('region', { name: 'Leituras individuais de corrente do motor' })).toBeFocused()
    const prediction = page.getByRole('region', { name: 'Previsão do equipamento', exact: true })
    await expect(prediction).toContainText('0 h')
    await expect(prediction).toContainText('dados gerados para teste')
    const positions = await page.evaluate(() => {
      const y = (selector: string) => document.querySelector(selector)!.getBoundingClientRect().top
      return { selection: y('.selection-panel'), navigation: y('nav[aria-label="Navegação da área"]'), metrics: y('.metrics-grid') }
    })
    expect(positions.navigation).toBeLessThan(positions.selection)
    expect(positions.selection).toBeLessThan(positions.metrics)
    const left = await history.boundingBox(), right = await prediction.boundingBox()
    if (width === 1440) expect(left!.y).toBe(right!.y)
    else expect(right!.y).toBeGreaterThan(left!.y + left!.height)
    const tops = await metrics.getByRole('article').evaluateAll((items) => items.map((item) => item.getBoundingClientRect().top))
    expect(tops[0]).toBe(tops[1])
    if (width === 1440) expect(new Set(tops).size).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await summary.focus(); await page.keyboard.press('Enter')
    await page.evaluate(() => scrollTo(0, 0))
    await page.evaluate(() => document.fonts.ready)
    await mkdir(evidence, { recursive: true })
    await page.screenshot({ path: new URL(width === 1440 ? 'desktop-viewport.png' : 'mobile-viewport.png', evidence).pathname, fullPage: false })
    await page.screenshot({ path: new URL(width === 1440 ? 'desktop.png' : 'mobile.png', evidence).pathname, fullPage: true })
    if (width === 1440) {
      const styles = await page.evaluate(() => {
        const targets = ['.measurement h2', '.metric-value', '.measurement-condition', '.period-control [aria-pressed="true"]', '.prediction-origin']
        return targets.map((selector) => {
          const element = document.querySelector(selector)!
          const style = getComputedStyle(element)
          let ancestor: Element | null = element
          let background = 'rgba(0, 0, 0, 0)'
          while (ancestor && background === 'rgba(0, 0, 0, 0)') {
            background = getComputedStyle(ancestor).backgroundColor
            ancestor = ancestor.parentElement
          }
          return { selector, color: style.color, background, fontSize: style.fontSize }
        })
      })
      await writeFile(new URL('rendered-colors.json', evidence), JSON.stringify({ browser: page.context().browser()!.version(), styles }, null, 2))
    }
    const actuators = page.getByRole('group', { name: 'Estado da luz e do som de aviso' })
    await actuators.locator('summary').click()
    await expect(page.getByRole('region', { name: 'Observação do LED' })).toContainText('Desligado')
    await expect(page.getByRole('region', { name: 'Pedido do LED' })).toContainText('Sem confirmação registrada')
    expect(mock.posts).toEqual([])
  })
}

test('UX-01: alertas e luz ficam perto da leitura e a comparação mostra só o período com dados', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  const now = new Date('2026-10-12T18:01:00Z')
  await page.clock.setFixedTime(now)
  const mock = await mockOverview(page)
  const telemetry = examples.find((item) => item.name === 'telemetry_received')!.payload
  await page.route('**/api/v3/readings?**', (route) => {
    const { searchParams } = new URL(route.request().url())
    const start = searchParams.get('start'), end = searchParams.get('end')
    if (!start || !end) return route.fallback()
    const rows = end === now.toISOString() ? Array.from({ length: 300 }, (_, index) => {
      const timestamp = new Date(+now - (300 - index) * 5_000).toISOString()
      return { persistence: 'persisted', telemetry: { ...telemetry,
        event_id: `00000000-0000-4000-8000-${String(index + 1000).padStart(12, '0')}`,
        occurred_at: timestamp, received_at: timestamp, data: { ...telemetry.data, measurements: {
          ...telemetry.data.measurements,
          ambient_temperature: { ...telemetry.data.measurements.ambient_temperature, value: 5.1 + Math.sin(index * 13) * 0.15 },
        } },
      } }
    }) : []
    return route.fulfill({ json: { success: true, data: rows, meta: {
      schema_version: 3, device_id: telemetry.device_id, start, end, count: rows.length, limit: 300,
      thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
    } } })
  })
  await page.goto('/dashboard')
  const metrics = page.getByRole('region', { name: 'Medições do ambiente', exact: true })
  const alerts = page.getByRole('region', { name: /^Alertas do dispositivo/ })
  const actuators = page.getByRole('group', { name: 'Estado da luz e do som de aviso' })
  const history = page.getByRole('region', { name: /^Histórico ·/ })
  const comparison = page.getByRole('region', { name: 'Comparação de temperatura', exact: true })
  await expect(alerts).toContainText('Nenhum alerta neste período.')
  await expect(actuators.locator('summary')).toContainText('Última leitura: luz desligada')
  await expect(comparison.getByRole('img', { name: 'Gráfico de temperatura do período selecionado', exact: true })).toBeVisible()
  await expect(comparison).toContainText('Sem leituras no período anterior para comparar.')
  await expect(comparison).toContainText('Limite de 300 atingido')
  await expect(comparison.getByRole('button', { name: 'Atualizar alertas e comparação', exact: true })).toBeVisible()
  const [measurementsBox, alertsBox, actuatorsBox, historyBox, comparisonBox] = await Promise.all(
    [metrics, alerts, actuators, history, comparison].map((section) => section.boundingBox()),
  )
  expect(alertsBox!.y).toBeGreaterThan(measurementsBox!.y + measurementsBox!.height)
  expect(actuatorsBox!.y).toBe(alertsBox!.y)
  expect(historyBox!.y).toBeGreaterThan(Math.max(alertsBox!.y + alertsBox!.height, actuatorsBox!.y + actuatorsBox!.height))
  expect(comparisonBox!.width).toBeCloseTo(measurementsBox!.width, 0)

  const evidenceDir = new URL('../../.impeccable/review/ux-01/', import.meta.url)
  await mkdir(evidenceDir, { recursive: true })
  await page.screenshot({ path: new URL('desktop.png', evidenceDir).pathname })
  await comparison.screenshot({ path: new URL('comparacao-periodo-anterior-vazio.png', evidenceDir).pathname })
  const tableSummary = comparison.getByText('Ver leituras de temperatura em tabela', { exact: true })
  await tableSummary.focus()
  await page.keyboard.press('Enter')
  await expect(comparison.getByRole('table')).toBeVisible()
  await expect(comparison.getByRole('row')).toHaveCount(301)
  await actuators.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('region', { name: 'Observação do LED' })).toContainText('Desligado')
  expect(mock.posts).toEqual([])
})

test('falha parcial e previsão antiga não removem leitura válida; viewer consulta sem atuar', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  const mock = await mockOverview(page, true)
  mock.failHistory()
  await page.goto('/dashboard')
  await expect(page.getByRole('region', { name: 'Diagnóstico atual', exact: true })).toContainText('6,5 °C')
  await expect(page.getByRole('region', { name: /^Histórico ·/ })).toContainText('histórico não pôde ser carregado')
  const prediction = page.getByRole('region', { name: 'Previsão do equipamento', exact: true })
  await expect(prediction).toContainText('0 h')
  mock.newReading()
  await expect(prediction).toContainText('Previsão desatualizada')
  await expect(prediction).not.toContainText('12 / 100')
  await expect(prediction).not.toContainText('0 h')
  await mkdir(evidence, { recursive: true })
  await page.screenshot({ path: new URL('partial-error.png', evidence).pathname, fullPage: true })
  await page.getByRole('group', { name: 'Estado da luz e do som de aviso' }).locator('summary').click()
  await expect(page.getByRole('button', { name: 'Ligar Luz', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Atualizar estado', exact: true }).click()
  expect(mock.posts).toEqual([])
})

test('320 px com texto 200%, leitura antiga, teclado e atualização sem mover foco', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const mock = await mockOverview(page)
  mock.stale()
  await page.goto('/dashboard')
  await expect(page.getByText('Leitura desatualizada', { exact: true })).toBeVisible()
  await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
  const control = page.getByRole('combobox', { name: 'Medição do gráfico' })
  await control.focus()
  const before = mock.requests
  mock.refresh()
  await expect.poll(() => mock.requests).toBeGreaterThan(before)
  await expect(control).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const periodLabelsFit = () => page.getByRole('group', { name: 'Período do histórico' }).getByRole('button').evaluateAll((buttons) => buttons.every((button) => {
    const range = document.createRange()
    range.selectNodeContents(button)
    const label = range.getBoundingClientRect(), bounds = button.getBoundingClientRect()
    return label.left >= bounds.left && label.right <= bounds.right
  }))
  expect(await periodLabelsFit()).toBe(true)
  await mkdir(evidence, { recursive: true })
  for (const period of ['15m', '1h']) {
    await page.getByRole('button', { name: period, exact: true }).click()
    expect(await periodLabelsFit()).toBe(true)
    await page.getByRole('group', { name: 'Período do histórico' }).screenshot({ path: new URL(`periods-320-text-200-${period}.png`, evidence).pathname })
  }
  const rows = await page.getByRole('region', { name: 'Medições do ambiente' }).getByRole('article').evaluateAll((items) => items.map((item) => item.getBoundingClientRect().top))
  expect(rows[0]).toBe(rows[1])
  await page.getByRole('group', { name: 'Estado da luz e do som de aviso' }).locator('summary').click()
  await expect(page.getByRole('region', { name: 'Observação do LED' })).toContainText('Estado atual não confirmado')
  await page.evaluate(() => scrollTo(0, 0))
  await mkdir(evidence, { recursive: true })
  await page.screenshot({ path: new URL('mobile-320-text-200-viewport.png', evidence).pathname, fullPage: false })
  await page.screenshot({ path: new URL('mobile-320-text-200.png', evidence).pathname, fullPage: true })
  await writeFile(new URL('reflow.json', evidence), JSON.stringify(await page.evaluate(() => ({
    width: innerWidth, scrollWidth: document.documentElement.scrollWidth, fontSize: getComputedStyle(document.documentElement).fontSize,
    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
  })), null, 2))
  expect(mock.posts).toEqual([])
})
