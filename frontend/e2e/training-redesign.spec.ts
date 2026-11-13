import { expect, test, type Page } from '@playwright/test'
import fixture from '../src/features/training/training.fixture.json' with { type: 'json' }

const jobId = fixture.job_id, datasetId = fixture.dataset_id
const timestamp = '2026-10-31T12:00:00Z'
const configuration = { job_type: 'generation', total_units: 1000000, seed: 42, environment_id: null, equipment_count: 100, days: 30,
  sensor_types: ['ambient_temperature_c', 'humidity_percent', 'light_percent', 'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c'],
  failure_fraction: .6, failure_modes: ['bearing_wear', 'imbalance'], operating_modes: ['normal', 'heavy', 'cycling'], noise_scale: 1, missing_rate: .01, outlier_rate: .002 }
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
const evidence = new URL('../../.impeccable/review/ux-08/desktop.png', import.meta.url)

async function training(page: Page) {
  const report = structuredClone(fixture)
  report.health.metrics.validation.baseline.mae = 10
  report.health.metrics.validation.candidate.mae = 1
  report.health.metrics.test.baseline.mae = 20
  const state = { posts: [] as unknown[], otherWrites: 0, resultGets: 0, resultStatus: 200, postStatus: 202,
    jobStatus: 'completed', equipmentCount: 100, report }
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('coldsafe-session')) sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'rd13-admin', expires_at: '2099-01-01T00:00:00Z' }))
  })
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { success: false } }))
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: jobId, email: 'admin@example.invalid', role: 'admin' } } }))
  await page.route('**/api/v3/**', route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    expect(route.request().headers().authorization).toBe('Bearer rd13-admin')
    const job = { id: jobId, owner_user_id: jobId, job_type: 'training', status: state.jobStatus, completed_units: 2, total_units: 2,
      result_id: state.jobStatus === 'completed' ? fixture.model_id : null, dataset_id: datasetId, environment_id: null, error_code: null,
      config: { job_type: 'training', dataset_id: datasetId, environment_id: null }, created_at: timestamp, updated_at: timestamp }
    if (path === '/api/v3/jobs' && method === 'POST') {
      state.posts.push(route.request().postDataJSON())
      return route.fulfill({ status: state.postStatus, json: state.postStatus === 202 ? envelope({ ...job, status: 'queued', completed_units: 0, result_id: null }) : { success: false } })
    }
    if (method !== 'GET') { state.otherWrites++; return route.fulfill({ status: 405 }) }
    // Lista vazia exercita dataset autorizado fora dos 50 mais recentes.
    if (path === '/api/v3/datasets') return route.fulfill({ json: envelope([]) })
    if (path === `/api/v3/datasets/${datasetId}`) return route.fulfill({ json: envelope({ id: datasetId, owner_user_id: jobId, generation_job_id: jobId,
      created_at: timestamp, row_count: 1000000, config: { ...configuration, equipment_count: state.equipmentCount }, storage_version: 'offline-numpy-v1',
      units: Object.fromEntries(configuration.sensor_types.map(key => [key, 'unidade'])), quality: {
        missing_by_sensor: Object.fromEntries(configuration.sensor_types.map(key => [key, 10000])),
        range_by_sensor: Object.fromEntries(configuration.sensor_types.map(key => [key, { min: 0, max: 100 }])), rul_observed_rows: 600000, rul_censored_rows: 400000 } }) })
    if (path === `/api/v3/jobs/${jobId}`) return route.fulfill({ json: envelope(job) })
    if (path === `/api/v3/jobs/${jobId}/result`) {
      state.resultGets++
      return route.fulfill({ status: state.resultStatus, json: state.resultStatus === 200 ? envelope(state.report) : { success: false } })
    }
    return route.fulfill({ status: 404, json: { success: false } })
  })
  return state
}

for (const scenario of [{ width: 1440, text: 100 }, { width: 390, text: 100 }, { width: 320, text: 200 }]) {
  test(`M-09 dois alvos, tabelas e recuperação da URL: ${scenario.width}px texto ${scenario.text}% (API simulada)`, async ({ page }) => {
    await page.setViewportSize({ width: scenario.width, height: 1024 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const state = await training(page)
    await page.goto(`/training?job=${jobId}&dataset=${datasetId}#diagnosticos`)
    if (scenario.text === 200) await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    const select = page.getByLabel('Dataset', { exact: true })
    await expect(select).toHaveValue(datasetId)
    await expect(select).toHaveAccessibleDescription(/outro dataset autorizado/)
    await expect(select.locator('option:checked')).toHaveText(/Dataset de .* · 1\.000\.000 linhas/)
    await expect(page.getByText('Nenhum dataset concluído', { exact: false })).toHaveCount(0)
    await expect(page.locator('input')).toHaveCount(0)
    await expect(page.getByText('Seed do treino: 42.', { exact: false })).toBeHidden()
    await expect(page.getByText('Pacote rejeitado pela validação', { exact: true })).toBeVisible()
    await expect(page.getByText(/Processamento concluído\. Treinar não ativa o modelo/)).toBeVisible()
    await expect(page.getByText(/Dados sintéticos, sem validação física/)).toBeVisible()
    const packageResult = page.getByRole('region', { name: 'Resultado do pacote', exact: true })
    const setup = page.getByRole('region', { name: 'Selecionar dataset concluído', exact: true })
    expect((await packageResult.boundingBox())!.y).toBeLessThan((await setup.boundingBox())!.y)
    const health = page.getByRole('region', { name: 'Resultados de Saúde', exact: true })
    const rul = page.getByRole('region', { name: 'Resultados de Vida útil restante (RUL)', exact: true })
    const boxes = await Promise.all([health.boundingBox(), rul.boundingBox()])
    if (scenario.width === 1440) expect(boxes[0]!.x).toBeLessThan(boxes[1]!.x)
    else expect(boxes[0]!.y).toBeLessThan(boxes[1]!.y)
    await expect(health.getByText('1 ponto de saúde', { exact: true })).toBeVisible()
    await expect(health.getByText('10 pontos de saúde', { exact: true })).toBeVisible()
    await expect(rul.getByText('30 horas', { exact: true })).toBeVisible()
    await expect(rul.getByText('23 horas', { exact: true })).toBeVisible()
    if (scenario.width === 1440) {
      await page.getByRole('heading', { level: 1 }).blur()
      await page.evaluate(() => scrollTo(0, 0))
      await page.screenshot({ path: evidence.pathname })
    }
    await select.focus(); await expect(select).toBeFocused()
    const expectedMae = [['10', '1', '20', '2,46'], ['23', '30', '23', '2,46']]
    for (const [index, target] of [health, rul].entries()) {
      const metrics = target.getByRole('region', { name: index === 0 ? 'Métricas de Saúde' : 'Métricas de Vida útil restante (RUL)', exact: true })
      await expect(metrics).toBeHidden()
      await target.getByText('Métricas e diagnósticos', { exact: true }).click()
      await expect(metrics).toBeVisible()
      const rows = metrics.locator('tbody tr')
      await expect(rows).toHaveCount(4)
      for (let i = 0; i < 4; i++) {
        await expect(rows.nth(i).locator('th')).toHaveText(i < 2 ? 'Validação' : 'Teste reservado')
        await expect(rows.nth(i).locator('td').nth(0)).toHaveText(i % 2 === 0 ? 'Baseline' : 'Candidato')
        await expect(rows.nth(i).locator('td').nth(1)).toHaveText(expectedMae[index]![i]!)
      }
      const chart = target.getByRole('img', { name: /Previsto versus real/ }).locator('canvas')
      await expect.poll(async () => (await chart.boundingBox())?.width ?? 0).toBeGreaterThan(0)
      await target.getByText('Inspecionar erros em tabela (2 linhas)', { exact: true }).click()
      const errors = target.getByRole('region', { name: index === 0 ? 'Erros de Saúde' : 'Erros de Vida útil restante (RUL)', exact: true })
      await expect(errors.locator('tbody tr')).toHaveCount(2)
      await expect(errors).toContainText('50'); await expect(errors).toContainText('-2')
      await expect(target.getByText('máximo 500', { exact: false })).toBeVisible()
      await expect(target.getByText('não demonstra causalidade', { exact: false })).toBeVisible()
      const importance = target.getByRole('region', { name: index === 0 ? 'Importância em Saúde' : 'Importância em Vida útil restante (RUL)', exact: true })
      await expect(importance).toContainText('-0,02')
      await expect(metrics).toHaveAccessibleDescription(/use as setas/)
      await metrics.focus(); await expect(metrics).toBeFocused()
      if (scenario.width < 1100) {
        await page.keyboard.press('ArrowRight')
        await expect.poll(() => metrics.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
      }
    }
    const nearFailure = rul.getByRole('region', { name: 'Métricas perto da falha', exact: true })
    await expect(nearFailure).toContainText('-1,2')
    await expect(page.getByText('numpy', { exact: true })).toBeHidden()
    await page.getByText('Versões e partições da avaliação', { exact: true }).click()
    await expect(page.getByText('numpy', { exact: true })).toBeVisible()
    await expect(page.getByText('Equipamentos por partição', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(scenario.width)
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Resultado do pacote', exact: true })).toBeVisible()
    await expect(page).toHaveURL(`/training?job=${jobId}&dataset=${datasetId}#diagnosticos`)
    expect(state.posts).toHaveLength(0); expect(state.otherWrites).toBe(0)
  })
}

test('lista vazia orienta a gerar dados quando não há seleção', async ({ page }) => {
  const state = await training(page)
  await page.goto('/training')
  const setup = page.getByRole('region', { name: 'Selecionar dataset concluído', exact: true })
  await expect(setup.getByText('Nenhum dataset concluído', { exact: false })).toBeVisible()
  await expect(setup.getByRole('link', { name: 'Gerar dados sintéticos', exact: true })).toHaveAttribute('href', '/laboratory')
  await expect(setup.getByRole('button', { name: 'Iniciar treinamento', exact: true })).toBeDisabled()
  expect(state.posts).toHaveLength(0)
})

test('pacote apto exige aprovação dos dois alvos na validação', async ({ page }) => {
  const state = await training(page)
  state.report.rul.metrics.validation.candidate.mae = 22
  state.report.rul.metrics.test.candidate.mae = 40
  state.report.rul.status = 'eligible'
  state.report.eligible = true
  await page.goto(`/training?job=${jobId}`)
  await expect(page.getByText('Pacote apto pela validação', { exact: true })).toBeVisible()
  await expect(page.getByText('Apto pela validação', { exact: true })).toHaveCount(2)
  await expect(page.getByText('22 horas', { exact: true })).toBeVisible()
  await expect(page.getByText('40 horas', { exact: true })).toHaveCount(0)
  expect(state.posts).toHaveLength(0); expect(state.otherWrites).toBe(0)
})

test('resultado indisponível conserva job concluído e recupera só GET', async ({ page }) => {
  const state = await training(page); state.resultStatus = 503
  await page.goto(`/training?job=${jobId}&dataset=${datasetId}`)
  await expect(page.getByRole('region', { name: 'Acompanhamento do treinamento', exact: true })).toContainText('Concluído')
  await expect(page.getByRole('alert')).toContainText(/não é necessário reenviar/i)
  await expect(page.getByRole('heading', { name: 'Resultado do pacote', exact: true })).toHaveCount(0)
  state.resultStatus = 200
  await page.getByRole('button', { name: 'Atualizar acompanhamento', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Resultado do pacote', exact: true })).toBeVisible()
  expect(state.resultGets).toBe(2); expect(state.posts).toHaveLength(0)
})

test('mínimo de três equipamentos, POST único e 100% ainda em execução', async ({ page }) => {
  const state = await training(page); state.equipmentCount = 2
  await page.goto(`/training?dataset=${datasetId}`)
  const submit = page.getByRole('button', { name: 'Iniciar treinamento', exact: true })
  await expect(page.getByRole('alert')).toContainText('ao menos três equipamentos')
  await expect(submit).toBeDisabled(); expect(state.posts).toHaveLength(0)
  state.equipmentCount = 3; state.jobStatus = 'running'
  await page.reload(); await expect(submit).toBeEnabled(); await submit.click()
  const progress = page.getByRole('region', { name: 'Acompanhamento do treinamento', exact: true })
  await expect(progress).toContainText('Em execução · 2 / 2 etapas')
  await expect(progress.getByText('Finalizando o treinamento.', { exact: false })).toBeVisible()
  expect((await progress.boundingBox())!.y).toBeLessThan((await submit.boundingBox())!.y)
  expect(state.resultGets).toBe(0)
  state.jobStatus = 'completed'
  await expect(page.getByRole('heading', { name: 'Resultado do pacote', exact: true })).toBeVisible()
  expect(state.posts).toEqual([{ job_type: 'training', dataset_id: datasetId, environment_id: null }])
  expect(state.otherWrites).toBe(0)
})

test('até 500 linhas do teste continuam acessíveis em cada tabela de erros', async ({ page }) => {
  const state = await training(page)
  for (const target of [state.report.health, state.report.rul]) {
    target.diagnostics.sample_count = 500; target.diagnostics.permutation.sample_count = 500
    target.diagnostics.scatter = Array.from({ length: 500 }, (_, index) => ({ actual: index % 100, predicted: index % 100 + 1, baseline: 50, error: 1 }))
  }
  await page.goto(`/training?job=${jobId}`)
  for (const name of ['Saúde', 'Vida útil restante (RUL)']) {
    const target = page.getByRole('region', { name: `Resultados de ${name}`, exact: true })
    await target.getByText('Métricas e diagnósticos', { exact: true }).click()
    await target.getByText('Inspecionar erros em tabela (500 linhas)', { exact: true }).click()
    const errors = target.getByRole('region', { name: `Erros de ${name}`, exact: true })
    await expect(errors.locator('tbody tr')).toHaveCount(500)
    await errors.focus(); await page.keyboard.press('End')
    await expect.poll(() => errors.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  }
  expect(state.posts).toHaveLength(0)
})

test('envio incerto do treino permanece bloqueado e não duplica POST ao navegar', async ({ page }) => {
  const state = await training(page); state.postStatus = 503
  await page.goto(`/training?dataset=${datasetId}`)
  await page.getByRole('button', { name: 'Iniciar treinamento', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('não tem retomada garantida')
  await expect(page.getByRole('button', { name: 'Iniciar treinamento', exact: true })).toBeDisabled()
  await page.getByRole('navigation', { name: 'Navegação da área', exact: true }).getByRole('link', { name: 'Dados sintéticos', exact: true }).click()
  await expect(page).toHaveURL('/laboratory')
  expect(state.posts).toHaveLength(1); expect(state.otherWrites).toBe(0)
})
