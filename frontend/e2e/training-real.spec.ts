import { writeFileSync } from 'node:fs'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const api = process.env.TRAINING_REAL_API_URL ?? ''
test.skip(!process.env.TRAINING_REAL_URL || !api || !process.env.TRAINING_REAL_PASSWORD,
  'Run through the disposable B2-23 training integration harness')

async function login(request: APIRequestContext, page: Page, email: string) {
  const response = await request.post(`${api}/api/v1/auth/login`, { data: {
    email, password: process.env.TRAINING_REAL_PASSWORD,
  } })
  expect(response.status()).toBe(200)
  const session = (await response.json()).data
  await page.addInitScript((value) => sessionStorage.setItem('coldsafe-session', JSON.stringify(value)), session)
  return session
}

test('admin treina pela página, recarrega e confere valores dos dois alvos reais', async ({ page, request }) => {
  const session = await login(request, page, process.env.TRAINING_REAL_EMAIL!)
  const headers = { authorization: `Bearer ${session.token}` }
  const dataset = process.env.TRAINING_REAL_DATASET!
  let posts = 0
  page.on('request', (call) => { if (call.url() === `${api}/api/v3/jobs` && call.method() === 'POST') posts++ })
  await page.goto(`/training?dataset=${dataset}`)
  await expect(page.getByRole('heading', { name: 'Treinamento', exact: true })).toBeVisible()
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue(dataset)
  const submit = page.getByRole('button', { name: 'Iniciar treinamento', exact: true })
  await expect(submit).toBeEnabled()
  const sent = page.waitForResponse((response) => response.url() === `${api}/api/v3/jobs` && response.request().method() === 'POST')
  await submit.click()
  const response = await sent
  expect(response.status()).toBe(202)
  const job = (await response.json()).data
  expect(job.job_type).toBe('training')
  await expect(page).toHaveURL(new RegExp(`job=${job.id}`))
  await expect.poll(async () => {
    const progress = await request.get(`${api}/api/v3/jobs/${job.id}`, { headers })
    const value = (await progress.json()).data
    expect(value.status).not.toBe('failed')
    return value.completed_units
  }, { timeout: 240_000, intervals: [1000] }).toBe(1)
  await page.reload()
  await expect(page.getByText(`Job: ${job.id}`, { exact: false })).toBeVisible()
  expect(posts).toBe(1)
  const ready = page.waitForResponse((result) => result.url() === `${api}/api/v3/jobs/${job.id}/result` && result.status() === 200)
  writeFileSync(process.env.TRAINING_REAL_RELEASE!, 'continue')
  const resultResponse = await ready
  expect(resultResponse.headers()['cache-control']).toBe('no-store')
  const result = (await resultResponse.json()).data
  expect(result.job_id).toBe(job.id)
  expect(result.dataset_id).toBe(dataset)
  expect(result.health.target).toBe('health_score_true')
  expect(result.rul.target).toBe('rul_hours_true')
  expect(result.rul.unit).toBe('hours')
  const formatted = (value: number) => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 4 }).format(value)
  for (const [role, name] of [['health', 'Saúde'], ['rul', 'Vida útil restante (RUL)']] as const) {
    const region = page.getByRole('region', { name: `Resultados de ${name}`, exact: true })
    await expect(region).toBeVisible()
    const report = result[role]
    expect(report.diagnostics.scatter).toHaveLength(500)
    expect(report.diagnostics.permutation.features).toHaveLength(48)
    expect(report.diagnostics.permutation.repeats).toBe(3)
    await expect(region.getByRole('cell', { name: formatted(report.metrics.validation.candidate.mae), exact: true }).first()).toBeVisible()
    await expect(region.getByRole('cell', { name: formatted(report.metrics.test.candidate.rmse), exact: true }).first()).toBeVisible()
    await expect(region.getByRole('img', { name: new RegExp(`Previsto versus real de ${name.replace(/[()]/g, '\\$&')}`) })).toBeVisible()
    await region.getByText(/^Inspecionar erros em tabela/).click()
    const errors = region.getByRole('region', { name: `Erros de ${name}`, exact: true })
    await expect(errors.locator('tbody tr')).toHaveCount(500)
    await expect(errors.locator('tbody tr').first().locator('td').nth(0)).toHaveText(formatted(report.diagnostics.scatter[0].actual))
    await expect(errors.locator('tbody tr').first().locator('td').nth(3)).toHaveText(formatted(report.diagnostics.scatter[0].error))
  }
  await expect(page.getByText(/Nenhum resultado desta página ativa modelos/i)).toBeVisible()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: test.info().outputPath('training-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 320, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('training-mobile.png'), fullPage: true })
  expect(posts).toBe(1)
  const stranger = await request.post(`${api}/api/v1/auth/login`, { data: {
    email: process.env.TRAINING_REAL_OTHER_EMAIL, password: process.env.TRAINING_REAL_PASSWORD,
  } })
  const otherHeaders = { authorization: `Bearer ${(await stranger.json()).data.token}` }
  expect((await request.get(`${api}/api/v3/jobs/${job.id}/result`, { headers: otherHeaders })).status()).toBe(404)
  const ownList = await request.get(`${api}/api/v3/datasets`, { headers: otherHeaders })
  expect((await ownList.json()).data).toEqual([])
})

test('visualizador não dispara treinamento nem pela API nem pela página', async ({ page, request }) => {
  const session = await login(request, page, process.env.TRAINING_REAL_VIEWER_EMAIL!)
  await page.goto('/training')
  await expect(page.getByText(/apenas para administradores/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Iniciar treinamento', exact: true })).toHaveCount(0)
  const forbidden = await request.post(`${api}/api/v3/jobs`, {
    headers: { authorization: `Bearer ${session.token}` },
    data: { job_type: 'training', dataset_id: process.env.TRAINING_REAL_DATASET },
  })
  expect(forbidden.status()).toBe(403)
})
