import { expect, test } from '@playwright/test'

test('orienta o foco na navegação e preserva acesso e histórico', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
    success: true, data: { user_id: 'test-user', email: 'teste@example.com', role: 'operator' },
  } }))
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: { token: 'test-token', expires_at: '2099-01-01T00:00:00Z' } }),
  }))
  await page.route('**/api/v1/auth/logout', (route) => route.fulfill({ status: 200 }))
  await page.route('**/api/v1/environments', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [{ id: 'lab', name: 'Laboratório' }] }),
  }))
  await page.route('**/api/v1/environments/lab/devices', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: [] }),
  }))
  await page.route('**/api/v1/environments/lab/rules', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ success: true, data: { min_c: 2, max_c: 8, attention_margin_c: 1 } }),
  }))

  await page.goto('/')
  await page.getByRole('link', { name: 'Entrar no painel' }).focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/login\?redirect=/)
  await expect(page).toHaveTitle('Entrar · ColdSafe')
  await expect(page.getByRole('heading', { name: 'Entrar' })).toBeFocused()

  await page.getByLabel('Email').fill('teste@example.com')
  await page.getByLabel('Senha').fill('senha-segura')
  await page.getByLabel('Senha').press('Enter')
  const dashboardTitle = page.getByRole('heading', { name: 'Diagnóstico do ambiente' })
  await expect(page).toHaveURL('/dashboard')
  await expect(dashboardTitle).toBeFocused()
  await expect(page).toHaveTitle('Monitoramento · ColdSafe')
  await expect(page.getByRole('link', { name: 'Monitoramento' })).toHaveAttribute('aria-current', 'page')

  await page.reload()
  const skip = page.getByRole('link', { name: 'Ir para o conteúdo' })
  await skip.focus()
  await expect(skip).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(dashboardTitle).toBeFocused()

  await page.getByRole('link', { name: 'Ambientes e dispositivos' }).focus()
  await page.keyboard.press('Enter')
  const manageTitle = page.getByRole('heading', { name: 'Ambientes e dispositivos' })
  await expect(page).toHaveURL('/manage')
  await expect(manageTitle).toBeFocused()
  await expect(page).toHaveTitle('Ambientes e dispositivos · ColdSafe')
  await expect(page.getByRole('link', { name: 'Ambientes e dispositivos' })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('link', { name: 'Ir para o conteúdo' }).focus()
  await page.keyboard.press('Enter')
  await expect(manageTitle).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440)
  await page.evaluate(() => { document.documentElement.style.zoom = '' })

  await page.getByRole('link', { name: 'Monitoramento' }).focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL('/dashboard')
  await expect(dashboardTitle).toBeFocused()
  await page.goBack()
  await expect(page).toHaveURL('/manage#manage-title')
  await expect(manageTitle).toBeFocused()
  await page.goForward()
  await expect(dashboardTitle).toBeFocused()

  await page.getByRole('button', { name: 'Sair' }).focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL('/login')
  await expect(page.getByRole('heading', { name: 'Entrar' })).toBeFocused()
  await page.goto('/manage')
  await expect(page).toHaveURL(/\/login\?redirect=/)
})
