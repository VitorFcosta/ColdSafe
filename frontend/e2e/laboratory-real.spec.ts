import { writeFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const api = process.env.LAB_REAL_API_URL ?? ''
test.skip(!process.env.LAB_REAL_URL || !api || !process.env.LAB_REAL_PASSWORD,
  'Run only through the disposable B2-19 integration harness')

test('admin gera um milhão, recarrega, identifica qualidade/autor e vê falha parcial', async ({ page, request }) => {
  const login = await request.post(`${api}/api/v1/auth/login`, { data: {
    email: process.env.LAB_REAL_EMAIL, password: process.env.LAB_REAL_PASSWORD,
  } })
  expect(login.status()).toBe(200)
  const session = (await login.json()).data
  await page.addInitScript((session) => {
    sessionStorage.setItem('coldsafe-session', JSON.stringify(session))
  }, session)
  let posts = 0
  const liveCalls: string[] = []
  page.on('request', (call) => {
    if (call.url() === `${api}/api/v3/jobs` && call.method() === 'POST') posts++
    if (/telemetry|monitoring|history/.test(call.url()) && call.url().startsWith(api)) liveCalls.push(call.url())
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/laboratory')
  await expect(page.getByRole('heading', { name: 'Laboratório de Dados', exact: true })).toBeVisible()
  await page.getByLabel('Linhas', { exact: true }).fill('2000001')
  await page.getByRole('button', { name: 'Gerar dataset', exact: true }).click()
  expect(posts).toBe(0)
  await page.getByLabel('Linhas', { exact: true }).fill('1000000')
  const submitted = page.waitForResponse((r) => r.url() === `${api}/api/v3/jobs` && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Gerar dataset', exact: true }).click()
  const response = await submitted
  expect(response.status()).toBe(202)
  const job = (await response.json()).data
  await expect(page).toHaveURL(new RegExp(`job=${job.id}`))
  await expect.poll(async () => {
    const r = await request.get(`${api}/api/v3/jobs/${job.id}`, { headers: { authorization: `Bearer ${session.token}` } })
    return (await r.json()).data.completed_units
  }).toBe(50_000)
  await page.reload()
  await expect(page.getByText(job.id, { exact: false }).first()).toBeVisible()
  expect(posts).toBe(1)
  const summaryResponse = page.waitForResponse((r) => /\/api\/v3\/datasets\/[^/]+$/.test(r.url()) && r.status() === 200)
  writeFileSync(process.env.LAB_REAL_RELEASE!, 'continue')
  const dataset = (await (await summaryResponse).json()).data
  expect(dataset.row_count).toBe(1_000_000)
  expect(dataset.config.seed).toBe(42)
  expect(dataset.owner_user_id).toBe(process.env.LAB_REAL_OWNER)
  expect(dataset.generation_job_id).toBe(job.id)
  expect(Object.values(dataset.quality.missing_by_sensor).some((count) => Number(count) > 0)).toBe(true)
  expect(dataset.quality.rul_censored_rows).toBeGreaterThan(0)
  await expect(page.getByText(dataset.id, { exact: false }).first()).toBeVisible()
  await expect(page.getByText(process.env.LAB_REAL_OWNER!, { exact: false }).first()).toBeVisible()
  const sampleResponse = page.waitForResponse((r) => r.url() === `${api}/api/v3/datasets/${dataset.id}/sample`)
  await page.getByRole('button', { name: 'Ver amostra', exact: true }).click()
  const sample = (await (await sampleResponse).json()).data
  expect(sample.rows).toHaveLength(10)
  expect(sample.rows[0]).toHaveProperty('rul_observed')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(liveCalls).toEqual([])
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: test.info().outputPath('laboratory-dataset.png'), fullPage: true })

  const stranger = await request.post(`${api}/api/v1/auth/login`, { data: {
    email: process.env.LAB_REAL_OTHER_EMAIL, password: process.env.LAB_REAL_PASSWORD,
  } })
  const otherToken = (await stranger.json()).data.token
  for (const suffix of ['', '/sample']) {
    const denied = await request.get(`${api}/api/v3/datasets/${dataset.id}${suffix}`,
      { headers: { authorization: `Bearer ${otherToken}` } })
    expect(denied.status()).toBe(404)
    expect(await denied.text()).not.toContain(dataset.id)
  }
  const invalid = await request.post(`${api}/api/v3/jobs`, { headers: { authorization: `Bearer ${session.token}` },
    data: { job_type: 'generation', total_units: 2_000_001 } })
  expect(invalid.status()).toBe(422)
  await page.getByLabel('Seed', { exact: true }).fill('43')
  const failedSubmit = page.waitForResponse((r) => r.url() === `${api}/api/v3/jobs` && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Gerar dataset', exact: true }).click()
  const failedJob = (await (await failedSubmit).json()).data
  await expect.poll(async () => {
    const r = await request.get(`${api}/api/v3/jobs/${failedJob.id}`, { headers: { authorization: `Bearer ${session.token}` } })
    return (await r.json()).data.status
  }).toBe('failed')
  await expect(page.getByText(/GENERATION_FAILED/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ver amostra', exact: true })).toHaveCount(0)
  expect(posts).toBe(2)
})
