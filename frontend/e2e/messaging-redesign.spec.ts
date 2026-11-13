import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'

const timestamp = '2026-10-31T12:00:00Z'
const eventId = '11111111-1111-4111-8111-111111111111'
const deadId = '11111111-1111-4111-8111-111111111112'
const environmentId = '22222222-2222-4222-8222-222222222222'
const sample = { event_id: eventId, type: 'telemetry.received', occurred_at: '2026-10-31T11:58:20Z', observed_at: '2026-10-31T11:58:30Z',
  device_record_id: '33333333-3333-4333-8333-333333333333', device_id: 'cold-lab-01', environment_id: environmentId,
  correlation_id: '44444444-4444-4444-8444-444444444444', source_queue: null as string | null, reason: null as string | null, error_code: null as string | null }
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
const evidence = new URL('../../.impeccable/review/rd-14/', import.meta.url)
const summary = (page: Page) => page.getByRole('region', { name: 'Estado das filas', exact: true })
const queueTable = (page: Page) => page.getByRole('region', { name: 'Métricas por fila', exact: true })
const observation = (page: Page) => page.getByRole('region', { name: 'Mensagens dos seus ambientes', exact: true })
const messageGroup = (page: Page) => observation(page).getByRole('group', { name: 'Últimas mensagens', exact: true })
const failuresGroup = (page: Page) => observation(page).getByRole('group', { name: 'Falhas nas mensagens', exact: true })

async function messaging(page: Page, role = 'admin') {
  await page.clock.install({ time: new Date(timestamp) })
  const state = { role, metricsStatus: 200, samplesStatus: 200, metricsGets: 0, samplesGets: 0, writes: [] as string[],
    metrics: { sampled_at: timestamp, queues: [
      { name: 'telemetry.api.q', messages: 41, messages_ready: 38, messages_unacknowledged: 3, consumers: 1, publish_rate: 12 as number | null, deliver_rate: 8 as number | null },
      { name: 'coldsafe.inference', messages: 4, messages_ready: 4, messages_unacknowledged: 0, consumers: 1, publish_rate: 2.2 as number | null, deliver_rate: 0 as number | null },
    ] },
    samples: { sampled_at: timestamp, connected: true, last_observed_at: sample.observed_at as string | null, stale: false,
      stale_after_seconds: 30, capacity_per_kind: 100, messages: [sample],
      dead_letters: [{ ...sample, event_id: deadId, source_queue: 'coldsafe.writer', reason: 'rejected', error_code: 'INVALID_SCHEMA' }] } }
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('coldsafe-session')) sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'rd14-admin', expires_at: '2099-01-01T00:00:00Z' }))
  })
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { success: false } }))
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: environmentId, email: 'admin@example.invalid', role: state.role } } }))
  await page.route('**/api/v3/messaging**', route => {
    if (route.request().method() !== 'GET') { state.writes.push(route.request().method()); return route.fulfill({ status: 405 }) }
    expect(route.request().headers().authorization).toBe('Bearer rd14-admin')
    const isSamples = new URL(route.request().url()).pathname.endsWith('/messages')
    if (isSamples) state.samplesGets++; else state.metricsGets++
    const status = isSamples ? state.samplesStatus : state.metricsStatus
    return route.fulfill({ status, json: status === 200 ? envelope(isSamples ? state.samples : state.metrics) : { success: false, error: { message: 'private broker diagnostic must not appear' } } })
  })
  return state
}

for (const scenario of [{ width: 1440, text: 100 }, { width: 390, text: 100 }, { width: 320, text: 200 }]) {
  test(`M-07 resumo global e metadados privados: ${scenario.width}px texto ${scenario.text}% (API simulada)`, async ({ page }) => {
    await page.setViewportSize({ width: scenario.width, height: 1024 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const state = await messaging(page)
    await page.goto(`/messaging?environment=${environmentId}&device=cold-lab-01`)
    if (scenario.text === 200) await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    await expect(summary(page).locator('dd')).toHaveText(['42', '3', '2', '14,2 /s'])
    await expect(page.locator('main select, main input, main button')).toHaveCount(1)
    await expect(page.getByRole('button', { name: 'Ocultar dados ao vivo', exact: true })).toBeVisible()
    await expect(summary(page)).toContainText('filas listadas')
    await expect(page.getByText('Serviços que consultam a fila periodicamente podem operar com zero assinaturas.', { exact: false })).toBeVisible()
    await expect(summary(page)).toContainText('Coleta das métricas')
    await expect(summary(page)).not.toContainText('Informação desatualizada')
    await expect(observation(page)).toContainText('Observador conectado')
    await expect(observation(page)).toContainText('Observação desatualizada')
    await expect(observation(page)).toContainText('100 eventos e 100 cópias')
    const queues = queueTable(page)
    await expect(queues.getByRole('columnheader')).toHaveText(['Fila', 'Total', 'Disponíveis', 'Entregues sem confirmação', 'Assinaturas ativas', 'Entrada', 'Entrega'])
    await expect(queues.getByRole('rowheader').first()).toHaveText('telemetry.api.q')
    await expect(queues.getByRole('rowheader').last()).toContainText('Análise de leituras e previsões')
    await expect(queues.getByRole('rowheader').last()).toContainText('coldsafe.inference')
    if (scenario.width === 1440) await expect(queues).not.toHaveAccessibleDescription(/use as setas/)
    else await expect(queues).toHaveAccessibleDescription(/use as setas/)
    const messages = messageGroup(page)
    const dead = failuresGroup(page)
    await messages.locator('summary').click()
    await dead.locator('summary').click()
    await expect(messages.getByText(eventId, { exact: true })).toBeVisible()
    await expect(dead.getByText(deadId, { exact: true })).toBeVisible()
    await expect(dead.getByRole('listitem')).toContainText('coldsafe.writer')
    await expect(dead).toContainText('rejected'); await expect(dead).toContainText('INVALID_SCHEMA')
    await mkdir(evidence, { recursive: true })
    const name = scenario.width === 1440 ? 'desktop' : scenario.width === 390 ? 'mobile' : 'mobile-320-text-200'
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: new URL(`${name}.png`, evidence).pathname })
    await queues.focus(); await expect(queues).toBeFocused(); await page.keyboard.press('ArrowRight')
    if (scenario.width < 1100) await expect.poll(() => queues.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
    await queues.evaluate(el => { el.scrollLeft = el.scrollWidth; el.scrollIntoView({ block: 'center' }) })
    await page.screenshot({ path: new URL(`${name}-queues-focus.png`, evidence).pathname })
    if (scenario.text === 100) await observation(page).screenshot({ path: new URL(`${name}-private.png`, evidence).pathname })
    else {
      await summary(page).locator('dl').screenshot({ path: new URL(`${name}-metrics.png`, evidence).pathname })
      await observation(page).locator('.observer-state').evaluate(el => el.scrollIntoView({ block: 'start' }))
      await page.screenshot({ path: new URL(`${name}-observer.png`, evidence).pathname })
      await dead.locator('summary').evaluate(el => el.scrollIntoView({ block: 'start' }))
      await page.screenshot({ path: new URL(`${name}-dlq.png`, evidence).pathname })
    }
    const layout = await page.evaluate(() => {
      const stale = getComputedStyle(document.querySelector('.observer-state')!), body = getComputedStyle(document.querySelector('.panel')!)
      const muted = getComputedStyle(document.querySelector('.hint')!)
      return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth, rootFont: getComputedStyle(document.documentElement).fontSize,
        body: { color: body.color, background: body.backgroundColor }, muted: { color: muted.color },
        stale: { color: stale.color, background: stale.backgroundColor },
        table: { width: document.querySelector('.table-scroll')!.clientWidth, scrollWidth: document.querySelector('.table-scroll')!.scrollWidth } }
    })
    expect(layout.scrollWidth).toBe(scenario.width)
    await writeFile(new URL(`${name}-layout.json`, evidence), JSON.stringify(layout, null, 2))
    expect(state.writes).toEqual([])
  })
}

test('UX-02: destaca as filas com mensagens disponíveis e mantém metadados e diagnóstico sob demanda', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  const state = await messaging(page)
  const queueNames = ['gateway', 'writer', 'inference', 'delivery', 'commands', 'generation',
    'training', 'observability', 'model-activation', 'dlq']
  state.metrics.queues = queueNames.map((name) => {
    const ready = name === 'writer' ? 32 : name === 'inference' ? 4 : 0
    const unacknowledged = name === 'writer' ? 3 : 0
    return { name: `coldsafe.${name}`, messages: ready + unacknowledged, messages_ready: ready,
      messages_unacknowledged: unacknowledged, consumers: 0, publish_rate: name === 'gateway' ? null : 0.2, deliver_rate: 0 }
  })
  await page.goto('/messaging')
  const status = page.getByRole('region', { name: 'Estado das filas', exact: true })
  const waiting = page.getByRole('region', { name: 'Filas com mais mensagens disponíveis', exact: true })
  await expect(status.locator('dd')).toHaveText(['36', '3', '0', 'Indisponível'])
  await expect(status).toContainText('1 fila sem taxa de entrada')
  await expect(waiting.getByRole('listitem')).toHaveCount(2)
  await expect(waiting.getByRole('listitem').first()).toContainText('Gravação de leituras')
  await expect(waiting.getByRole('listitem').first()).toContainText('32 disponíveis')

  const queues = page.getByRole('region', { name: 'Métricas por fila', exact: true })
  await expect(queues.getByRole('rowheader')).toHaveCount(10)
  await expect(queues.getByRole('rowheader').filter({ hasText: 'coldsafe.writer' })).toContainText('Gravação de leituras')
  expect(await queues.evaluate(el => el.scrollWidth)).toBe(await queues.evaluate(el => el.clientWidth))
  await expect(queues).not.toHaveAccessibleDescription(/use as setas/)
  await expect(page.getByText(eventId, { exact: true })).toBeHidden()
  await expect(page.getByText('Ensaio de parada do gravador', { exact: true })).toBeHidden()
  const output = new URL('../../.impeccable/review/ux-02/', import.meta.url)
  await mkdir(output, { recursive: true })
  await page.locator('#messaging-title').blur()
  await page.screenshot({ path: new URL('desktop-topo.png', output).pathname })
  await page.screenshot({ path: new URL('desktop.png', output).pathname, fullPage: true })

  await page.setViewportSize({ width: 800, height: 1024 })
  await expect(queues).toHaveAccessibleDescription(/use as setas/)
  await queues.focus()
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => queues.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
  await page.setViewportSize({ width: 1440, height: 1024 })
  await expect(queues).not.toHaveAccessibleDescription(/use as setas/)

  await messageGroup(page).locator('summary').press('Enter')
  await expect(page.getByText(eventId, { exact: true })).toBeVisible()
  await page.getByText('Diagnóstico técnico', { exact: true }).press('Enter')
  await expect(page.getByText('Ensaio de parada do gravador', { exact: true })).toBeVisible()
  expect(state.writes).toEqual([])
})

for (const failure of ['metrics', 'samples'] as const) {
  test(`falha parcial de ${failure} conserva outra seção e recupera por polling GET`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    const state = await messaging(page)
    const queueName = 'coldsafe.observacao.mensagens.refrigeracao.laboratorio.engenharia.instrumentacao.entrada.telemetria.camara.principal'
    state.metrics.queues[0]!.name = queueName
    await page.goto('/messaging')
    await expect(summary(page).locator('dd')).toHaveText(['42', '3', '2', '14,2 /s'])
    const readyHeader = queueTable(page).getByRole('columnheader', { name: 'Disponíveis', exact: true })
    expect(await readyHeader.evaluate(element => {
      const text = document.createRange()
      text.selectNodeContents(element)
      return text.getClientRects().length
    })).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1280)
    await messageGroup(page).locator('summary').click()
    await expect(page.getByText(eventId, { exact: true })).toBeVisible()
    await queueTable(page).focus()
    if (failure === 'metrics') state.metricsStatus = 503; else state.samplesStatus = 503
    await page.clock.fastForward(5000)
    await expect(page.getByRole('alert')).toContainText(failure === 'metrics' ? 'Não foi possível atualizar as filas' : 'Não foi possível atualizar as mensagens')
    await expect(page.getByRole('alert')).toContainText('Última consulta bem-sucedida')
    await expect(queueTable(page)).toContainText(queueName)
    await expect(page.getByText(eventId, { exact: true })).toBeVisible()
    await expect(page.locator('main')).not.toContainText('private broker diagnostic')
    state.metricsStatus = 200; state.samplesStatus = 200
    await page.clock.fastForward(5000)
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(queueTable(page)).toBeFocused()
    expect(state.metricsGets).toBeGreaterThanOrEqual(3); expect(state.samplesGets).toBeGreaterThanOrEqual(3)
    expect(state.writes).toEqual([])
  })
}

test('taxa desconhecida, baixa, zero e ausência de filas permanecem distintas ao atualizar', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1024 })
  const state = await messaging(page); state.metrics.queues[0]!.publish_rate = null
  await page.goto('/messaging')
  await expect(summary(page).locator('dd')).toHaveText(['42', '3', '2', 'Indisponível'])
  await expect(queueTable(page).getByRole('row').last()).toContainText('2,2 /s')
  await mkdir(evidence, { recursive: true })
  await summary(page).locator('dl').screenshot({ path: new URL('mobile-unknown-rate.png', evidence).pathname })
  state.metrics.queues = [{ name: 'zero.q', messages: 0, messages_ready: 0, messages_unacknowledged: 0, consumers: 0, publish_rate: 0, deliver_rate: 0 }]
  await page.clock.fastForward(5000)
  await expect(summary(page).locator('dd')).toHaveText(['0', '0', '0', '0 /s'])
  state.metrics.queues[0]!.publish_rate = 0.001
  await page.clock.fastForward(5000)
  await expect(summary(page).locator('dd').last()).toHaveText('< 0,01 /s')
  await expect(queueTable(page).getByRole('cell').nth(4)).toHaveText('< 0,01 /s')
  await expect(queueTable(page).getByRole('cell').nth(5)).toHaveText('0 /s')
  state.metrics.queues = []
  await page.clock.fastForward(5000)
  await expect(summary(page).locator('dd')).toHaveText(Array(4).fill('Indisponível'))
  await expect(page.getByText('Nenhuma fila disponível nesta amostra.', { exact: true })).toBeVisible()
  expect(state.writes).toEqual([])
})

for (const role of ['viewer', 'operator']) {
  test(`${role} não consulta endpoints privados nem vê métricas globais`, async ({ page }) => {
    const state = await messaging(page, role)
    await page.goto('/messaging')
    await expect(page.getByRole('heading', { name: 'Acesso restrito', exact: true })).toBeVisible()
    await expect(summary(page)).toHaveCount(0); await expect(page.locator('main table')).toHaveCount(0)
    expect(state.metricsGets).toBe(0); expect(state.samplesGets).toBe(0); expect(state.writes).toEqual([])
  })
}

for (const status of [401, 403]) {
  test(`revogação ${status} no polling limpa métricas e amostras privadas`, async ({ page }) => {
    const state = await messaging(page)
    await page.goto('/messaging')
    await messageGroup(page).locator('summary').click()
    await expect(page.getByText(eventId, { exact: true })).toBeVisible()
    state.samplesStatus = status
    if (status === 403) state.role = 'viewer'
    await page.clock.fastForward(5000)
    if (status === 401) await expect(page).toHaveURL(/\/login/)
    else await expect(page.getByRole('heading', { name: 'Acesso restrito', exact: true })).toBeVisible()
    await expect(summary(page)).toHaveCount(0)
    await expect(page.getByText(eventId, { exact: true })).toHaveCount(0)
    await expect(page.getByText(deadId, { exact: true })).toHaveCount(0)
    expect(state.writes).toEqual([])
  })
}

test('amostras vazias preservam observador desconectado e os limites de 100 por categoria', async ({ page }) => {
  const state = await messaging(page)
  state.samples.messages = []; state.samples.dead_letters = []; state.samples.connected = false; state.samples.last_observed_at = null
  await page.goto('/messaging')
  await expect(observation(page)).toContainText('Observador desconectado')
  await expect(observation(page)).toContainText('Nenhuma mensagem observada')
  await expect(observation(page)).toContainText('Nenhuma falha observada')
  await expect(observation(page)).toContainText('100 eventos e 100 cópias')
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(state.writes).toEqual([])
})
