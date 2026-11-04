import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { mockDashboardAccount } from './monitoring-api'

const captureDir = '../.impeccable/review/rd-01'

for (const width of [1440, 320]) {
  test(`fundamentos preservam acesso, gestão e apresentação em ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.route('**/api/v1/auth/login', (route) => route.fulfill({
      status: 401, json: { success: false, error: { message: 'Email ou senha inválidos.' } },
    }))
    await page.goto('/login')
    await page.getByLabel('Email').fill('teste@example.com')
    await page.getByLabel('Senha').fill('senha-segura')
    await page.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(page.getByRole('alert')).toHaveText('Email ou senha inválidos.')
    await expect(page.getByLabel('Email')).toHaveValue('teste@example.com')
    await expect(page.getByLabel('Senha')).toHaveValue('senha-segura')
    await page.getByRole('button', { name: 'Criar conta', exact: true }).click()
    await expect(page.getByLabel('Senha')).toHaveAttribute('autocomplete', 'new-password')
    await expect(page.getByLabel('Senha')).toHaveAccessibleDescription(/Use ao menos 8 caracteres/)
    await expect(page.getByRole('alert')).toHaveCount(0)
    await page.getByLabel('Senha').focus()
    await expect(page.getByLabel('Senha')).toHaveCSS('outline-style', 'solid')
    await expect(page.getByLabel('Senha')).toHaveCSS('outline-width', '3px')

    if (process.env.RD01_CAPTURE) {
      await mkdir(captureDir, { recursive: true })
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: `${captureDir}/access-${width}.png`, fullPage: true })
    }
    for (const fontSize of ['100%', '200%']) {
      await page.evaluate((size) => { document.documentElement.style.fontSize = size }, fontSize)
      const submit = page.getByRole('button', { name: 'Criar conta e entrar' })
      await expect(submit).toHaveCSS('font-size', fontSize === '200%' ? '28px' : '14px')
      await page.evaluate(async () => {
        await document.fonts.ready
        // Wait for rem-based layout after the control's enlarged font has been applied.
        await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
      })
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
      await page.getByLabel('Senha').focus()
      await page.keyboard.press('Tab')
      await expect(submit).toBeFocused()
      await expect(submit).toBeInViewport()
      const size = await submit.boundingBox()
      expect(size!.height).toBeGreaterThanOrEqual(44)
    }

    await mockDashboardAccount(page)
    await page.route('**/api/v1/environments/*/rules', (route) => route.fulfill({
      json: { success: true, data: { min_c: 2, max_c: 8, attention_margin_c: 1 } },
    }))
    await page.goto('/manage')
    await expect(page.getByLabel('Mínimo (°C)')).toHaveValue('2')
    await page.getByRole('button', { name: 'Adicionar dispositivo' }).click()
    await expect(page.getByLabel('Identificador MQTT')).toHaveAccessibleDescription(/mesmo identificador configurado no ESP32/)
    await page.getByLabel('Identificador MQTT').focus()
    await expect(page.getByLabel('Identificador MQTT')).toHaveCSS('outline-style', 'solid')
    if (process.env.RD01_CAPTURE) {
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: `${captureDir}/manage-${width}.png`, fullPage: true })
    }
    await page.getByLabel('Mínimo (°C)').fill('10')
    await page.getByRole('button', { name: 'Salvar limites' }).click()
    await expect(page.getByLabel('Mínimo (°C)')).toBeFocused()
    await expect(page.getByLabel('Mínimo (°C)')).toHaveAttribute('aria-invalid', 'true')
    await expect(page.getByLabel('Mínimo (°C)')).toHaveAccessibleDescription('O mínimo deve ser menor que o máximo.')
    for (const fontSize of ['100%', '200%']) {
      await page.evaluate((size) => { document.documentElement.style.fontSize = size }, fontSize)
      const save = page.getByRole('button', { name: 'Salvar limites' })
      await expect(save).toHaveCSS('font-size', fontSize === '200%' ? '28px' : '14px')
      await page.evaluate(async () => {
        await document.fonts.ready
        // Wait for rem-based layout after the control's enlarged font has been applied.
        await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
      })
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
      await page.getByLabel('Mínimo (°C)').focus()
      await page.keyboard.press('Tab')
      await page.keyboard.press('Tab')
      await page.keyboard.press('Tab')
      await expect(save).toBeFocused()
      await expect(save).toBeInViewport()
    }

    await page.goto('/')
    await expect(page.locator('.presentation-theme')).toBeVisible()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    if (process.env.RD01_CAPTURE) {
      for (const image of await page.locator('img').all()) {
        await image.scrollIntoViewIfNeeded()
        await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0)
      }
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: `${captureDir}/presentation-${width}.png`, fullPage: true })
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  })
}
