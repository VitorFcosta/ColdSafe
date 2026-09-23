import { expect, test } from '@playwright/test'

import { mockMonitoringApi } from './monitoring-api'

test('apresenta o projeto sem depender da API ou iniciar o monitoramento', async ({ page }) => {
  const monitoringRequests: string[] = []
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/')) {
      monitoringRequests.push(request.url())
    }
  })
  await page.route('**/api/v1/**', (route) => route.abort())
  await page.clock.install()

  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Ver código', exact: true }).first()).toHaveAttribute(
    'href', 'https://github.com/VitorFcosta/ColdSafe',
  )
  await page.clock.runFor(10_100)

  expect(monitoringRequests).toEqual([])
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('abre a demonstração por teclado e oferece vídeo simulado com controles nativos', async ({ page }) => {
  await page.goto('/')
  const demoLink = page.getByRole('link', { name: 'Ver demonstração', exact: true }).first()
  await expect(demoLink).toHaveAttribute('href', '#demonstracao')
  await demoLink.focus()
  await expect(demoLink).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#demonstracao$/)

  const demonstration = page.locator('#demonstracao')
  await expect(demonstration).toContainText(/simulad[ao]/i)
  const video = demonstration.locator('video')
  await expect(video).toBeVisible()
  await expect(video).toHaveJSProperty('controls', true)
  await expect(video).toHaveJSProperty('autoplay', false)
  await expect(video).toHaveJSProperty('paused', true)
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.readyState)).toBeGreaterThanOrEqual(1)
  const duration = await video.evaluate((element: HTMLVideoElement) => element.duration)
  expect(duration).toBeGreaterThanOrEqual(60)
  expect(duration).toBeLessThanOrEqual(90)

  const images = page.locator('img')
  expect(await images.count()).toBeGreaterThan(0)
  for (const image of await images.all()) {
    await image.scrollIntoViewIfNeeded()
    await expect(image).toHaveAttribute('alt', /\S/)
    await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0)
  }
})

for (const width of [320, 375, 768, 1440]) {
  test(`mantém apresentação e dashboard legíveis sem rolagem horizontal em ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await mockMonitoringApi(page, { status: 'normal' })

    for (const route of ['/', '/dashboard']) {
      await page.goto(route)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      if (route === '/') {
        await expect(page.getByRole('link', { name: 'Ver demonstração', exact: true }).first()).toBeVisible()
        await page.locator('#demonstracao').scrollIntoViewIfNeeded()
        await expect(page.locator('#demonstracao video')).toBeVisible()
      } else {
        await expect(page.getByText('Normal', { exact: true })).toBeVisible()
        await expect(page.getByRole('button', { name: '24h', exact: true })).toBeVisible()
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    }
  })
}

test('redução de movimento deixa seções imediatamente visíveis e mantém foco perceptível', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  for (const section of await page.locator('.reveal').all()) {
    await expect(section).toHaveCSS('opacity', '1')
    await expect(section).toHaveCSS('transform', 'none')
  }
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Ir para o conteúdo' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeVisible()
  expect(await skip.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe('none')
})

test('ampliação de 200% preserva conteúdo e controles nas duas rotas', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockMonitoringApi(page, { status: 'normal' })
  for (const route of ['/', '/dashboard']) {
    await page.goto(route)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440)
    const control = route === '/' ? page.getByRole('link', { name: 'Ver demonstração', exact: true }) : page.getByRole('button', { name: '24h', exact: true })
    await control.focus()
    await expect(control).toBeFocused()
    await expect(control).toBeVisible()
  }
})
