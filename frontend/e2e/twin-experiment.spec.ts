import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'

const url = '/experiments/rd02/'
const components = (page: import('@playwright/test').Page) => page.getByRole('region', { name: 'Componentes', exact: true })
const snapshot = (page: import('@playwright/test').Page) => page.evaluate(() => (window as any).rd02.snapshot())

for (const width of [1440, 320]) {
  test(`experimento 3D seleciona nove IDs por raycast/lista e conserva pausa em ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const requests: string[] = []
    page.on('request', (request) => { if (request.url().includes('/api/')) requests.push(request.url()) })
    await page.goto(url)
    const list = components(page)
    await expect(list.getByRole('button')).toHaveCount(9)
    await expect(page.locator('canvas')).toBeVisible()
    await page.getByRole('button', { name: 'Pausar animação', exact: true }).click()
    const points = await page.evaluate(() => (window as any).rd02.projection())
    for (const point of points) {
      await page.locator('canvas').click({ position: { x: point.x, y: point.y } })
      await expect(page.locator('.inspector')).toHaveAttribute('data-selected-id', point.id)
      await expect(list.locator('[aria-pressed=true]')).toHaveCount(1)
    }
    const first = list.getByRole('button').first()
    await first.focus()
    await page.keyboard.press('Enter')
    await expect(first).toHaveAttribute('aria-pressed', 'true')
    await expect(first).toHaveCSS('outline-style', 'solid')
    await expect(first).toBeFocused()
    await page.getByRole('combobox', { name: 'Cenário controlado' }).selectOption('changed')
    await expect(first).toContainText('7,5 °C')
    expect((await snapshot(page)).paused).toBe(true)
    expect((await snapshot(page)).animating).toBe(false)
    const renders = await page.evaluate(() => (window as any).rd02.probe.snapshot().totalRenders)
    await page.waitForTimeout(250)
    expect(await page.evaluate(() => (window as any).rd02.probe.snapshot().totalRenders)).toBe(renders)
    if (process.env.RD02_CAPTURE) {
      await mkdir('../.impeccable/review/rd-02', { recursive: true })
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: `../.impeccable/review/rd-02/candidate-${width}.png`, fullPage: true })
    }
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    await page.getByRole('button', { name: 'Retomar animação' }).focus()
    await expect(page.getByRole('button', { name: 'Retomar animação' })).toBeInViewport()
    expect(requests).toEqual([])
  })
}

test('stale, zero, movimento reduzido e contexto WebGL perdido conservam lista e seleção', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto(url)
  await expect(page.locator('#twin-animation-reason')).toContainText('Movimento reduzido')
  expect((await snapshot(page)).animating).toBe(false)
  await page.getByRole('combobox', { name: 'Cenário controlado' }).selectOption('zero')
  await expect(components(page).getByRole('button').first()).toContainText('0 °C')
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  expect((await snapshot(page)).animating).toBe(false)
  await page.getByRole('combobox', { name: 'Cenário controlado' }).selectOption('active')
  await expect.poll(async () => (await snapshot(page)).animating).toBe(true)
  await page.getByRole('combobox', { name: 'Cenário controlado' }).selectOption('stale')
  await expect(page.locator('#twin-animation-reason')).toContainText('sem telemetria atual')
  const frozen = await snapshot(page)
  await page.waitForTimeout(100)
  expect((await snapshot(page)).angle).toBe(frozen.angle)
  await page.evaluate(() => document.querySelector('canvas')!.getContext('webgl2')!.getExtension('WEBGL_lose_context')!.loseContext())
  await expect(page.locator('#twin-animation-reason')).toContainText('3D indisponível')
  const buttons = components(page).getByRole('button')
  await expect(buttons).toHaveCount(9)
  await buttons.nth(6).click()
  await expect(page.locator('.inspector')).toContainText('LED')
  await expect(page.locator('.inspector')).toContainText('Sem dados atuais')
})

test('falha ao criar WebGL preserva inspeção por teclado', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (...args: Parameters<typeof original>) {
      return String(args[0]).startsWith('webgl') ? null : original.apply(this, args)
    } as typeof original
  })
  await page.goto(url)
  await expect(page.locator('#twin-animation-reason')).toContainText('3D indisponível')
  const led = components(page).getByRole('button', { name: /^LED/ })
  await led.focus(); await page.keyboard.press('Enter')
  await expect(page.locator('.inspector')).toContainText('LED')
  await expect(led).toBeFocused()
})
