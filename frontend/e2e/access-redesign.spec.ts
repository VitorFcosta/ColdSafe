import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'

const evidence = new URL('../../.impeccable/review/rd-16/', import.meta.url)
const email = (page: Page) => page.getByLabel('Email', { exact: true })
const password = (page: Page) => page.getByLabel('Senha', { exact: true })
const submit = (page: Page) => page.getByRole('button', { name: 'Entrar', exact: true }).first()
const envelope = (data: unknown) => ({ success: true, data })

async function isolate(page: Page) {
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { success: false } }))
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: envelope({ user_id: 'rd16-user', email: 'rd16@example.invalid', role: 'viewer' }) }))
}
async function fill(page: Page) {
  await email(page).fill('rd16@example.invalid')
  await password(page).fill('password123')
}
async function capture(page: Page, name: string) {
  await mkdir(evidence, { recursive: true })
  await page.evaluate(async () => { window.scrollTo(0, 0); await document.fonts.ready })
  await page.screenshot({ path: new URL(`${name}.png`, evidence).pathname, fullPage: true })
}

for (const scenario of [{ width: 1440, height: 1024, text: 100 }, { width: 390, height: 844, text: 100 }, { width: 320, height: 480, text: 200 }]) {
  test(`M-02 teclado, validação e tela curta ${scenario.width}px texto ${scenario.text}% (API simulada)`, async ({ page, browser }) => {
    await isolate(page)
    await page.setViewportSize(scenario)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/login')
    if (scenario.text === 200) await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    await expect(page.locator('input')).toHaveCount(2)
    await expect(email(page)).toHaveAttribute('maxlength', '254')
    await expect(email(page)).toHaveAttribute('autocomplete', 'username')
    await expect(password(page)).toHaveAttribute('maxlength', '128')
    await expect(password(page)).toHaveAttribute('autocomplete', 'current-password')
    const back = page.getByRole('link', { name: 'Voltar à apresentação', exact: true })
    await back.focus(); await page.keyboard.press('Tab'); await expect(email(page)).toBeFocused()
    await page.keyboard.press('Tab'); await expect(password(page)).toBeFocused()
    await page.keyboard.press('Tab'); await expect(submit(page)).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(email(page)).toBeFocused()
    await expect(email(page)).toHaveAccessibleDescription('Informe um email válido.')
    await email(page).fill('rd16@example.invalid')
    await submit(page).click()
    await expect(password(page)).toBeFocused()
    await expect(password(page)).toHaveAccessibleDescription('Informe sua senha.')
    await password(page).fill('password123')
    const name = scenario.width === 1440 ? 'desktop' : scenario.width === 390 ? 'mobile' : 'mobile-320-text-200'
    await capture(page, name)
    await page.getByRole('button', { name: 'Criar conta', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Criar conta', exact: true })).toBeFocused()
    await expect(password(page)).toHaveAttribute('autocomplete', 'new-password')
    await expect(password(page)).toHaveAccessibleDescription(/72 bytes UTF-8/)
    await password(page).fill('short')
    const create = page.getByRole('button', { name: 'Criar conta e entrar', exact: true })
    await email(page).fill('invalid-email')
    await create.click()
    await expect(email(page)).toBeFocused()
    await expect(email(page)).toHaveAccessibleDescription('Informe um email válido.')
    await expect(password(page)).not.toHaveAttribute('aria-invalid', 'true')
    await expect(password(page)).not.toHaveAccessibleDescription(/Informe um email válido/)
    await email(page).fill('rd16@example.invalid')
    await create.click()
    await expect(password(page)).toBeFocused()
    await expect(password(page)).toHaveAttribute('aria-invalid', 'true')
    await expect(password(page)).toHaveAccessibleDescription(/8 caracteres.*8 caracteres/)
    await password(page).fill('é'.repeat(37))
    await create.click()
    await expect(password(page)).toBeFocused()
    await expect(page.getByRole('alert')).toContainText('Reduza o tamanho')
    await page.getByRole('alert').scrollIntoViewIfNeeded()
    await expect(page.getByRole('alert')).toBeInViewport()
    await password(page).focus(); await page.keyboard.press('Tab')
    await expect(create).toBeFocused(); await expect(create).toBeInViewport()
    await expect(create).toHaveCSS('outline-style', 'solid')
    expect(await create.evaluate(el => getComputedStyle(el).outlineWidth)).not.toBe('0px')
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(scenario.width)
    for (const control of await page.locator('.access-page').locator('input:visible, button:visible, a:visible').all()) {
      expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    await capture(page, `${name}-register-error`)
    const styles = await page.evaluate(() => Object.fromEntries(['.brand', '.return-link', 'h1', '.intro', 'label', 'input', '.hint', '.feedback', '.primary', '.mode-switch', '.session-note'].map(selector => {
      const el = document.querySelector(selector)!, style = getComputedStyle(el)
      let surface: Element | null = el
      while (surface && getComputedStyle(surface).backgroundColor === 'rgba(0, 0, 0, 0)') surface = surface.parentElement
      return [selector, { color: style.color, background: surface ? getComputedStyle(surface).backgroundColor : '', border: style.borderColor, outline: style.outlineColor, fontSize: style.fontSize }]
    })))
    await writeFile(new URL(`${name}.json`, evidence), JSON.stringify({ scenario, browser: browser.version(), styles }, null, 2))
    await password(page).fill('password123')
    await back.click()
    await expect(page).toHaveURL('/')
  })
}

test('cadastro ocupado não duplica envio e retoma destino protegido com query/hash (API simulada)', async ({ page }) => {
  await isolate(page)
  let registrations = 0, logins = 0
  let release!: () => void
  const waiting = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/auth/register', async route => {
    registrations++
    expect(route.request().postDataJSON()).toEqual({ email: 'rd16@example.invalid', password: 'password123' })
    await waiting
    await route.fulfill({ status: 201, json: envelope({ id: 'rd16-user' }) })
  })
  await page.route('**/api/v1/auth/login', route => {
    logins++
    return route.fulfill({ json: envelope({ token: 'rd16-token', expires_at: '2099-01-01T00:00:00Z' }) })
  })
  const destination = '/manage?source=rd16#manage-title'
  await page.goto(destination)
  await expect(page).toHaveURL(url => url.pathname === '/login' && url.searchParams.get('redirect') === destination)
  await page.getByRole('button', { name: 'Criar conta', exact: true }).click()
  await fill(page)
  await page.getByRole('button', { name: 'Criar conta e entrar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Criando conta…' })).toBeDisabled()
  await expect(email(page)).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeDisabled()
  await page.locator('form').evaluate(form => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(registrations).toBe(1); expect(logins).toBe(0)
  await capture(page, 'register-busy')
  release()
  await expect(page).toHaveURL(destination)
  await expect(page.getByRole('heading', { name: 'Ambientes e dispositivos', exact: true })).toBeVisible()
  expect(registrations).toBe(1); expect(logins).toBe(1)
})

test('login diferencia credenciais, indisponibilidade, rede e limite; retry conserva dados (API simulada)', async ({ page }) => {
  await isolate(page)
  let attempt = 0
  await page.route('**/api/v1/auth/login', route => {
    attempt++
    if (attempt === 1) return route.fulfill({ status: 401, body: '' })
    if (attempt === 2) return route.fulfill({ status: 503, contentType: 'text/html', body: '<html>offline</html>' })
    if (attempt === 3) return route.abort('failed')
    if (attempt === 4) return route.fulfill({ status: 429, body: '' })
    return route.fulfill({ json: envelope({ token: 'rd16-token', expires_at: '2099-01-01T00:00:00Z' }) })
  })
  await page.goto(`/login?redirect=${encodeURIComponent('https://evil.invalid')}`)
  await fill(page)
  for (const message of ['Email ou senha inválidos.', 'O serviço de acesso está indisponível.', 'Não foi possível conectar à API.', 'Muitas tentativas de acesso.']) {
    await submit(page).click()
    await expect(page.getByRole('alert')).toContainText(message)
    await expect(email(page)).toHaveValue('rd16@example.invalid')
    await expect(password(page)).toHaveValue('password123')
    await expect(page.locator('form')).toHaveAccessibleDescription(new RegExp(message))
    await expect(submit(page)).toBeEnabled()
    if (attempt === 1) await capture(page, 'login-error')
  }
  await submit(page).click()
  await expect(page).toHaveURL('/dashboard')
  expect(attempt).toBe(5)
})

test('conta existente conserva formulário e permite voltar ao login (API simulada)', async ({ page }) => {
  await isolate(page)
  await page.setViewportSize({ width: 390, height: 360 })
  await page.route('**/api/v1/auth/register', route => route.fulfill({ status: 409, json: { success: false, error: { message: 'Conta já existe.' } } }))
  await page.goto('/login')
  await page.getByRole('button', { name: 'Criar conta', exact: true }).click()
  await fill(page)
  await page.getByRole('button', { name: 'Criar conta e entrar', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Conta já existe.')
  await page.getByRole('alert').scrollIntoViewIfNeeded()
  await expect(page.getByRole('alert')).toBeInViewport()
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Entrar', exact: true })).toBeFocused()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(email(page)).toHaveValue('rd16@example.invalid')
  await expect(password(page)).toHaveAttribute('autocomplete', 'current-password')
})
