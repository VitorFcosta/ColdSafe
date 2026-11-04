import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import fixture from '../src/features/training/training.fixture.json' with { type: 'json' }
import { mockDashboardAccount } from './monitoring-api'

const envA = '00000000-0000-4000-8000-000000000001'
const envB = '00000000-0000-4000-8000-000000000002'
const devA = '00000000-0000-4000-8000-000000000011'
const devB = '00000000-0000-4000-8000-000000000021'
const datasetId = fixture.dataset_id
const otherDatasetId = '00000000-0000-4000-8000-000000000099'
const rules = { health_critical: 20, health_recovery: 40, rul_critical_hours: 10, rul_recovery_hours: 30, open_count: 2, close_count: 2 }
const config = { job_type: 'generation', total_units: 1000000, seed: 42, environment_id: null, equipment_count: 100, days: 30,
  sensor_types: ['ambient_temperature_c', 'humidity_percent', 'light_percent', 'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c'],
  failure_fraction: .6, failure_modes: ['bearing_wear', 'imbalance'], operating_modes: ['normal', 'heavy', 'cycling'], noise_scale: 1, missing_rate: .01, outlier_rate: .002 }
const timestamp = '2026-10-17T12:00:00Z'
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
const dialog = (page: Page) => page.getByRole('dialog', { name: 'Descartar alterações?', exact: true })
const localNav = (page: Page) => page.getByRole('navigation', { name: 'Navegação da área', exact: true })
const globalNav = (page: Page) => page.getByRole('navigation', { name: 'Navegação principal', exact: true })
const environment = (page: Page) => page.getByRole('combobox', { name: 'Ambiente', exact: true })
const openingCount = (page: Page) => page.getByRole('spinbutton', { name: 'Previsões para abrir', exact: true })
const path = (name: string) => new URL(`../../.impeccable/review/rd-05/${name}`, import.meta.url)

async function mockDraftApi(page: Page) {
  await page.route('**/api/**', (route) => route.fulfill({ status: 503, json: { success: false, error: { message: 'Serviço de ensaio indisponível.' } } }))
  await mockDashboardAccount(page)
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { success: true, data: { user_id: fixture.job_id, email: 'admin@example.invalid', role: 'admin' } } }))
  await page.route('**/api/v1/environments', (route) => route.fulfill({ json: { success: true, data: [{ id: envA, name: 'Câmara A' }, { id: envB, name: 'Câmara B' }] } }))
  await page.route('**/api/v1/environments/*/devices', (route) => {
    const second = route.request().url().includes(envB)
    return route.fulfill({ json: { success: true, data: [{ id: second ? devB : devA, environment_id: second ? envB : envA,
      name: second ? 'Motor B' : 'Motor A', mqtt_device_id: second ? 'motor-b' : 'motor-a', is_active: true }] } })
  })
  const state = { insightStatus: 200, failSave: false, insightGets: 0, rulePuts: 0, generationPosts: 0, trainingPosts: 0, cancellationRequests: 0 }
  let currentRules = { ...rules }
  await page.route('**/api/v1/environments/*/rules', (route) => route.fulfill({ json: { success: true, data:
    route.request().method() === 'PUT' ? route.request().postDataJSON() : { min_c: 2, max_c: 8, attention_margin_c: 1 } } }))
  await page.route('**/api/v3/**', (route) => {
    const url = new URL(route.request().url()), method = route.request().method()
    if (url.pathname === '/api/v3/insights') {
      state.insightGets++
      if (state.insightStatus !== 200) return route.fulfill({ status: state.insightStatus, json: { success: false, error: { message: 'Acesso indisponível.' } } })
      return route.fulfill({ json: envelope({ device_id: url.searchParams.get('device_id'), equipment_id: fixture.model_id,
        rules: currentRules, prediction: null, availability: 'no_data', age_seconds: null, trend: 'unknown', active_alerts: [] }) })
    }
    if (url.pathname === '/api/v3/insights/rules') {
      state.rulePuts++
      if (state.failSave) return route.fulfill({ status: 503, json: { success: false } })
      currentRules = route.request().postDataJSON()
      return route.fulfill({ json: envelope(currentRules) })
    }
    if (url.pathname === '/api/v3/datasets') return route.fulfill({ json: envelope([datasetId, otherDatasetId].map((id, index) => ({
      id, name: `Dataset ${index + 1}`, row_count: 1000000, generation_job_id: fixture.job_id, created_at: timestamp,
    }))) })
    if (url.pathname.startsWith('/api/v3/datasets/')) return route.fulfill({ json: envelope({
      id: url.pathname.split('/').at(-1), owner_user_id: fixture.job_id, generation_job_id: fixture.job_id, created_at: timestamp,
      row_count: 1000000, config, storage_version: 'offline-numpy-v1', units: Object.fromEntries(config.sensor_types.map((key) => [key, 'unit'])),
      quality: { missing_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, 10])),
        range_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, { min: 0, max: 100 }])), rul_observed_rows: 600000, rul_censored_rows: 400000 },
    }) })
    if (url.pathname === '/api/v3/jobs' && method === 'POST') {
      const requested = route.request().postDataJSON(), generation = requested.job_type === 'generation'
      if (generation) state.generationPosts++; else state.trainingPosts++
      return route.fulfill({ status: 202, json: envelope({ id: fixture.job_id, owner_user_id: fixture.job_id,
        job_type: requested.job_type, status: 'queued', completed_units: 0, total_units: generation ? 1000000 : 2,
        result_id: null, dataset_id: generation ? null : requested.dataset_id, environment_id: requested.environment_id,
        error_code: null, config: requested, created_at: timestamp, updated_at: timestamp }) })
    }
    if (url.pathname.startsWith('/api/v3/jobs/')) {
      if (method !== 'GET') state.cancellationRequests++
      const generation = page.url().includes('/laboratory')
      return route.fulfill({ json: envelope({ id: fixture.job_id, owner_user_id: fixture.job_id, job_type: generation ? 'generation' : 'training',
        status: 'running', completed_units: 1, total_units: generation ? 1000000 : 2, result_id: null,
        dataset_id: generation ? null : datasetId, environment_id: null, error_code: null,
        config: generation ? config : { job_type: 'training', dataset_id: datasetId, environment_id: null }, created_at: timestamp, updated_at: timestamp }) })
    }
    return route.fulfill({ status: 503, json: { success: false } })
  })
  return state
}

async function openInsights(page: Page) {
  await page.goto(`/insights?environment=${envA}&device=${devA}`)
  await expect(openingCount(page)).toHaveValue('2')
}

test('Insights: permanecer conserva edição, foco, URL e escopo; descartar troca uma vez', async ({ page }) => {
  const state = await mockDraftApi(page)
  await openInsights(page)
  await openingCount(page).fill('5')
  const originalUrl = page.url(), historyLength = await page.evaluate(() => history.length)
  await environment(page).focus()
  await environment(page).selectOption(envB)
  await expect(dialog(page)).toBeVisible()
  await expect(dialog(page).getByRole('button', { name: 'Permanecer', exact: true })).toBeFocused()
  await dialog(page).getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(page).toHaveURL(originalUrl)
  await expect(environment(page)).toHaveValue(envA)
  await expect(openingCount(page)).toHaveValue('5')
  await expect(environment(page)).toBeFocused()
  await page.waitForTimeout(2200)
  await expect(openingCount(page)).toHaveValue('5')
  expect(state.insightGets).toBeGreaterThan(1)
  await environment(page).selectOption(envB)
  await dialog(page).getByRole('button', { name: 'Descartar alterações', exact: true }).click()
  await expect(page).toHaveURL(`/insights?environment=${envB}&device=${devB}`)
  await expect(openingCount(page)).toHaveValue('2')
  expect(await page.evaluate(() => history.length)).toBe(historyLength + 1)
  expect(state.rulePuts).toBe(0)
})

test('Insights: voltar permanece na rota; Escape conserva o rascunho e descarte permite voltar', async ({ page }) => {
  await mockDraftApi(page)
  await page.goto('/manage')
  await globalNav(page).getByRole('link', { name: 'Monitoramento', exact: true }).click()
  await localNav(page).getByRole('link', { name: 'Saúde e previsões', exact: true }).click()
  await expect(openingCount(page)).toHaveValue('2')
  const current = page.url()
  await openingCount(page).fill('4')
  await page.evaluate(() => history.back())
  await expect(dialog(page)).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog(page)).not.toBeVisible()
  await expect(page).toHaveURL(current)
  await expect(openingCount(page)).toHaveValue('4')
  await page.evaluate(() => history.back())
  await dialog(page).getByRole('button', { name: 'Descartar alterações', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard\?/)
  await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente', exact: true })).toBeFocused()
})

test('Insights: voltar ao valor original ou salvar confirmado deixa navegar sem aviso; erro conserva edição', async ({ page }) => {
  const state = await mockDraftApi(page)
  await openInsights(page)
  await openingCount(page).fill('5')
  await openingCount(page).fill('2')
  await globalNav(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true }).click()
  await expect(page).toHaveURL('/manage')
  await expect(dialog(page)).not.toBeVisible()
  await page.goBack()
  await expect(openingCount(page)).toHaveValue('2')
  state.failSave = true
  await openingCount(page).fill('5')
  await page.getByRole('button', { name: 'Salvar regras', exact: true }).click()
  await expect(page.getByText('Não foi possível salvar as regras.', { exact: false })).toBeVisible()
  await expect(openingCount(page)).toHaveValue('5')
  await globalNav(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  await dialog(page).getByRole('button', { name: 'Permanecer', exact: true }).click()
  state.failSave = false
  await page.getByRole('button', { name: 'Salvar regras', exact: true }).click()
  await expect(page.getByText('Regras salvas.', { exact: false })).toBeVisible()
  await globalNav(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true }).click()
  await expect(page).toHaveURL('/manage')
  await expect(dialog(page)).not.toBeVisible()
})

for (const status of [401, 403]) test(`revogação ${status} durante aviso prevalece e limpa rascunho privado`, async ({ page }) => {
  const state = await mockDraftApi(page)
  await openInsights(page)
  await openingCount(page).fill('7')
  await globalNav(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  state.insightStatus = status
  await expect(dialog(page)).not.toBeVisible()
  await expect(openingCount(page)).toHaveCount(0)
  if (status === 401) {
    await expect(page).toHaveURL(/\/login/)
    expect(await page.evaluate(() => sessionStorage.getItem('coldsafe-session'))).toBeNull()
  } else {
    await expect(page).toHaveURL(`/insights?environment=${envA}`)
    expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('coldsafe-session')!).monitoring_selection)).toBeNull()
  }
})

test('logout já solicitado termina durante aviso sem ficar bloqueado', async ({ page }) => {
  await mockDraftApi(page)
  let release!: () => void
  const waiting = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/v1/auth/logout', async (route) => { await waiting; await route.fulfill({ status: 200 }) })
  await openInsights(page)
  await openingCount(page).fill('7')
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await localNav(page).getByRole('link', { name: 'Visão geral', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  release()
  await expect(page).toHaveURL(/\/login/)
  await expect(dialog(page)).not.toBeVisible()
  await expect(openingCount(page)).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('coldsafe-session'))).toBeNull()
})

test('Gestão: abrir vazio não avisa; cancelar editado conserva ou descarta somente seu formulário', async ({ page }) => {
  await mockDraftApi(page)
  await page.goto('/manage')
  await page.getByRole('button', { name: 'Adicionar ambiente', exact: true }).click()
  await page.getByRole('button', { name: 'Cancelar inclusão de ambiente', exact: true }).click()
  await expect(dialog(page)).not.toBeVisible()
  await page.getByRole('button', { name: 'Adicionar ambiente', exact: true }).click()
  await page.getByLabel('Nome do novo ambiente', { exact: true }).fill('Rascunho global')
  await page.getByLabel('Margem de atenção (°C)', { exact: true }).fill('2')
  await page.getByRole('button', { name: 'Cancelar inclusão de ambiente', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  await dialog(page).getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(page.getByLabel('Nome do novo ambiente', { exact: true })).toHaveValue('Rascunho global')
  await page.getByRole('button', { name: 'Cancelar inclusão de ambiente', exact: true }).click()
  await dialog(page).getByRole('button', { name: 'Descartar alterações', exact: true }).click()
  await expect(page.getByLabel('Nome do novo ambiente', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Margem de atenção (°C)', { exact: true })).toHaveValue('2')
})

test('Gestão: ambiente troca somente após decisão e mantém inclusão global independente', async ({ page }) => {
  await mockDraftApi(page)
  await page.goto('/manage')
  await page.getByRole('button', { name: 'Adicionar ambiente', exact: true }).click()
  await page.getByLabel('Nome do novo ambiente', { exact: true }).fill('Rascunho global')
  await page.getByLabel('Margem de atenção (°C)', { exact: true }).fill('2')
  const nextEnvironment = page.getByRole('button', { name: 'Câmara B', exact: true })
  await nextEnvironment.click()
  await dialog(page).getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Limites de temperatura de Câmara A', exact: true })).toBeVisible()
  await expect(page.getByLabel('Margem de atenção (°C)', { exact: true })).toHaveValue('2')
  await expect(nextEnvironment).toBeFocused()
  await nextEnvironment.click()
  await dialog(page).getByRole('button', { name: 'Descartar alterações', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Limites de temperatura de Câmara B', exact: true })).toBeVisible()
  await expect(page.getByLabel('Margem de atenção (°C)', { exact: true })).toHaveValue('1')
  await expect(page.getByLabel('Nome do novo ambiente', { exact: true })).toHaveValue('Rascunho global')
})

test('Laboratório: edição avisa ao sair; job enviado navega sem aviso nem cancelamento', async ({ page }) => {
  const state = await mockDraftApi(page)
  await page.goto('/laboratory')
  await page.getByRole('spinbutton', { name: 'Seed', exact: true }).fill('43')
  await localNav(page).getByRole('link', { name: 'Treinamento de modelos', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  await dialog(page).getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(page.getByRole('spinbutton', { name: 'Seed', exact: true })).toHaveValue('43')
  await page.getByRole('button', { name: 'Gerar dataset', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`job=${fixture.job_id}`))
  await localNav(page).getByRole('link', { name: 'Treinamento de modelos', exact: true }).click()
  await expect(page).toHaveURL('/training')
  await expect(dialog(page)).not.toBeVisible()
  expect(state.generationPosts).toBe(1)
  expect(state.cancellationRequests).toBe(0)
})

test('Treinamento: dataset da URL é baseline; escolha manual alterada exige decisão ao sair', async ({ page }) => {
  const state = await mockDraftApi(page)
  await page.goto(`/training?dataset=${datasetId}`)
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue(datasetId)
  await localNav(page).getByRole('link', { name: 'Dados sintéticos', exact: true }).click()
  await expect(page).toHaveURL('/laboratory')
  await expect(dialog(page)).not.toBeVisible()
  await page.goBack()
  await page.getByLabel('Dataset', { exact: true }).selectOption(otherDatasetId)
  await localNav(page).getByRole('link', { name: 'Dados sintéticos', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  await dialog(page).getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue(otherDatasetId)
  await localNav(page).getByRole('link', { name: 'Dados sintéticos', exact: true }).click()
  await dialog(page).getByRole('button', { name: 'Descartar alterações', exact: true }).click()
  await expect(page).toHaveURL('/laboratory')
  expect(state.trainingPosts).toBe(0)
})

test('Treinamento: job confirmado deixa sair sem aviso e sem pedido de cancelamento', async ({ page }) => {
  const state = await mockDraftApi(page)
  await page.goto('/training')
  await page.getByLabel('Dataset', { exact: true }).selectOption(datasetId)
  await expect(page.getByRole('button', { name: 'Iniciar treinamento', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Iniciar treinamento', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`job=${fixture.job_id}`))
  await localNav(page).getByRole('link', { name: 'Dados sintéticos', exact: true }).click()
  await expect(page).toHaveURL('/laboratory')
  await expect(dialog(page)).not.toBeVisible()
  expect(state.trainingPosts).toBe(1)
  expect(state.cancellationRequests).toBe(0)
})

test('recarga usa aviso nativo do Chromium; recusar mantém edição sem diálogo personalizado', async ({ page }) => {
  await mockDraftApi(page)
  await page.goto('/laboratory')
  await page.getByRole('spinbutton', { name: 'Seed', exact: true }).click()
  await page.getByRole('spinbutton', { name: 'Seed', exact: true }).fill('43')
  const nativeDialog = page.waitForEvent('dialog')
  const reloading = page.reload({ timeout: 2000 }).catch(() => null)
  const warning = await nativeDialog
  expect(warning.type()).toBe('beforeunload')
  await warning.dismiss()
  await reloading
  await expect(page.getByRole('spinbutton', { name: 'Seed', exact: true })).toHaveValue('43')
  await expect(dialog(page)).not.toBeVisible()
})

for (const width of [1440, 320]) test(`aviso acessível ${width}px: foco contido, fundo inerte, texto ampliado e Escape`, async ({ page }) => {
  await page.setViewportSize({ width, height: width === 320 ? 740 : 1000 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockDraftApi(page)
  await page.goto('/laboratory')
  await page.getByRole('spinbutton', { name: 'Seed', exact: true }).fill('43')
  const destination = localNav(page).getByRole('link', { name: 'Treinamento de modelos', exact: true })
  await destination.click()
  await expect(dialog(page)).toBeVisible()
  await expect(dialog(page)).toHaveAttribute('aria-describedby', 'draft-dialog-description')
  const stay = dialog(page).getByRole('button', { name: 'Permanecer', exact: true })
  await expect(stay).toBeFocused()
  // Native dialog may focus browser chrome (reported as body), never inert page controls.
  await page.keyboard.press('Shift+Tab')
  expect(await dialog(page).evaluate((node) => node.contains(document.activeElement) || document.activeElement === document.body)).toBe(true)
  await page.keyboard.press('Tab')
  expect(await dialog(page).evaluate((node) => node.contains(document.activeElement))).toBe(true)
  const backdropBlocks = await page.getByRole('heading', { name: 'Laboratório de Dados', exact: true }).evaluate((node) => {
    ;(node as HTMLElement).focus()
    return document.activeElement !== node
  })
  expect(backdropBlocks).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await mkdir(path('.'), { recursive: true })
  if (width === 320) {
    await page.screenshot({ path: path('mobile-320.png').pathname, fullPage: false })
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    await stay.scrollIntoViewIfNeeded()
    await expect(stay).toBeFocused()
  }
  await page.screenshot({ path: path(width === 320 ? 'mobile-320-200.png' : 'desktop.png').pathname, fullPage: false })
  const measurements = await dialog(page).evaluate((node) => {
    const style = getComputedStyle(node), text = node.querySelector('p')!, button = node.querySelector('button')!
    return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth, dialog: { width: node.getBoundingClientRect().width, scrollWidth: node.scrollWidth, clientWidth: node.clientWidth, background: style.backgroundColor, color: style.color }, overflow: Array.from(document.querySelectorAll('body *')).map((item) => ({ tag: item.tagName, class: item.className, width: item.getBoundingClientRect().width, right: item.getBoundingClientRect().right })).filter((item) => item.right > innerWidth + 1),
      description: { color: getComputedStyle(text).color, fontSize: getComputedStyle(text).fontSize }, button: { color: getComputedStyle(button).color, background: getComputedStyle(button).backgroundColor } }
  })
  await writeFile(path(`${width === 320 ? 'mobile' : 'desktop'}-layout.json`), JSON.stringify(measurements, null, 2))
  expect(measurements.scrollWidth).toBeLessThanOrEqual(measurements.width)
  expect(measurements.dialog.scrollWidth).toBeLessThanOrEqual(measurements.dialog.clientWidth)
  await page.keyboard.press('Escape')
  await expect(dialog(page)).not.toBeVisible()
  await expect(destination).toBeFocused()
  await expect(page.getByRole('spinbutton', { name: 'Seed', exact: true })).toHaveValue('43')
})

test('menu móvel permanece aberto ao conservar rascunho e só fecha após navegar', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await mockDraftApi(page)
  await page.goto('/laboratory')
  await page.getByRole('spinbutton', { name: 'Seed', exact: true }).fill('43')
  await page.getByRole('button', { name: 'Menu', exact: true }).click()
  const menu = page.getByRole('dialog', { name: 'Menu de navegação', exact: true })
  const destination = menu.getByRole('link', { name: 'Monitoramento', exact: true })
  await destination.click()
  await expect(dialog(page)).toBeVisible()
  await dialog(page).getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(menu).toBeVisible()
  await expect(destination).toBeFocused()
  await expect(page).toHaveTitle('Dados sintéticos · ColdSafe')
  await destination.click()
  await dialog(page).getByRole('button', { name: 'Descartar alterações', exact: true }).click()
  await expect(menu).not.toBeVisible()
  await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente', exact: true })).toBeFocused()
})

test('Gestão:403 ao salvar fecha aviso, limpa detalhes e deixa escolher outro ambiente sem ciclo', async ({ page }) => {
  await mockDraftApi(page)
  let identities = 0, puts = 0, release!: () => void
  const waiting = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/v1/auth/me', (route) => {
    identities++
    return route.fulfill({ json: { success: true, data: { user_id: fixture.job_id, email: 'admin@example.invalid', role: 'admin' } } })
  })
  await page.route(`**/api/v1/environments/${envA}/rules`, async (route) => {
    if (route.request().method() !== 'PUT') return route.fallback()
    puts++; await waiting
    await route.fulfill({ status: 403, json: { success: false, error: { message: 'Acesso indisponível.' } } })
  })
  await page.goto('/manage')
  await page.getByLabel('Margem de atenção (°C)', { exact: true }).fill('2')
  await page.getByRole('button', { name: 'Salvar limites', exact: true }).click()
  await globalNav(page).getByRole('link', { name: 'Monitoramento', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  release()
  await expect(dialog(page)).not.toBeVisible()
  await expect(page.getByLabel('Margem de atenção (°C)', { exact: true })).toHaveCount(0)
  await expect(page).toHaveURL('/manage')
  await page.getByRole('button', { name: 'Câmara B', exact: true }).click()
  await expect(page.getByLabel('Margem de atenção (°C)', { exact: true })).toHaveValue('1')
  expect(identities).toBe(1)
  expect(puts).toBe(1)
})
