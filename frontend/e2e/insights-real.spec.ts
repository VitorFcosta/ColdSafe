import { readFileSync, renameSync, writeFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const api = process.env.INSIGHTS_REAL_API_URL ?? ''
test.skip(!process.env.INSIGHTS_REAL_URL || !api || !process.env.INSIGHTS_REAL_PASSWORD,
  'Run through the disposable B2-26 insights integration harness')

test('histerese persistente resiste à oscilação, ausência, redelivery e recarga', async ({ page, request }) => {
  page.on('pageerror', (error) => console.log('Browser error:', error.message))
  page.on('response', async (response) => {
    if (!response.url().startsWith(`${api}/api/v3/insights`) || response.request().method() !== 'GET') return
    const payload = await response.json().catch(() => null)
    console.log('Insights browser poll:', response.status(), payload?.data?.availability, payload?.data?.active_alerts?.length)
  })
  const login = async (email: string) => {
    const response = await request.post(`${api}/api/v1/auth/login`, {
      data: { email, password: process.env.INSIGHTS_REAL_PASSWORD },
    })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const session = await login(process.env.INSIGHTS_REAL_EMAIL!)
  const headers = { authorization: `Bearer ${session.token}` }
  const params = { device_id: process.env.INSIGHTS_REAL_DEVICE! }
  const snapshot = async () => {
    const response = await request.get(`${api}/api/v3/insights`, { headers, params })
    expect(response.status()).toBe(200)
    const payload = await response.json()
    expect(payload.meta.schema_version).toBe(3)
    return payload.data
  }
  let sequence = 0
  const sample = async (health: number | null, rul: number | null, duplicate = false) => {
    const control = process.env.INSIGHTS_REAL_CONTROL!
    const id = ++sequence
    writeFileSync(control + '.next', JSON.stringify({ id, health, rul, duplicate }))
    renameSync(control + '.next', control)
    await expect.poll(() => JSON.parse(readFileSync(control + '.ack', 'utf8')).id).toBe(id)
    const receipt = JSON.parse(readFileSync(control + '.ack', 'utf8'))
    const current = await snapshot()
    expect(current.prediction.event_id).toBe(receipt.prediction_event_id)
    expect(current.prediction.data.source_event_id).toBe(receipt.source_event_id)
    expect(current.active_alerts.map((alert: { alert_id: string }) => alert.alert_id))
      .toEqual(receipt.recreated_active_alert_ids)
    return current
  }
  await page.addInitScript((value) => sessionStorage.setItem('coldsafe-session', JSON.stringify(value)), session)
  await page.goto('/insights')
  const panel = page.getByRole('region', { name: 'Insights do equipamento', exact: true })
  const alerts = page.getByRole('region', { name: 'Alertas preditivos ativos', exact: true })
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('Sem previsão')
  expect((await snapshot()).availability).toBe('no_data')

  const rules = { health_critical: 32, health_recovery: 42, rul_critical_hours: 22,
    rul_recovery_hours: 44, open_count: 3, close_count: 10 }
  const form = page.getByRole('form', { name: 'Regras preditivas' })
  await form.getByLabel('Saúde crítica', { exact: true }).fill(String(rules.health_critical))
  await form.getByLabel('Saúde de recuperação', { exact: true }).fill(String(rules.health_recovery))
  await form.getByLabel('RUL crítico (h)', { exact: true }).fill(String(rules.rul_critical_hours))
  await form.getByLabel('RUL de recuperação (h)', { exact: true }).fill(String(rules.rul_recovery_hours))
  await form.getByRole('button', { name: 'Salvar regras' }).click()
  await expect.poll(async () => (await snapshot()).rules).toEqual(rules)
  for (const [health, rul] of [[70, 120], [45, 70], [31, 21], [30, 20], [35, 30], [29, 20], [28, 18]]) {
    expect((await sample(health!, rul!)).active_alerts).toEqual([])
  }
  const opened = await sample(27, 16)
  expect(opened.active_alerts).toHaveLength(1)
  expect(opened.trend).toBe('declining')
  const parsed = await page.evaluate(async ({ value, device, modulePath }) =>
    (await import(modulePath)).parseInsights(value, device), { value: opened,
    device: { id: opened.prediction.device_record_id, environment_id: opened.prediction.environment_id,
      mqtt_device_id: opened.device_id }, modulePath: '/src/features/insights/insights-api.ts' })
  expect(parsed).not.toBeNull()
  const alertId = opened.active_alerts[0].alert_id
  await expect(alerts).toContainText('Alerta preditivo persistente')
  await expect(panel).toContainText('demo-v1')
  await expect(panel.getByText('27 / 100', { exact: true })).toBeVisible()
  await expect(panel.getByText('16 h', { exact: true })).toBeVisible()
  await expect(panel.getByText('Em queda', { exact: true })).toBeVisible()
  await expect(panel.getByText(/^há \d+ s \(desde a entrada\)$/)).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('insights-open.png'), fullPage: true })
  expect((await sample(27, 16, true)).active_alerts[0].alert_id).toBe(alertId)
  for (const [health, rul] of [[31, 21], [35, 30], [43, 50], [38, 35]]) {
    expect((await sample(health!, rul!)).active_alerts[0].alert_id).toBe(alertId)
  }
  const unavailable = await sample(null, null)
  expect(unavailable.availability).toBe('unavailable')
  expect(unavailable.active_alerts[0].alert_id).toBe(alertId)
  await expect(panel).toContainText('Previsão indisponível')
  await expect(alerts).toContainText('Alerta preditivo persistente')

  await sample(25, 15)
  await expect.poll(async () => (await snapshot()).availability, {
    timeout: 40_000, intervals: [500],
  }).toBe('stale')
  await expect(panel).toContainText('Previsão desatualizada')
  await expect(alerts).toContainText('Alerta preditivo persistente')
  expect((await snapshot()).active_alerts[0].alert_id).toBe(alertId)
  await page.reload()
  await expect(panel).toContainText('Previsão desatualizada')
  await expect(alerts).toContainText('Alerta preditivo persistente')
  expect((await snapshot()).rules).toEqual(rules)
  await page.screenshot({ path: test.info().outputPath('insights-stale-active.png'), fullPage: true })
  for (let index = 0; index < 9; index++) {
    expect((await sample(80 + index, 100 + index)).active_alerts[0].alert_id).toBe(alertId)
  }
  const recovered = await sample(90, 110)
  expect(recovered.active_alerts).toEqual([])
  expect(recovered.trend).toBe('improving')
  await expect(alerts).toContainText('Nenhum alerta preditivo ativo')
  await page.setViewportSize({ width: 320, height: 844 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('insights-recovered-mobile.png'), fullPage: true })

  const stranger = await login(process.env.INSIGHTS_REAL_OTHER_EMAIL!)
  const otherHeaders = { authorization: `Bearer ${stranger.token}` }
  expect((await request.get(`${api}/api/v3/insights`, { headers: otherHeaders, params })).status()).toBe(404)
  expect((await request.put(`${api}/api/v3/insights/rules`, {
    headers: otherHeaders, params, data: rules,
  })).status()).toBe(404)
  const otherContext = await page.context().browser()!.newContext()
  try {
    await otherContext.addInitScript((value) => sessionStorage.setItem('coldsafe-session', JSON.stringify(value)), stranger)
    const otherPage = await otherContext.newPage()
    await otherPage.goto(`${process.env.INSIGHTS_REAL_URL}/insights`)
    await expect(otherPage.getByText('Nenhum equipamento ativo neste ambiente.')).toBeVisible()
    await expect(otherPage.getByRole('region', { name: 'Insights do equipamento', exact: true })).toHaveCount(0)
  } finally {
    await otherContext.close()
  }
  expect((await snapshot()).rules).toEqual(rules)
  writeFileSync(process.env.INSIGHTS_REAL_EVIDENCE!, JSON.stringify({ opened, recovered,
    unavailable, rules, active_alert_id: alertId, duplicate_republished: true,
    neutral_resets_open_sequence: true, recovery_requires_ten_consecutive: true,
    oscillation_no_flicker: true, no_prediction_not_recovery: true,
    real_telemetry_interruption_stale: true, reload_preserves_alert_and_rules: true,
    private_owner_denied: true, mobile_320_without_overflow: true }, null, 2))
})
