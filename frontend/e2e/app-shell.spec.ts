import { expect, test, type Page } from '@playwright/test'
import training from '../src/features/training/training.fixture.json' with { type: 'json' }

type Role = 'viewer' | 'operator' | 'admin'
const identity = (role: Role) => ({ success: true, data: { user_id: 'shell-user', email: `${role}@example.invalid`, role } })
const globalNav = (page: Page) => page.getByRole('navigation', { name: 'Navegação principal', exact: true })
const localNav = (page: Page) => page.getByRole('navigation', { name: 'Navegação da área', exact: true })
const menu = (page: Page) => page.getByRole('dialog', { name: 'Menu de navegação', exact: true })

async function account(page: Page, role: Role = 'operator') {
  await page.route('**/api/**', (route) => route.fulfill({ status: 503, json: {
    success: false, error: { message: 'Serviço de ensaio indisponível.' },
  } }))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: identity(role) }))
  await page.route('**/api/v1/environments', (route) => route.fulfill({ json: { success: true, data: [] } }))
  await page.addInitScript(() => sessionStorage.setItem('coldsafe-session', JSON.stringify({
    token: 'shell-token', expires_at: '2099-01-01T00:00:00Z',
  })))
}

for (const role of ['viewer', 'operator', 'admin'] as const) {
  test(`${role}: destinos globais, locais e utilitários respeitam o papel confirmado`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await account(page, role)
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente', exact: true })).toBeVisible()
    await expect(globalNav(page).getByRole('link')).toHaveCount(role === 'admin' ? 4 : 2)
    await expect(globalNav(page).getByRole('link', { name: 'Monitoramento', exact: true })).toHaveAttribute('href', '/dashboard')
    await expect(globalNav(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true })).toHaveAttribute('href', '/manage')
    await expect(globalNav(page).getByRole('link', { name: 'Dados e modelos', exact: true })).toHaveCount(role === 'admin' ? 1 : 0)
    await expect(globalNav(page).getByRole('link', { name: 'Filas e mensagens', exact: true })).toHaveCount(role === 'admin' ? 1 : 0)
    await expect(localNav(page).getByRole('link')).toHaveCount(3)
    await expect(localNav(page).getByRole('link', { name: 'Visão geral', exact: true })).toHaveAttribute('aria-current', 'page')
    await expect(localNav(page).getByRole('link', { name: 'Saúde e previsões', exact: true })).toHaveAttribute('href', '/insights')
    const utilities = page.getByRole('navigation', { name: 'Utilitários', exact: true })
    await expect(utilities.getByRole('link', { name: 'Assistente', exact: true })).toHaveAttribute('href', '/assistant')
    await expect(utilities.getByRole('link', { name: /Documentação da API/ })).toHaveAttribute('target', '_blank')
    await expect(utilities.getByRole('link', { name: /Documentação da API/ })).toContainText('nova aba')
    await expect(utilities.getByRole('link', { name: 'Apresentação do projeto', exact: true })).toHaveAttribute('href', '/')
    await expect(page.getByRole('link', { name: 'ColdSafe', exact: true })).toHaveAttribute('href', '/dashboard')
  })
}

for (const role of ['viewer', 'operator'] as const) {
  for (const path of ['/laboratory', '/training', '/messaging']) {
    test(`${role}: URL direta ${path} mostra restrição sem consultar módulo privado`, async ({ page }) => {
      await account(page, role)
      const privateCalls: string[] = []
      page.on('request', (request) => {
        const pathname = new URL(request.url()).pathname
        if (pathname.startsWith('/api/') && pathname !== '/api/v1/auth/me') privateCalls.push(pathname)
      })
      await page.goto(path)
      await expect(page.getByRole('heading', { name: 'Acesso restrito', exact: true })).toBeVisible()
      await expect(page).toHaveURL(path)
      expect(privateCalls).toEqual([])
      await expect(page.getByRole('button', { name: /Gerar dataset|Iniciar treinamento/ })).toHaveCount(0)
    })
  }
}

test('identidade pendente não monta conteúdo privado; mudar destino mantém a verificação', async ({ page }) => {
  await account(page)
  let release!: () => void
  const held = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/v1/auth/me', async (route) => { await held; await route.fulfill({ json: identity('operator') }) })
  const privateCalls: string[] = []
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/') && path !== '/api/v1/auth/me') privateCalls.push(path)
  })
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Verificando identidade', exact: true })).toBeVisible()
  expect(privateCalls).toEqual([])
  await globalNav(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true }).click()
  await expect(page).toHaveURL('/manage')
  await expect(page.getByRole('heading', { name: 'Verificando identidade', exact: true })).toBeVisible()
  await expect(page.locator('#environments-title')).toHaveCount(0)
  await expect(page.getByText('Modo visualizador:', { exact: false })).toHaveCount(0)
  expect(privateCalls).toEqual([])
  release()
  await expect(page.getByRole('heading', { name: 'Ambientes e dispositivos', exact: true })).toBeFocused()
  await expect.poll(() => privateCalls).toContain('/api/v1/environments')
})

test('falha de identidade após login oferece retry sem repetir credenciais ou consultar dados privados', async ({ page }) => {
  let logins = 0, identities = 0, privateCalls = 0
  await page.route('**/api/v1/auth/login', (route) => {
    logins++
    return route.fulfill({ json: { success: true, data: { token: 'new-shell-token', expires_at: '2099-01-01T00:00:00Z' } } })
  })
  await page.route('**/api/v1/auth/me', (route) => {
    identities++
    return identities === 1 ? route.fulfill({ status: 503, json: { success: false } }) : route.fulfill({ json: identity('operator') })
  })
  await page.route('**/api/v1/environments', (route) => { privateCalls++; return route.fulfill({ json: { success: true, data: [] } }) })
  await page.goto('/login?redirect=%2Fmanage')
  await page.getByLabel('Email', { exact: true }).fill('operator@example.invalid')
  await page.getByLabel('Senha', { exact: true }).fill('senha-segura')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Não foi possível verificar a identidade', exact: true })).toBeVisible()
  expect(privateCalls).toBe(0)
  expect(logins).toBe(1)
  await page.getByRole('button', { name: 'Verificar novamente', exact: true }).click()
  await expect(page).toHaveURL('/manage')
  await expect(page.getByRole('heading', { name: 'Ambientes e dispositivos', exact: true })).toBeFocused()
  expect(logins).toBe(1)
  expect(identities).toBe(2)
})

test('menu modal em 320 px contém foco, fecha por Escape/botão/destino e mantém link de salto', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await account(page, 'admin')
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente', exact: true })).toBeVisible()
  const open = page.getByRole('button', { name: 'Menu', exact: true })
  await open.focus(); await page.keyboard.press('Enter')
  await expect(open).toHaveAttribute('aria-expanded', 'true')
  await expect(menu(page)).toBeVisible()
  const close = menu(page).getByRole('button', { name: 'Fechar menu', exact: true })
  await expect(close).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect.poll(() => menu(page).evaluate((element) => element.contains(document.activeElement))).toBe(true)
  await page.keyboard.press('Tab')
  await expect(close).toBeFocused()
  await page.locator('#dashboard-title').evaluate((element) => element.focus())
  await expect(close).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(menu(page)).not.toBeVisible()
  await expect(open).toBeFocused()
  await open.click(); await close.click()
  await expect(open).toBeFocused()
  await open.click()
  await menu(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true }).click()
  await expect(page.locator('#manage-title')).toBeFocused()
  await expect(menu(page)).not.toBeVisible()
  const skip = page.getByRole('link', { name: 'Ir para o conteúdo', exact: true })
  await skip.focus(); await page.keyboard.press('Enter')
  await expect(page.locator('#manage-title')).toBeFocused()
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
  await open.click()
  await expect(menu(page).getByRole('link', { name: 'Ambientes e dispositivos', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
})

test('entradas específicas preservam dataset/job, recarga e histórico; entrada global vai ao laboratório', async ({ page }) => {
  await account(page, 'admin')
  const trainingUrl = `/training?dataset=${training.dataset_id}&job=${training.job_id}`
  await page.goto(trainingUrl)
  await expect(page.getByRole('heading', { name: 'Treinamento', exact: true })).toBeVisible()
  await expect(page).toHaveURL(trainingUrl)
  await page.reload()
  await expect(page).toHaveURL(trainingUrl)
  await globalNav(page).getByRole('link', { name: 'Dados e modelos', exact: true }).click()
  await expect(page).toHaveURL('/laboratory')
  await expect(localNav(page).getByRole('link', { name: 'Dados sintéticos', exact: true })).toHaveAttribute('aria-current', 'page')
  await page.goBack()
  await expect(page).toHaveURL(trainingUrl)
  await page.goForward()
  await expect(page).toHaveURL('/laboratory')
  await page.goto(`/laboratory?job=${training.job_id}`)
  await page.reload()
  await expect(page).toHaveURL(`/laboratory?job=${training.job_id}`)
})

test('rota desconhecida apresenta recuperação sem inventar destino ou expor conteúdo privado', async ({ page }) => {
  await account(page, 'viewer')
  await page.goto('/rota-que-nao-existe?job=desconhecido')
  await expect(page.getByRole('heading', { name: 'Página não encontrada', exact: true })).toBeVisible()
  await expect(page).toHaveURL('/rota-que-nao-existe?job=desconhecido')
  await expect(page.locator('a[href="/dashboard"]').first()).toBeVisible()
  await expect(page.locator('#dashboard-title')).toHaveCount(0)
})

const pages = [
  ['/', 'presentation-title', 'Da leitura do sensor à compreensão do equipamento.'], ['/login', 'access-title', 'Entrar'], ['/dashboard', 'dashboard-title', 'Diagnóstico do ambiente'],
  ['/insights', 'insights-title', 'Saúde e previsões'], ['/digital-twin', 'digital-twin-title', 'Gêmeo digital'], ['/manage', 'manage-title', 'Ambientes e dispositivos'],
  ['/laboratory', 'laboratory-title', 'Laboratório de Dados'], ['/training', 'training-title', 'Treinamento'], ['/messaging', 'messaging-title', 'Mensageria'], ['/assistant', 'assistant-title', 'Assistente'],
] as const
for (const [path, titleId, title] of pages) {
  test(`smoke da rota ${path} preserva seu conteúdo e uma única navegação compartilhada`, async ({ page }) => {
    if (path !== '/' && path !== '/login') await account(page, 'admin')
    else await page.route('**/api/**', (route) => route.abort())
    await page.goto(path)
    await expect(page.locator(`#${titleId}`)).toBeVisible()
    await expect(page.locator(`#${titleId}`)).toHaveText(title)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    if (path !== '/' && path !== '/login') {
      await expect(globalNav(page)).toHaveCount(1)
      await expect(page.getByRole('button', { name: 'Sair', exact: true })).toHaveCount(1)
    }
  })
}


test('login confirmado com identidade atrasada conserva destino e queries solicitados', async ({ page }) => {
  await page.route('**/api/**', (route) => route.fulfill({ status: 503, json: { success: false } }))
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({ json: { success: true, data: {
    token: 'login-destination-token', expires_at: '2099-01-01T00:00:00Z',
  } } }))
  await page.route('**/api/v1/auth/me', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 100))
    await route.fulfill({ json: identity('admin') })
  })
  const destination = `/training?dataset=${training.dataset_id}&job=${training.job_id}`
  await page.goto(`/login?redirect=${encodeURIComponent(destination)}`)
  await page.getByLabel('Email', { exact: true }).fill('admin@example.invalid')
  await page.getByLabel('Senha', { exact: true }).fill('senha-segura')
  const verified = page.waitForResponse('**/api/v1/auth/me')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await verified
  await page.waitForLoadState('networkidle')
  await expect(page).toHaveURL(destination)
  await expect(page.locator('#training-title')).toHaveText('Treinamento')
  await expect(page).toHaveTitle('Treinamento de modelos · ColdSafe')
})
