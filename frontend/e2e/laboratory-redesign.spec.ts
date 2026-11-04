import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'

const jobId = '00000000-0000-4000-8000-000000000101'
const datasetId = '00000000-0000-4000-8000-000000000102'
const ownerId = '00000000-0000-4000-8000-000000000103'
const timestamp = '2026-10-31T12:00:00Z'
const defaults = { job_type: 'generation', total_units: 1000000, seed: 42, environment_id: null,
  equipment_count: 100, days: 30,
  sensor_types: ['ambient_temperature_c', 'humidity_percent', 'light_percent', 'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c'],
  failure_fraction: .6, failure_modes: ['bearing_wear', 'imbalance'], operating_modes: ['normal', 'heavy', 'cycling'],
  noise_scale: 1, missing_rate: .01, outlier_rate: .002 }
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
const evidence = new URL('../../.impeccable/review/rd-12/', import.meta.url)

async function laboratory(page: Page) {
  const state = { status: 'running', postStatus: 202, jobStatus: 200, datasetStatus: 200, sampleStatus: 200,
    posts: [] as unknown[], datasetGets: 0, sampleGets: 0, otherWrites: 0, config: { ...defaults } }
  await page.addInitScript(({ jobId }) => {
    if (!sessionStorage.getItem('rd12-initialized')) {
      sessionStorage.setItem('rd12-initialized', 'true')
      sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'rd12-admin', expires_at: '2099-01-01T00:00:00Z', known_jobs: { generation: { jobId } } }))
    }
  }, { jobId })
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { success: false } }))
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: ownerId, email: 'admin@example.invalid', role: 'admin' } } }))
  await page.route('**/api/v3/**', route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    expect(route.request().headers().authorization).toBe('Bearer rd12-admin')
    const job = { id: jobId, owner_user_id: ownerId, job_type: 'generation', status: state.status,
      completed_units: state.status === 'failed' ? 500000 : 1000000, total_units: 1000000,
      result_id: state.status === 'completed' ? datasetId : null, dataset_id: null, error_code: state.status === 'failed' ? 'GENERATION_FAILED' : null,
      environment_id: state.config.environment_id, config: state.config, created_at: timestamp, updated_at: timestamp }
    if (path === '/api/v3/llm/status') return route.fulfill({ json: envelope({ state: 'ready', model: 'test-model' }) })
    if (method === 'POST' && path === '/api/v3/jobs') {
      state.config = route.request().postDataJSON(); state.posts.push(state.config)
      return route.fulfill({ status: state.postStatus, json: state.postStatus === 202 ? envelope({ ...job, config: state.config, status: 'queued', completed_units: 0 }) : { success: false } })
    }
    if (method !== 'GET') { state.otherWrites++; return route.fulfill({ status: 405 }) }
    if (path === `/api/v3/jobs/${jobId}`) return route.fulfill({ status: state.jobStatus, json: state.jobStatus === 200 ? envelope(job) : { success: false } })
    if (path === `/api/v3/datasets/${datasetId}/sample`) {
      state.sampleGets++
      return route.fulfill({ status: state.sampleStatus, json: state.sampleStatus === 200 ? envelope({ dataset_id: datasetId,
        rows: Array.from({ length: 10 }, (_, i) => ({ equipment_id: ownerId, observed_at: timestamp,
          measurements: Object.fromEntries(state.config.sensor_types.map(key => [key, i === 0 ? null : 0])),
          degradation_true: 0, health_score_true: 100, rul_hours_true: null, rul_observed: false })) }) : { success: false } })
    }
    if (path === `/api/v3/datasets/${datasetId}`) {
      state.datasetGets++
      return route.fulfill({ status: state.datasetStatus, json: state.datasetStatus === 200 ? envelope({ id: datasetId, owner_user_id: ownerId,
        generation_job_id: jobId, created_at: timestamp, row_count: 1000000, config: state.config, storage_version: 'offline-numpy-v1',
        units: Object.fromEntries(state.config.sensor_types.map(key => [key, key.endsWith('_c') ? '°C' : 'unidade'])), quality: {
          missing_by_sensor: Object.fromEntries(state.config.sensor_types.map(key => [key, 10000])),
          range_by_sensor: Object.fromEntries(state.config.sensor_types.map(key => [key, { min: 0, max: 100 }])),
          rul_observed_rows: 600000, rul_censored_rows: 400000 } }) : { success: false } })
    }
    if (path === '/api/v3/datasets') return route.fulfill({ json: envelope([]) })
    return route.fulfill({ status: 404, json: { success: false } })
  })
  return state
}

for (const scenario of [{ width: 1440, text: 100 }, { width: 390, text: 100 }, { width: 320, text: 200 }]) {
  test(`M-08 formulário e resultado acessíveis: ${scenario.width}px texto ${scenario.text}% (API simulada)`, async ({ page }) => {
    await page.setViewportSize({ width: scenario.width, height: 1024 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const state = await laboratory(page)
    await page.goto('/laboratory')
    if (scenario.text === 200) await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    await expect(page.getByText('Modelo local carregado.', { exact: false })).toBeVisible()
    const configuration = page.getByRole('region', { name: 'Configuração da geração', exact: true })
    const estimate = page.getByRole('region', { name: 'Estimativa e execução', exact: true })
    const model = page.locator('.model-state')
    const boxes = await Promise.all([configuration.boundingBox(), estimate.boundingBox(), model.boundingBox()])
    if (scenario.width === 1440) expect(boxes[0]!.x).toBeLessThan(boxes[1]!.x)
    else { expect(boxes[2]!.y).toBeLessThan(boxes[0]!.y); expect(boxes[0]!.y).toBeLessThan(boxes[1]!.y) }
    await expect(page.locator('input[type="number"]')).toHaveCount(8)
    await expect(page.locator('input[name="sensor_types"]')).toHaveCount(6)
    await expect(estimate).toContainText('600 sensores')
    const lines = page.getByLabel('Linhas', { exact: true })
    await lines.fill('2000001')
    await page.getByRole('button', { name: 'Gerar dataset', exact: true }).click()
    await expect(lines).toBeFocused(); await expect(lines).toHaveAttribute('aria-invalid', 'true')
    await expect(lines).toHaveAccessibleDescription(/1.000.000 a 2.000.000/)
    expect(state.posts).toHaveLength(0)
    if (scenario.text === 200) {
      await mkdir(evidence, { recursive: true })
      await page.screenshot({ path: new URL('mobile-320-text-200-error-focus.png', evidence).pathname })
    }
    await lines.fill('1000000')
    await expect(lines).not.toHaveAttribute('aria-invalid', 'true')
    await lines.focus(); await page.keyboard.press('Tab'); await expect(page.getByLabel('Seed', { exact: true })).toBeFocused()
    await mkdir(evidence, { recursive: true })
    const name = scenario.width === 1440 ? 'desktop' : scenario.width === 390 ? 'mobile' : 'mobile-320-text-200'
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: new URL(`${name}.png`, evidence).pathname, fullPage: scenario.text === 100 })
    if (scenario.width === 1440) await page.screenshot({ path: new URL('hero-repro.png', evidence).pathname })
    const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      fontSize: getComputedStyle(document.documentElement).fontSize, fields: [...document.querySelectorAll('input')].map(el => ({ name: el.name, width: el.getBoundingClientRect().width })),
      input: { color: getComputedStyle(document.querySelector('input')!).color, background: getComputedStyle(document.querySelector('input')!).backgroundColor, border: getComputedStyle(document.querySelector('input')!).borderColor },
      button: { color: getComputedStyle(document.querySelector('.execution button')!).color, background: getComputedStyle(document.querySelector('.execution button')!).backgroundColor } }))
    expect(layout.scrollWidth).toBe(scenario.width)
    await writeFile(new URL(`${name}-layout.json`, evidence), JSON.stringify(layout, null, 2))
    const generate = page.getByRole('button', { name: 'Gerar dataset', exact: true })
    if (scenario.text === 200) {
      await generate.focus(); await generate.scrollIntoViewIfNeeded()
      await page.screenshot({ path: new URL('mobile-320-text-200-action.png', evidence).pathname })
    }
    await generate.click()
    await expect(page).toHaveURL(`/laboratory?job=${jobId}`)
    const tracking = page.getByRole('region', { name: 'Acompanhamento da geração', exact: true })
    await expect(tracking).toContainText('Em execução · 100%')
    await expect(page.getByRole('link', { name: 'Treinar modelos com este dataset', exact: true })).toHaveCount(0)
    expect(state.datasetGets).toBe(0)
    state.status = 'completed'
    await expect(page.getByRole('heading', { name: 'Dataset concluído', exact: true })).toBeVisible()
    expect(state.sampleGets).toBe(0)
    await page.getByText('Configuração enviada ao gerador', { exact: true }).click()
    await expect(page.locator('pre')).toContainText('"seed": 42')
    await expect(page.getByText('RUL observada:', { exact: false })).toContainText('600.000')
    await expect(page.getByText('Taxa de outliers configurada:', { exact: false })).toContainText('não é uma contagem')
    await page.getByRole('button', { name: 'Ver amostra', exact: true }).click()
    const sample = page.getByRole('region', { name: 'Amostra do dataset sintético', exact: true })
    await expect(sample.locator('tbody tr')).toHaveCount(10)
    await expect(sample).toContainText('Faltante'); await expect(sample).toContainText('Não (censurada)')
    await expect(page.getByText('Até 10 linhas, seleção determinística', { exact: false })).toContainText('não representativa')
    await page.getByRole('heading', { name: 'Dataset concluído', exact: true }).evaluate(el => el.scrollIntoView({ block: 'start' }))
    await page.screenshot({ path: new URL(`${name}-result.png`, evidence).pathname })
    await sample.focus(); await page.keyboard.press('ArrowRight')
    await expect.poll(() => sample.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
    if (scenario.text === 200) {
      await sample.evaluate(el => el.scrollIntoView({ block: 'start' }))
      await page.screenshot({ path: new URL('mobile-320-text-200-sample.png', evidence).pathname })
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(scenario.width)
    await page.getByRole('link', { name: 'Treinar modelos com este dataset', exact: true }).click()
    await expect(page).toHaveURL(`/training?dataset=${datasetId}`)
    await page.getByRole('link', { name: 'Retomar geração', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Dataset concluído', exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Dataset concluído', exact: true })).toBeVisible()
    expect(state.posts).toEqual([defaults]); expect(state.otherWrites).toBe(0)
  })
}

test('resultado e amostra com falha parcial recuperam só por GET', async ({ page }) => {
  const state = await laboratory(page); state.status = 'completed'; state.datasetStatus = 503
  await page.goto(`/laboratory?job=${jobId}`)
  await expect(page.getByRole('alert')).toContainText('não está confirmada')
  await expect(page.getByRole('heading', { name: 'Acompanhamento da geração', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Treinar modelos com este dataset', exact: true })).toHaveCount(0)
  state.datasetStatus = 200
  await page.getByRole('button', { name: 'Atualizar acompanhamento', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Dataset concluído', exact: true })).toBeVisible()
  state.sampleStatus = 503
  await page.getByRole('button', { name: 'Ver amostra', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Não foi possível consultar a amostra')
  await expect(page.getByRole('region', { name: 'Qualidade dos sensores; role horizontalmente para ver todas as colunas', exact: true })).toBeVisible()
  state.sampleStatus = 200
  await page.getByRole('button', { name: 'Ver amostra', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Amostra do dataset sintético', exact: true }).locator('tbody tr')).toHaveCount(10)
  expect(state.posts).toHaveLength(0); expect(state.sampleGets).toBe(2)
})

test('envio incerto bloqueia novo POST e falha parcial não libera treinamento', async ({ page }) => {
  const state = await laboratory(page); state.postStatus = 503
  await page.goto('/laboratory')
  await page.getByRole('button', { name: 'Gerar dataset', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('não tem retomada garantida')
  await expect(page.getByRole('button', { name: 'Gerar dataset', exact: true })).toBeDisabled()
  await page.getByRole('link', { name: 'Retomar geração', exact: true }).click()
  state.status = 'failed'
  await expect(page.getByText('Resultados parciais', { exact: false })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Treinar modelos com este dataset', exact: true })).toHaveCount(0)
  expect(state.posts).toHaveLength(1); expect(state.datasetGets).toBe(0)
})

test('perda de sessão durante acompanhamento remove dados privados', async ({ page }) => {
  const state = await laboratory(page)
  await page.goto(`/laboratory?job=${jobId}`)
  await expect(page.getByRole('heading', { name: 'Acompanhamento da geração', exact: true })).toBeVisible()
  state.jobStatus = 401
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByText(jobId, { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('coldsafe-session'))).toBeNull()
  expect(state.posts).toHaveLength(0)
})
