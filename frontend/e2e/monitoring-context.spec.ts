import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import examples from '../../contracts/examples/aiot.valid.json' with { type: 'json' }
import { mockDashboardAccount } from './monitoring-api'

test.skip(process.env.VITE_AIOT_ENABLED !== 'true', 'Contexto nas três vistas requer AIoT v3')
const envA = '00000000-0000-4000-8000-000000000001'
const envB = '00000000-0000-4000-8000-000000000002'
const devA = '00000000-0000-4000-8000-000000000011'
const devB = '00000000-0000-4000-8000-000000000021'
const inactive = '00000000-0000-4000-8000-000000000022'
const unknown = '00000000-0000-4000-8000-000000000099'
const telemetry = examples.find((item) => item.name === 'telemetry_received')!.payload
const inventory = { equipment_id: telemetry.data.equipment.equipment_id,
  sensors: Object.fromEntries(Object.entries(telemetry.data.measurements).map(([key, value]) => [key, value.sensor_id])),
  actuators: { led: telemetry.data.actuators.led.actuator_id, buzzer: telemetry.data.actuators.buzzer.actuator_id } }
const thresholds = { min_c: 2, max_c: 8, attention_margin_c: 1 }
const rules = { health_critical: 20, health_recovery: 40, rul_critical_hours: 10, rul_recovery_hours: 30, open_count: 2, close_count: 2 }
const pair = (env: string, dev: string) => `environment=${env}&device=${dev}`
const evidence = new URL('../../.impeccable/review/rd-04/', import.meta.url)
const localNav = (page: Page) => page.getByRole('navigation', { name: 'Navegação da área', exact: true })
const environment = (page: Page) => page.getByRole('combobox', { name: 'Ambiente', exact: true })
const device = (page: Page) => page.getByRole('combobox', { name: 'Dispositivo', exact: true })

async function mockContext(page: Page, preference?: { environmentId: string; deviceUuid: string }) {
  await mockDashboardAccount(page)
  if (preference) await page.addInitScript((selection) => {
    if (sessionStorage.getItem('context-test-initialized')) return
    const stored = JSON.parse(sessionStorage.getItem('coldsafe-session')!)
    sessionStorage.setItem('coldsafe-session', JSON.stringify({ ...stored, monitoring_selection: selection }))
    sessionStorage.setItem('context-test-initialized', 'true')
  }, preference)
  const requests: string[] = [], periods: string[] = []
  let activeB = true
  await page.route('**/api/v1/environments', (route) => route.fulfill({ json: { success: true, data: [
    { id: envA, name: 'Câmara A' }, { id: envB, name: 'Câmara B' },
  ] } }))
  await page.route('**/api/v1/environments/*/devices', (route) => {
    const second = route.request().url().includes(envB)
    return route.fulfill({ json: { success: true, data: [
      { id: second ? devB : devA, environment_id: second ? envB : envA, name: second ? 'Motor B' : 'Motor A',
        mqtt_device_id: second ? 'motor-b' : 'motor-a', is_active: second ? activeB : true },
      ...(second ? [{ id: inactive, environment_id: envB, name: 'Motor desativado', mqtt_device_id: 'motor-inactive', is_active: false }] : []),
    ] } })
  })
  await page.route('**/api/v3/**', (route) => {
    const url = new URL(route.request().url())
    requests.push(url.pathname + url.search)
    const mqtt = url.searchParams.get('device_id') ?? 'motor-a', second = mqtt === 'motor-b'
    if (url.pathname.endsWith('/summary')) return route.fulfill({ json: { success: true, data: {
      environment: { id: second ? envB : envA, name: second ? 'Câmara B' : 'Câmara A' }, device: { id: mqtt }, inventory, thresholds,
      telemetry: null, prediction: null, persistence: null, prediction_unavailable_reason: null, commands: { led: null, buzzer: null }, alerts: [],
      freshness: { state: 'no_data', age_seconds: null, last_event_id: null, last_received_at: null, stale_after_seconds: 30 },
    }, meta: { schema_version: 3 } } })
    if (url.pathname.endsWith('/insights')) return route.fulfill({ json: { success: true, data: {
      device_id: mqtt, equipment_id: inventory.equipment_id, rules, prediction: null, availability: 'no_data', age_seconds: null, trend: 'unknown', active_alerts: [],
    }, meta: { schema_version: 3 } } })
    if (url.pathname.endsWith('/readings')) {
      periods.push(`${mqtt}:${url.searchParams.get('period')}`)
      return route.fulfill({ json: { success: true, data: [], meta: { schema_version: 3, device_id: mqtt,
        start: '2026-10-12T17:00:00Z', end: '2026-10-12T18:01:00Z', count: 0, limit: 300, thresholds } } })
    }
    return route.fulfill({ status: 503, json: { success: false, error: { message: 'Consulta não prevista no ensaio.' } } })
  })
  await page.routeWebSocket('**/api/v3/events?**', (socket) => socket.onMessage(() => {}))
  return { requests, periods, deactivateB: () => { activeB = false } }
}

test('URL prevalece, par segue entre três vistas, recarga e histórico; período e peça são locais', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const mock = await mockContext(page, { environmentId: envA, deviceUuid: devA })
  await page.goto(`/dashboard?${pair(envB, devB)}`)
  await expect(environment(page)).toHaveValue(envB)
  await expect(device(page)).toHaveValue(devB)
  await mkdir(evidence, { recursive: true })
  await page.screenshot({ path: new URL('desktop.png', evidence).pathname, fullPage: false })
  await expect(localNav(page).getByRole('link', { name: 'Gêmeo digital', exact: true })).toHaveAttribute('href', `/digital-twin?${pair(envB, devB)}`)
  await page.getByRole('button', { name: '24h', exact: true }).click()
  await localNav(page).getByRole('link', { name: 'Saúde e previsões', exact: true }).click()
  await expect(page).toHaveURL(`/insights?${pair(envB, devB)}`)
  await expect(device(page)).toHaveValue(devB)
  await localNav(page).getByRole('link', { name: 'Gêmeo digital', exact: true }).click()
  await expect(page).toHaveURL(`/digital-twin?${pair(envB, devB)}`)
  await expect(device(page)).toHaveValue(devB)
  await page.getByRole('region', { name: 'Componentes do gêmeo digital', exact: true }).getByRole('button', { name: /^Temperatura ambiente/ }).click()
  await expect(page.getByRole('region', { name: 'Detalhes do componente', exact: true })).toBeVisible()
  await expect.poll(() => mock.periods).toContain('motor-b:15m')
  await environment(page).selectOption(envA)
  await expect(page).toHaveURL(`/digital-twin?${pair(envA, devA)}`)
  await expect(page.getByRole('region', { name: 'Detalhes do componente', exact: true })).toHaveCount(0)
  await page.goBack()
  await expect(device(page)).toHaveValue(devB)
  await page.goForward()
  await expect(device(page)).toHaveValue(devA)
  await page.reload()
  await expect(device(page)).toHaveValue(devA)
  await localNav(page).getByRole('link', { name: 'Visão geral', exact: true }).click()
  await expect(device(page)).toHaveValue(devA)
  await expect(page.getByRole('button', { name: '24h', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(() => mock.periods).toContain('motor-a:24h')
  expect(mock.requests.some((request) => request.includes('/insights?device_id=motor-b'))).toBe(true)
})

for (const [description, query] of [
  ['parcial', `environment=${envB}`], ['malformado', 'environment=not-a-uuid&device=not-a-uuid'],
  ['duplicado', `${pair(envB, devB)}&device=${devA}`], ['incompatível', pair(envA, devB)],
  ['inativo', pair(envB, inactive)], ['inacessível', pair(unknown, unknown)],
]) test(`par ${description} exige escolha sem consultar dados de outro equipamento`, async ({ page }) => {
  const mock = await mockContext(page, { environmentId: envA, deviceUuid: devA })
  await page.goto(`/dashboard?${query}`)
  await expect(page.locator('.selection-panel [role="status"]')).toContainText(/selecione|escolha/i)
  await expect(device(page)).toHaveValue('')
  await expect(page).toHaveURL(`/dashboard?${query}`)
  expect(mock.requests).toEqual([])
  await environment(page).selectOption(envB)
  await device(page).selectOption(devB)
  await expect(page).toHaveURL(`/dashboard?${pair(envB, devB)}`)
  await expect.poll(() => mock.requests.some((request) => request.includes('device_id=motor-b'))).toBe(true)
})

for (const path of ['/insights', '/digital-twin']) test(`${path}: URL inválida oferece seleção sem consultar medições ou previsão`, async ({ page }) => {
  const mock = await mockContext(page)
  await page.goto(`${path}?environment=not-a-uuid`)
  await expect(page.getByRole('status').filter({ hasText: /Selecione um ambiente e um dispositivo/ })).toBeVisible()
  await expect(device(page)).toHaveValue('')
  expect(mock.requests).toEqual([])
  await environment(page).selectOption(envB)
  await expect(device(page)).toHaveValue(devB)
  await expect(page).toHaveURL(`${path}?${pair(envB, devB)}`)
})

test('preferência da aba é revalidada; inativação pede escolha e gestão não herda query', async ({ page }) => {
  const mock = await mockContext(page, { environmentId: envB, deviceUuid: devB })
  await page.goto('/insights')
  await expect(device(page)).toHaveValue(devB)
  await expect(page).toHaveURL(`/insights?${pair(envB, devB)}`)
  await page.getByRole('link', { name: 'Ambientes e dispositivos', exact: true }).click()
  await expect(page).toHaveURL('/manage')
  mock.deactivateB()
  await page.getByRole('link', { name: 'Monitoramento', exact: true }).click()
  await expect(device(page)).toHaveValue('')
  const selection = page.getByRole('region', { name: 'Selecionar ambiente e dispositivo', exact: true })
  await expect(selection.getByRole('status').filter({ hasText: /selecione|escolha/i })).toBeVisible()
  await expect(selection.getByRole('status').filter({ hasText: 'Nenhum dispositivo ativo neste ambiente.' })).toBeVisible()
  await expect(page.getByText('Câmara A / motor-a', { exact: true })).toHaveCount(0)
})

test('320 px, texto 200%: escolha e links sem overflow, polling sem histórico nem roubo de foco', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockContext(page)
  await page.goto('/dashboard')
  await expect(device(page)).toHaveValue(devA)
  await mkdir(evidence, { recursive: true })
  await page.screenshot({ path: new URL('mobile-320.png', evidence).pathname, fullPage: false })
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  await environment(page).selectOption(envB)
  await expect(device(page)).toHaveValue(devB)
  await device(page).focus()
  const historyLength = await page.evaluate(() => history.length)
  await page.waitForTimeout(5200)
  await expect(device(page)).toBeFocused()
  expect(await page.evaluate(() => history.length)).toBe(historyLength)
  await mkdir(evidence, { recursive: true })
  await page.screenshot({ path: new URL('mobile-320-200.png', evidence).pathname, fullPage: false })
  const layout = await page.evaluate(() => ({ width: window.innerWidth, scrollWidth: document.documentElement.scrollWidth,
    overflow: Array.from(document.querySelectorAll('body *')).map((node) => ({ tag: node.tagName, class: node.className,
      right: node.getBoundingClientRect().right, width: node.getBoundingClientRect().width })).filter((node) => node.right > window.innerWidth + 1) }))
  await writeFile(new URL('mobile-layout.json', evidence), JSON.stringify(layout, null, 2))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width)
  await localNav(page).getByRole('link', { name: 'Saúde e previsões', exact: true }).click()
  await expect(device(page)).toHaveValue(devB)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

for (const status of [403, 404]) test(`Insights ${status} persistente limpa URL e preferência sem repetir após revalidar identidade; outra escolha recupera`, async ({ page }) => {
  const mock = await mockContext(page)
  let identities = 0, deniedRequests = 0
  await page.route('**/api/v1/auth/me', (route) => {
    identities += 1
    return route.fulfill({ json: { success: true, data: { user_id: 'test-user', email: 'test@example.com', role: 'operator' } } })
  })
  await page.route('**/api/v3/insights?**', (route) => {
    if (new URL(route.request().url()).searchParams.get('device_id') !== 'motor-a') return route.fallback()
    deniedRequests += 1
    return route.fulfill({ status, json: { success: false, error: { message: 'Acesso indisponível.' } } })
  })
  await page.goto(`/insights?${pair(envA, devA)}`)
  await expect(page).toHaveURL(`/insights?environment=${envA}`)
  await expect(device(page)).toHaveValue('')
  await expect(page.getByRole('region', { name: 'Limites preditivos', exact: true })).toHaveCount(0)
  await expect.poll(() => identities).toBe(2)
  expect(deniedRequests).toBe(1)
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('coldsafe-session')!).monitoring_selection)).toBeNull()
  const afterRevocation = { identities, deniedRequests }
  await page.waitForTimeout(2300)
  expect({ identities, deniedRequests }).toEqual(afterRevocation)
  await expect(localNav(page).getByRole('link', { name: 'Gêmeo digital', exact: true })).toHaveAttribute('href', '/digital-twin')
  await environment(page).selectOption(envB)
  await expect(page).toHaveURL(`/insights?${pair(envB, devB)}`)
  await expect(device(page)).toHaveValue(devB)
  await expect(page.getByRole('region', { name: 'Limites preditivos', exact: true })).toBeVisible()
  await expect.poll(() => mock.requests.some((request) => request.includes('/insights?device_id=motor-b'))).toBe(true)
  expect(deniedRequests).toBe(1)
  expect(identities).toBe(2)
})
