import { expect, test } from '@playwright/test'
import fixture from '../src/features/training/training.fixture.json' with { type: 'json' }

const id = fixture.job_id
const datasetId = fixture.dataset_id
const generatedAt = '2026-10-17T12:00:00Z'
const config = { job_type: 'generation', total_units: 1000000, seed: 42, environment_id: null,
  equipment_count: 100, days: 30,
  sensor_types: ['ambient_temperature_c', 'humidity_percent', 'light_percent', 'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c'],
  failure_fraction: .6, failure_modes: ['bearing_wear', 'imbalance'], operating_modes: ['normal', 'heavy', 'cycling'],
  noise_scale: 1, missing_rate: .01, outlier_rate: .002 }
const dataset = { id: datasetId, owner_user_id: id, generation_job_id: id, created_at: generatedAt,
  row_count: 1000000, config, storage_version: 'offline-numpy-v1',
  units: Object.fromEntries(config.sensor_types.map((key) => [key, 'unit'])),
  quality: { missing_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, 10])),
    range_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, { min: 0, max: 100 }])),
    rul_observed_rows: 600000, rul_censored_rows: 400000 } }
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })

for (const path of ['laboratory', 'training'] as const) {
  test(`${path}: carga, pausa, recarga e falhas do LLM em 320 px (HTTP simulado)`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 })
    await page.addInitScript(() => sessionStorage.setItem('coldsafe-session', JSON.stringify({
      token: 'llm-status-test', expires_at: '2099-01-01T00:00:00Z',
    })))
    await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
      success: true, data: { user_id: id, email: 'admin@example.com', role: 'admin' },
    } }))
    let state = 'loading'
    let complete = false
    let posts = 0
    let statusRequests = 0
    const jobType = path === 'laboratory' ? 'generation' : 'training'
    const jobConfig = jobType === 'generation' ? config : { job_type: 'training', dataset_id: datasetId, environment_id: null }
    const job = () => ({ id, owner_user_id: id, job_type: jobType,
      status: complete ? 'completed' : 'running', completed_units: complete ? (jobType === 'generation' ? 1000000 : 2) : 0,
      total_units: jobType === 'generation' ? 1000000 : 2, error_code: null, environment_id: null,
      result_id: complete ? (jobType === 'generation' ? datasetId : fixture.model_id) : null,
      dataset_id: jobType === 'generation' ? null : datasetId, config: jobConfig,
      created_at: generatedAt, updated_at: generatedAt })
    await page.route('**/api/v3/**', async (route) => {
      const request = route.request()
      const endpoint = new URL(request.url()).pathname
      expect(request.headers().authorization).toBe('Bearer llm-status-test')
      if (endpoint === '/api/v3/llm/status') {
        statusRequests++; expect(request.method()).toBe('GET')
        return route.fulfill({ json: envelope({ state, model: 'llama3.2:3b-instruct-q4_K_M' }) })
      }
      if (endpoint === '/api/v3/jobs' && request.method() === 'POST') {
        posts++; expect(request.postDataJSON()).toEqual(jobConfig)
        return route.fulfill({ status: 202, json: envelope(job()) })
      }
      if (endpoint === `/api/v3/jobs/${id}`) return route.fulfill({ json: envelope(job()) })
      if (endpoint === `/api/v3/jobs/${id}/result`) return route.fulfill({ json: envelope(fixture) })
      if (endpoint === `/api/v3/datasets/${datasetId}`) return route.fulfill({ json: envelope(dataset) })
      if (endpoint === '/api/v3/datasets') return route.fulfill({ json: envelope([
        { id: datasetId, name: 'Dataset simulado', row_count: 1000000, generation_job_id: id, created_at: generatedAt },
      ]) })
      throw new Error(`Unexpected API request: ${request.method()} ${endpoint}`)
    })
    await page.goto(`/${path}${path === 'training' ? `?dataset=${datasetId}` : ''}`)
    const status = page.locator('.llm-status')
    await expect(status).toContainText('Preparando o modelo local')
    state = 'ready'
    await expect(status).toContainText('Modelo local carregado')
    expect(posts).toBe(0)
    await expect(page.getByRole('textbox', { name: /mensagem|conversa|pergunta/i })).toHaveCount(0)
    await page.getByRole('button', { name: path === 'laboratory' ? 'Gerar dataset' : 'Iniciar treinamento', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`job=${id}`))
    state = 'paused'
    await expect(status).toContainText('pausado durante geração ou treinamento')
    await expect(status).toContainText('recarregado automaticamente')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`${path}-llm-paused-320.png`), fullPage: true })
    complete = true; state = 'ready'
    await expect(status).toContainText('Modelo local carregado')
    await expect(page.getByRole('heading', { name: path === 'laboratory' ? 'Dataset concluído' : 'Resultado do pacote', exact: true })).toBeVisible()
    await page.reload()
    await expect(status).toContainText('Modelo local carregado')
    expect(posts).toBe(1)
    state = 'unavailable'
    await expect(status).toContainText('Modelo local indisponível')
    state = 'model_missing'
    await expect(status).toContainText('Modelo local ainda não preparado')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(posts).toBe(1); expect(statusRequests).toBeGreaterThanOrEqual(6)
  })
}
