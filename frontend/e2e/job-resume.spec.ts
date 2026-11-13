import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import fixture from '../src/features/training/training.fixture.json' with { type: 'json' }

const generationId = '00000000-0000-4000-8000-000000000101'
const trainingId = '00000000-0000-4000-8000-000000000102'
const datasetId = fixture.dataset_id
const otherDatasetId = '00000000-0000-4000-8000-000000000103'
const ownerId = fixture.job_id
const timestamp = '2026-10-17T12:00:00Z'
const config = { job_type: 'generation', total_units: 1000000, seed: 42, environment_id: null, equipment_count: 100, days: 30,
  sensor_types: ['ambient_temperature_c', 'humidity_percent', 'light_percent', 'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c'],
  failure_fraction: .6, failure_modes: ['bearing_wear', 'imbalance'], operating_modes: ['normal', 'heavy', 'cycling'], noise_scale: 1, missing_rate: .01, outlier_rate: .002 }
const known = { generation: { jobId: generationId }, training: { jobId: trainingId, datasetId } }
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
const localNav = (page: Page) => page.getByRole('navigation', { name: 'Navegação da área', exact: true })
const resume = (page: Page) => page.getByLabel('Retomar trabalhos conhecidos', { exact: true })
const generationLink = (page: Page) => page.getByRole('link', { name: 'Retomar geração', exact: true })
const trainingLink = (page: Page) => page.getByRole('link', { name: 'Retomar treinamento', exact: true })
const evidence = (name: string) => new URL(`../../.impeccable/review/ux-07/retomada-${name}`, import.meta.url)

function job(kind: 'generation' | 'training') {
  const generation = kind === 'generation'
  return { id: generation ? generationId : trainingId, owner_user_id: ownerId, job_type: kind,
    status: 'running', completed_units: 1, total_units: generation ? 1000000 : 2,
    result_id: null, dataset_id: generation ? null : datasetId, environment_id: null, error_code: null,
    config: generation ? config : { job_type: 'training', dataset_id: datasetId, environment_id: null }, created_at: timestamp, updated_at: timestamp }
}

async function mockResumeApi(page: Page, options: { knownJobs?: unknown; role?: string; expired?: boolean } = {}) {
  const state = { role: options.role ?? 'admin', generationStatus: 200, trainingStatus: 200, postStatus: 202,
    generationPosts: 0, trainingPosts: 0, otherWrites: 0, identityGets: 0, privateRequests: 0, jobGets: [] as string[], datasetGets: [] as string[], resultGets: 0 }
  await page.addInitScript(({ knownJobs, expired }) => {
    if (sessionStorage.getItem('job-resume-initialized')) return
    sessionStorage.setItem('job-resume-initialized', 'true')
    sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'resume-account', expires_at: expired ? '2000-01-01T00:00:00Z' : '2099-01-01T00:00:00Z',
      ...(knownJobs === undefined ? {} : { known_jobs: knownJobs }) }))
  }, options)
  await page.route('**/api/**', (route) => route.fulfill({ status: 503, json: { success: false, error: { message: 'Serviço de ensaio indisponível.' } } }))
  await page.route('**/api/v1/auth/me', (route) => {
    state.identityGets++
    const other = route.request().headers().authorization === 'Bearer other-account'
    return route.fulfill({ json: { success: true, data: { user_id: other ? otherDatasetId : ownerId, email: other ? 'other@example.invalid' : 'admin@example.invalid', role: state.role } } })
  })
  await page.route('**/api/v1/auth/logout', (route) => route.fulfill({ status: 200 }))
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({ json: { success: true, data: { token: 'other-account', expires_at: '2099-01-01T00:00:00Z' } } }))
  await page.route('**/api/v3/**', (route) => {
    state.privateRequests++
    expect(route.request().headers().authorization).toMatch(/^Bearer (resume-account|other-account)$/)
    const url = new URL(route.request().url()), method = route.request().method()
    if (method === 'POST' && url.pathname === '/api/v3/jobs') {
      const generation = route.request().postDataJSON().job_type === 'generation'
      if (generation) state.generationPosts++; else state.trainingPosts++
      if (state.postStatus !== 202) return route.fulfill({ status: state.postStatus, json: { success: false } })
      return route.fulfill({ status: 202, json: envelope({ ...job(generation ? 'generation' : 'training'), status: 'queued', completed_units: 0 }) })
    }
    if (method !== 'GET') { state.otherWrites++; return route.fulfill({ status: 405 }) }
    if (url.pathname === '/api/v3/datasets') return route.fulfill({ json: envelope([]) })
    if (url.pathname.startsWith('/api/v3/datasets/')) {
      const id = url.pathname.split('/').at(-1)!
      state.datasetGets.push(id)
      return route.fulfill({ json: envelope({ id, owner_user_id: ownerId, generation_job_id: generationId,
        created_at: timestamp, row_count: 1000000, config, storage_version: 'offline-numpy-v1',
        units: Object.fromEntries(config.sensor_types.map((key) => [key, 'unit'])), quality: {
          missing_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, 10])),
          range_by_sensor: Object.fromEntries(config.sensor_types.map((key) => [key, { min: 0, max: 100 }])),
          rul_observed_rows: 600000, rul_censored_rows: 400000 } }) })
    }
    if (url.pathname.endsWith('/result')) { state.resultGets++; return route.fulfill({ json: envelope(fixture) }) }
    if (url.pathname.startsWith('/api/v3/jobs/')) {
      const id = url.pathname.split('/').at(-1)!
      state.jobGets.push(id)
      const generation = id === generationId, status = generation ? state.generationStatus : state.trainingStatus
      if (status !== 200) return route.fulfill({ status, json: { success: false, error: { message: 'Private owner details must stay hidden.' } } })
      return route.fulfill({ json: envelope(job(generation ? 'generation' : 'training')) })
    }
    return route.fulfill({ status: 404, json: { success: false } })
  })
  return state
}

async function storedJobs(page: Page) {
  return page.evaluate(() => JSON.parse(sessionStorage.getItem('coldsafe-session') ?? 'null')?.known_jobs ?? {})
}

test('criação confirmada registra referências mínimas nas duas vistas; retorno e recarga não reenviam', async ({ page }) => {
  const state = await mockResumeApi(page)
  await page.goto('/laboratory')
  await page.getByRole('button', { name: 'Gerar dados de teste', exact: true }).click()
  await expect(page).toHaveURL(`/laboratory?job=${generationId}`)
  await expect(generationLink(page)).toBeVisible()
  expect(await storedJobs(page)).toEqual({ generation: known.generation })
  await localNav(page).getByRole('link', { name: 'Treinamento de modelos', exact: true }).click()
  await expect(generationLink(page)).toBeVisible()
  await page.goto(`/training?dataset=${datasetId}`)
  await expect(page.getByRole('button', { name: 'Iniciar treinamento', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Iniciar treinamento', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`job=${trainingId}`))
  await expect(trainingLink(page)).toBeVisible()
  expect(await storedJobs(page)).toEqual(known)
  await localNav(page).getByRole('link', { name: 'Dados sintéticos', exact: true }).click()
  await expect(generationLink(page)).toHaveAttribute('href', `/laboratory?job=${generationId}`)
  const destination = new URL((await trainingLink(page).getAttribute('href'))!, page.url())
  expect(destination.pathname).toBe('/training')
  expect(Object.fromEntries(destination.searchParams)).toEqual({ job: trainingId, dataset: datasetId })
  await trainingLink(page).click()
  await expect(page.getByRole('heading', { name: 'Acompanhamento do treinamento', exact: true })).toBeVisible()
  await page.reload()
  await expect(trainingLink(page)).toBeVisible()
  expect(state.generationPosts).toBe(1); expect(state.trainingPosts).toBe(1); expect(state.otherWrites).toBe(0)
})

test('GET direto conserva job/dataset/hash, registra conhecimento e consulta dataset fora da lista', async ({ page }) => {
  const state = await mockResumeApi(page)
  await page.goto(`/laboratory?job=${generationId}&source=manual#progresso`)
  await expect(generationLink(page)).toBeVisible()
  await expect(page).toHaveURL(`/laboratory?job=${generationId}&source=manual#progresso`)
  await page.goto(`/training?dataset=${datasetId}&job=${trainingId}&source=manual#resultado`)
  await expect(trainingLink(page)).toBeVisible()
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue(datasetId)
  const setup = page.getByRole('region', { name: 'Selecionar dataset concluído', exact: true })
  await expect(setup.locator('option:checked')).toHaveText(/^Dataset de /)
  await setup.getByText('Configuração do dataset', { exact: true }).click()
  await expect(setup.getByText(`Dataset: ${datasetId}`, { exact: false })).toBeVisible()
  await expect(page).toHaveURL(`/training?dataset=${datasetId}&job=${trainingId}&source=manual#resultado`)
  expect(await storedJobs(page)).toEqual(known)
  expect(state.datasetGets).toContain(datasetId)
  expect(state.generationPosts + state.trainingPosts).toBe(0)
})

test('job de treino sem dataset na URL recupera associação pelo GET, sem reescrever o endereço', async ({ page }) => {
  const state = await mockResumeApi(page)
  await page.goto(`/training?job=${trainingId}#resultado`)
  await expect(trainingLink(page)).toBeVisible()
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue(datasetId)
  await expect(page).toHaveURL(`/training?job=${trainingId}#resultado`)
  expect(await storedJobs(page)).toEqual({ training: known.training })
  expect(state.trainingPosts).toBe(0)
})

test('job e dataset incompatíveis não são associados nem registrados', async ({ page }) => {
  const state = await mockResumeApi(page)
  await page.goto(`/training?job=${trainingId}&dataset=${otherDatasetId}`)
  await expect(page.getByRole('alert')).toContainText(/indisponível|incompatível|correspond|diverg/i)
  await expect(page.getByRole('heading', { name: 'Acompanhamento do treinamento', exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Resultado do pacote', exact: true })).toHaveCount(0)
  expect(state.datasetGets).not.toContain(otherDatasetId)
  expect(state.resultGets).toBe(0)
  expect(await storedJobs(page)).toEqual({})
  expect(state.trainingPosts).toBe(0)
})

for (const target of ['/laboratory?job=invalid', `/training?job=${trainingId}&dataset=invalid`, `/training?job=${trainingId}&job=${generationId}`]) {
  test(`UUID inválido não consulta recursos: ${target}`, async ({ page }) => {
    const state = await mockResumeApi(page)
    await page.goto(target)
    await expect(page.getByRole('alert')).toContainText(/inválid/i)
    expect(state.jobGets).toEqual([]); expect(state.datasetGets).toEqual([])
    expect(state.generationPosts + state.trainingPosts).toBe(0)
  })
}

test('referência malformada é removida com explicação, preservando o outro tipo válido', async ({ page }) => {
  const state = await mockResumeApi(page, { knownJobs: { generation: { jobId: 'https://evil.invalid/private' }, training: known.training } })
  await page.goto('/laboratory')
  await expect(generationLink(page)).toHaveCount(0)
  await expect(trainingLink(page)).toBeVisible()
  await expect(resume(page)).toContainText(/referência/i)
  expect(await storedJobs(page)).toEqual({ training: known.training })
  expect(state.jobGets).toEqual([])
})

for (const kind of ['generation', 'training'] as const) for (const status of [403, 404]) {
  test(`${kind} ${status} remove só a referência consultada e não repete consulta negada`, async ({ page }) => {
    const state = await mockResumeApi(page, { knownJobs: known })
    if (kind === 'generation') state.generationStatus = status; else state.trainingStatus = status
    await page.goto(kind === 'generation' ? `/laboratory?job=${generationId}` : `/training?job=${trainingId}&dataset=${datasetId}`)
    const remaining = kind === 'generation' ? { training: known.training } : { generation: known.generation }
    await expect.poll(() => storedJobs(page)).toEqual(remaining)
    await expect(page.getByRole('alert')).toContainText(/indisponível|acesso|referência/i)
    await expect(page.getByText('Private owner details must stay hidden.', { exact: true })).toHaveCount(0)
    await page.waitForTimeout(1700)
    expect(state.jobGets).toEqual([kind === 'generation' ? generationId : trainingId])
    expect(state.identityGets).toBe(1)
    expect(state.generationPosts + state.trainingPosts).toBe(0)
  })
}

for (const kind of ['generation', 'training'] as const) test(`${kind} 503 conserva referência; retry usa GET`, async ({ page }) => {
  const state = await mockResumeApi(page, { knownJobs: known })
  if (kind === 'generation') state.generationStatus = 503; else state.trainingStatus = 503
  await page.goto(kind === 'generation' ? `/laboratory?job=${generationId}` : `/training?job=${trainingId}&dataset=${datasetId}`)
  const retry = page.getByRole('button', { name: 'Atualizar acompanhamento', exact: true })
  await expect(retry).toBeVisible()
  expect(await storedJobs(page)).toEqual(known)
  if (kind === 'generation') state.generationStatus = 200; else state.trainingStatus = 200
  await retry.click()
  await expect(page.getByRole('heading', { name: kind === 'generation' ? 'Acompanhamento da geração' : 'Acompanhamento do treinamento', exact: true })).toBeVisible()
  expect(state.generationPosts + state.trainingPosts).toBe(0)
  expect(await storedJobs(page)).toEqual(known)
})

test('envio incerto sem ID não inventa retomada nem repete geração ao retornar', async ({ page }) => {
  const state = await mockResumeApi(page); state.postStatus = 503
  await page.goto('/laboratory')
  await page.getByRole('button', { name: 'Gerar dados de teste', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('O job pode ter sido criado')
  await expect(generationLink(page)).toHaveCount(0)
  expect(await storedJobs(page)).toEqual({})
  await localNav(page).getByRole('link', { name: 'Treinamento de modelos', exact: true }).click()
  await localNav(page).getByRole('link', { name: 'Dados sintéticos', exact: true }).click()
  await page.reload()
  await expect(generationLink(page)).toHaveCount(0)
  expect(state.generationPosts).toBe(1)
})

test('logout e nova conta limpam referências privadas da aba', async ({ page }) => {
  const state = await mockResumeApi(page, { knownJobs: known })
  await page.goto('/laboratory')
  await expect(trainingLink(page)).toBeVisible()
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  expect(await page.evaluate(() => sessionStorage.getItem('coldsafe-session'))).toBeNull()
  await page.getByLabel('Email', { exact: true }).fill('other@example.invalid')
  await page.getByLabel('Senha', { exact: true }).fill('password123')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByText('other@example.invalid', { exact: true })).toBeVisible()
  await page.goto('/laboratory')
  await expect(page.getByRole('heading', { name: 'Dados sintéticos', exact: true })).toBeVisible()
  await expect(trainingLink(page)).toHaveCount(0); await expect(generationLink(page)).toHaveCount(0)
  expect(await storedJobs(page)).toEqual({})
  expect(state.jobGets).toEqual([])
})

test('resposta antiga após logout não registra trabalho na nova conta', async ({ page }) => {
  await mockResumeApi(page, { knownJobs: known })
  let release!: () => void, completed!: () => void, requests = 0
  const waiting = new Promise<void>((resolve) => { release = resolve })
  const finished = new Promise<void>((resolve) => { completed = resolve })
  await page.route(`**/api/v3/jobs/${generationId}`, async (route) => {
    requests++; await waiting
    try { await route.fulfill({ json: envelope(job('generation')) }) }
    finally { completed() }
  })
  await page.goto(`/laboratory?job=${generationId}`)
  await expect.poll(() => requests).toBe(1)
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel('Email', { exact: true }).fill('other@example.invalid')
  await page.getByLabel('Senha', { exact: true }).fill('password123')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByText('other@example.invalid', { exact: true })).toBeVisible()
  await page.goto('/laboratory')
  release(); await finished
  await expect(page.getByRole('heading', { name: 'Dados sintéticos', exact: true })).toBeVisible()
  await expect(generationLink(page)).toHaveCount(0); await expect(trainingLink(page)).toHaveCount(0)
  expect(await storedJobs(page)).toEqual({})
})

test('aba independente não recebe referências da outra aba; sessão expirada não as restaura', async ({ page, context }) => {
  await mockResumeApi(page, { knownJobs: known })
  await page.goto('/laboratory'); await expect(trainingLink(page)).toBeVisible()
  const other = await context.newPage()
  try {
    await mockResumeApi(other)
    await other.goto('/laboratory')
    await expect(other.getByRole('heading', { name: 'Dados sintéticos', exact: true })).toBeVisible()
    await expect(trainingLink(other)).toHaveCount(0)
    expect(await storedJobs(other)).toEqual({})
    await other.evaluate(() => {
      const stored = JSON.parse(sessionStorage.getItem('coldsafe-session')!)
      sessionStorage.setItem('coldsafe-session', JSON.stringify({ ...stored, expires_at: '2000-01-01T00:00:00Z', known_jobs: { generation: { jobId: '00000000-0000-4000-8000-000000000101' } } }))
    })
    await other.reload(); await expect(other).toHaveURL(/\/login/)
    expect(await other.evaluate(() => sessionStorage.getItem('coldsafe-session'))).toBeNull()
  } finally { await other.close() }
})

for (const role of ['viewer', 'operator']) test(`${role} não recebe ações administrativas de retomada`, async ({ page }) => {
  const state = await mockResumeApi(page, { knownJobs: known, role })
  await page.goto('/training')
  await expect(page.getByRole('heading', { name: 'Acesso restrito', exact: true })).toBeVisible()
  await expect(trainingLink(page)).toHaveCount(0); await expect(generationLink(page)).toHaveCount(0)
  expect(state.jobGets).toEqual([]); expect(state.datasetGets).toEqual([])
  expect(state.privateRequests).toBe(0)
  expect(state.generationPosts + state.trainingPosts).toBe(0)
})

test('retomar geração respeita rascunho de dataset na outra vista', async ({ page }) => {
  const state = await mockResumeApi(page, { knownJobs: { generation: known.generation } })
  await page.goto(`/training?dataset=${datasetId}`)
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue(datasetId)
  await page.getByLabel('Dataset', { exact: true }).selectOption('')
  await generationLink(page).click()
  const decision = page.getByRole('dialog', { name: 'Descartar alterações?', exact: true })
  await expect(decision).toBeVisible()
  await decision.getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(page).toHaveURL(`/training?dataset=${datasetId}`)
  await expect(page.getByLabel('Dataset', { exact: true })).toHaveValue('')
  await generationLink(page).click()
  await decision.getByRole('button', { name: 'Descartar alterações', exact: true }).click()
  await expect(page).toHaveURL(`/laboratory?job=${generationId}`)
  await expect(generationLink(page)).toBeVisible()
  expect(state.generationPosts + state.trainingPosts).toBe(0)
})

for (const width of [1440, 320]) test(`retomada ${width}px: foco, texto ampliado e reflow`, async ({ page }) => {
  await page.setViewportSize({ width, height: width === 320 ? 740 : 1000 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockResumeApi(page, { knownJobs: known })
  await page.goto('/laboratory')
  await expect(generationLink(page)).toBeVisible(); await expect(trainingLink(page)).toBeVisible()
  await generationLink(page).focus()
  await expect(generationLink(page)).toBeFocused()
  await mkdir(new URL('.', evidence('desktop.png')), { recursive: true })
  if (width === 320) {
    await page.screenshot({ path: evidence('mobile-320.png').pathname, fullPage: false })
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  }
  await resume(page).scrollIntoViewIfNeeded()
  await page.screenshot({ path: evidence(width === 320 ? 'mobile-320-200.png' : 'desktop.png').pathname, fullPage: false })
  const measured = await resume(page).evaluate((node) => {
    function background(element: Element | null): string {
      if (!element) return 'rgb(255, 255, 255)'
      const color = getComputedStyle(element).backgroundColor
      return color === 'rgba(0, 0, 0, 0)' || color === 'transparent' ? background(element.parentElement) : color
    }
    const link = node.querySelector('a')!, style = getComputedStyle(link)
    return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      panelWidth: node.getBoundingClientRect().width, panelScrollWidth: node.scrollWidth, panelClientWidth: node.clientWidth,
      link: { color: style.color, background: background(link), outlineColor: style.outlineColor, outlineWidth: style.outlineWidth, fontSize: style.fontSize },
      overflow: Array.from(document.querySelectorAll('body *')).map((element) => ({ tag: element.tagName, right: element.getBoundingClientRect().right })).filter((element) => element.right > innerWidth + 1) }
  })
  await writeFile(evidence(`${width === 320 ? 'mobile' : 'desktop'}-layout.json`), JSON.stringify(measured, null, 2))
  expect(measured.scrollWidth).toBeLessThanOrEqual(measured.width)
  expect(measured.panelScrollWidth).toBeLessThanOrEqual(measured.panelClientWidth)
  await expect(generationLink(page)).toBeFocused()
  await page.keyboard.press('Tab'); await expect(trainingLink(page)).toBeFocused()
})
