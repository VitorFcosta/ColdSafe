import { readFileSync, writeFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const api = process.env.INFERENCE_REAL_API_URL ?? ''
test.skip(!process.env.INFERENCE_REAL_URL || !api || !process.env.INFERENCE_REAL_PASSWORD,
  'Run through the disposable B2-25 inference integration harness')

test('previsão real chega pelo barramento e troca versão na mesma página e worker', async ({ page, request }) => {
  const models: string[] = JSON.parse(process.env.INFERENCE_REAL_MODELS!)
  const password = process.env.INFERENCE_REAL_PASSWORD
  const control = async (value: 'pause' | 'stream') => {
    writeFileSync(process.env.INFERENCE_REAL_CONTROL!, value)
    await expect.poll(() => readFileSync(process.env.INFERENCE_REAL_CONTROL! + '.ack', 'utf8')).toBe(value)
  }
  const login = async (email: string) => {
    const response = await request.post(`${api}/api/v1/auth/login`, { data: { email, password } })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const session = await login(process.env.INFERENCE_REAL_EMAIL!)
  const headers = { authorization: `Bearer ${session.token}` }
  await page.addInitScript((value) => sessionStorage.setItem('coldsafe-session', JSON.stringify(value)), session)
  let navigations = 0
  const predictions: { event_id: string; model_version: string | null; source_event_id: string }[] = []
  page.on('request', (call) => { if (call.resourceType() === 'document') navigations++ })
  page.on('websocket', (socket) => socket.on('framereceived', (frame) => {
    const event = JSON.parse(String(frame.payload))
    if (event.type === 'prediction') predictions.push({ event_id: event.event_id,
      model_version: event.data.model_version, source_event_id: event.data.source_event_id })
  }))
  await page.goto('/dashboard')
  const panel = page.getByRole('region', { name: 'Previsão do equipamento', exact: true })
  await expect(panel).toBeVisible()
  const marker = await page.evaluate(() => {
    const value = crypto.randomUUID()
    Object.assign(window, { inferenceAcceptanceMarker: value })
    return value
  })
  await control('stream')
  await expect(panel.getByRole('status')).toContainText('Nenhum modelo ativo.')
  await page.screenshot({ path: test.info().outputPath('inference-no-model.png'), fullPage: true })

  const activate = async (model: string, expected: 'active' | 'failed') => {
    const response = await request.post(`${api}/api/v3/model-activations`, { headers, data: { model_id: model } })
    expect(response.status()).toBe(202)
    const activation = (await response.json()).data
    let state = activation
    await expect.poll(async () => {
      const result = await request.get(`${api}/api/v3/model-activations/${activation.id}`, { headers })
      expect(result.status()).toBe(200)
      state = (await result.json()).data
      return state.status
    }, { timeout: 30_000, intervals: [100] }).toBe(expected)
    return state
  }
  const snapshot = async () => {
    const response = await request.get(`${api}/api/v3/monitoring/summary`, {
      headers, params: { device_id: process.env.INFERENCE_REAL_DEVICE! },
    })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const versions = []
  for (const [index, model] of models.slice(0, 2).entries()) {
    const activation = await activate(model, 'active')
    await control('stream')
    await expect(panel.getByRole('status')).toHaveText('Previsão disponível para a última leitura.')
    await expect(panel.getByText(activation.model_version, { exact: true })).toBeVisible()
    await expect(panel.getByRole('status')).toHaveText('Previsão disponível para a última leitura.')
    await control('pause')
    // Let the final source/receipt/inference drain before comparing stable REST values to the UI.
    await expect.poll(async () => {
      const current = await snapshot()
      return current.prediction?.data.model_id === model && current.prediction?.data.status === 'available'
    }, { intervals: [250] }).toBe(true)
    const current = await snapshot()
    const prediction = current.prediction
    expect(prediction.data.source_event_id).toBe(current.telemetry.event_id)
    expect(prediction.data.input_received_at).toBe(current.telemetry.received_at)
    expect(Number.isFinite(prediction.data.health_score)).toBe(true)
    expect(prediction.data.health_score).toBeGreaterThanOrEqual(0)
    expect(prediction.data.health_score).toBeLessThanOrEqual(100)
    expect(prediction.data.rul_hours).toBeGreaterThanOrEqual(0)
    const formatted = (value: number) => value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })
    await expect(panel.getByText(`${formatted(prediction.data.health_score)} / 100`, { exact: true })).toBeVisible()
    await expect(panel.getByText(`${formatted(prediction.data.rul_hours)} h`, { exact: true })).toBeVisible()
    await expect(panel.locator('time').first()).toHaveAttribute('datetime', prediction.data.input_received_at)
    await expect.poll(() => predictions.some((event) => event.event_id === prediction.event_id)).toBe(true)
    versions.push({ activation, prediction, telemetry_event_id: current.telemetry.event_id })
    await page.screenshot({ path: test.info().outputPath(`inference-version-${index + 1}.png`), fullPage: true })
  }
  expect(versions[0]!.prediction.data.model_version).not.toBe(versions[1]!.prediction.data.model_version)
  const failed = await activate(models[2]!, 'failed')
  expect(failed.error_code).toBe('MODEL_LOAD_FAILED')
  const active = await request.get(`${api}/api/v3/models/active`, { headers })
  expect((await active.json()).data.model_id).toBe(models[1])
  await expect(panel.getByText(versions[1]!.prediction.data.model_version, { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 320, height: 844 })
  const mobileBefore = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
    overflow: [...document.querySelectorAll('body *')].flatMap((element) => {
      const box = element.getBoundingClientRect()
      return box.right > innerWidth + 1 ? [{ tag: element.tagName, className: element.className,
        right: box.right, text: element.textContent?.slice(0, 70) }] : []
    }),
  }))
  console.log('Mobile resize before chart/layout settle:', JSON.stringify(mobileBefore))
  await page.screenshot({ path: test.info().outputPath('inference-mobile.png'), fullPage: true })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('inference-mobile.png'), fullPage: true })
  expect(await page.evaluate(() => Reflect.get(window, 'inferenceAcceptanceMarker'))).toBe(marker)
  expect(navigations).toBe(1)

  const stranger = await login(process.env.INFERENCE_REAL_OTHER_EMAIL!)
  const otherHeaders = { authorization: `Bearer ${stranger.token}` }
  expect((await request.get(`${api}/api/v3/monitoring/summary`, {
    headers: otherHeaders, params: { device_id: process.env.INFERENCE_REAL_DEVICE! },
  })).status()).toBe(404)
  expect((await request.get(`${api}/api/v3/model-activations/${failed.id}`, { headers: otherHeaders })).status()).toBe(404)
  expect((await request.post(`${api}/api/v1/auth/logout`, { headers })).status()).toBe(200)
  expect((await request.get(`${api}/api/v3/models/active`, { headers })).status()).toBe(401)
  writeFileSync(process.env.INFERENCE_REAL_EVIDENCE!, JSON.stringify({ versions, failed_activation: failed,
    no_model_visible: true, browser_not_reloaded: true, navigations, websocket_predictions: predictions,
    private_owner_denied: true, revoked_session_denied: true, mobile_320_without_overflow: true,
    mobile_before_layout_settle: mobileBefore }, null, 2))
})
