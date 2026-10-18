import { expect, test } from '@playwright/test'
import fixture from '../src/features/training/training.fixture.json' with { type: 'json' }
const id = fixture.job_id
const datasetId = fixture.dataset_id
const config = { job_type: 'generation', total_units: 1000000, seed: 42, environment_id: null, equipment_count: 100, days: 30,
  sensor_types: ['ambient_temperature_c', 'humidity_percent', 'light_percent', 'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c'],
  failure_fraction: .6, failure_modes: ['bearing_wear', 'imbalance'], operating_modes: ['normal', 'heavy', 'cycling'], noise_scale: 1, missing_rate: .01, outlier_rate: .002 }
const job = { id, owner_user_id: id, job_type: 'training', status: 'queued', completed_units: 0, total_units: 2, result_id: null,
  dataset_id: datasetId, environment_id: null, error_code: null, config: { job_type: 'training', dataset_id: datasetId, environment_id: null },
  created_at: '2026-10-17T12:00:00Z', updated_at: '2026-10-17T12:00:00Z' }
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })

test('treino autenticado recuperável, métricas, tabela e mobile sem POST duplicado (API simulada)', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'training-test', expires_at: '2099-01-01T00:00:00Z' })))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { success: true, data: { user_id: id, email: 'admin@example.com', role: 'admin' } } }))
  let posts = 0
  await page.route('**/api/v3/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    expect(route.request().headers().authorization).toBe('Bearer training-test')
    if (path === '/api/v3/datasets') return route.fulfill({ json: envelope([{ id: datasetId, name: 'Dataset do ensaio', row_count: 1000000, generation_job_id: id, created_at: job.created_at }]) })
    if (path === `/api/v3/datasets/${datasetId}`) return route.fulfill({ json: envelope({ id: datasetId, owner_user_id: id, generation_job_id: id, created_at: job.created_at, row_count: 1000000, config, storage_version: 'offline-numpy-v1', units: Object.fromEntries(config.sensor_types.map((key) => [key, 'unit'])), quality: { missing_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, 10])), range_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, { min: 0, max: 100 }])), rul_observed_rows: 600000, rul_censored_rows: 400000 } }) })
    if (path === '/api/v3/jobs' && route.request().method() === 'POST') { posts++; expect(route.request().postDataJSON()).toEqual(job.config); return route.fulfill({ status: 202, json: envelope(job) }) }
    if (path === `/api/v3/jobs/${id}`) return route.fulfill({ json: envelope({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id }) })
    if (path === `/api/v3/jobs/${id}/result`) return route.fulfill({ json: envelope(fixture) })
    return route.fulfill({ status: 404, json: { success: false } })
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/training?dataset=${datasetId}`)
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue(datasetId)
  await expect(page.getByText('RUL observado:', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Iniciar treinamento', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`job=${id}`))
  await expect(page.getByRole('heading', { name: 'Resultado do pacote' })).toBeVisible()
  await expect(page.getByText('Pacote rejeitado:', { exact: false })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Resultados de Saúde', exact: true })).toContainText('2,46')
  await page.getByText('Inspecionar erros em tabela (2 linhas)').first().click()
  await expect(page.getByRole('region', { name: 'Erros de Saúde', exact: true })).toContainText('32')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.reload(); await expect(page.getByRole('heading', { name: 'Resultado do pacote' })).toBeVisible(); expect(posts).toBe(1)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: test.info().outputPath('training-mocked.png'), fullPage: true })
})

test('operador não envia nem consulta dados de treinamento (API simulada)', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'operator', expires_at: '2099-01-01T00:00:00Z' })))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { success: true, data: { user_id: id, email: 'operator@example.com', role: 'operator' } } }))
  let privateRequests = 0
  await page.route('**/api/v3/**', (route) => { privateRequests++; return route.fulfill({ status: 403 }) })
  await page.goto('/training'); await expect(page.getByText('O treinamento está disponível apenas para administradores.', { exact: false })).toBeVisible()
  expect(privateRequests).toBe(0); await expect(page.getByRole('button', { name: 'Iniciar treinamento' })).toHaveCount(0)
})
