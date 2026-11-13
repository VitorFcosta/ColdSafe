import { expect, test } from '@playwright/test'

import { mockMonitoringApi } from './monitoring-api'

test('apresenta o projeto sem depender da API ou iniciar o monitoramento', async ({ page }) => {
  const monitoringRequests: string[] = []
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) {
      monitoringRequests.push(request.url())
    }
  })
  page.on('websocket', (socket) => {
    if (new URL(socket.url()).pathname.startsWith('/api/')) {
      monitoringRequests.push(socket.url())
    }
  })
  await page.route('**/api/**', (route) => route.abort())
  await page.clock.install()

  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByRole('link', { name: 'GitHub', exact: true })).toHaveAttribute(
    'href', 'https://github.com/VitorFcosta/ColdSafe',
  )
  await page.clock.runFor(10_100)

  expect(monitoringRequests).toEqual([])
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('abre a demonstração por teclado e oferece vídeo simulado com controles nativos', async ({ page }) => {
  await page.goto('/')
  const demoLink = page.getByRole('link', { name: 'Ver demonstração gravada', exact: true })
  await expect(demoLink).toHaveAttribute('href', '#demonstracao')
  await expect(demoLink).toHaveAccessibleDescription(/Versão anterior.*dados simulados/)
  await expect(page.getByText('Versão anterior · dados simulados', { exact: true })).toBeVisible()
  await demoLink.focus()
  await expect(demoLink).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#demonstracao$/)

  const demonstration = page.locator('#demonstracao')
  await expect(demonstration.locator('.section-heading')).toContainText(/dados simulados.*versão anterior.*histórico de temperatura.*desatualizadas.*comando de LED/)
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

test('menu móvel abre por teclado e mantém acesso à demonstração, código e painel', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByText('Protótipo acadêmico · AIoT', { exact: true })).toBeVisible()
  await expect(page.getByText('01', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Acessar painel' })).toHaveAttribute('href', '/dashboard')

  const menu = page.getByText('Menu', { exact: true })
  await menu.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.mobile-nav')).toHaveAttribute('open', '')
  await expect(page.getByRole('navigation', { name: 'Navegação principal móvel' }).getByRole('link')).toHaveCount(3)
  await expect(page.getByRole('navigation', { name: 'Navegação principal móvel' }).getByRole('link', { name: 'GitHub' })).toHaveAttribute('href', 'https://github.com/VitorFcosta/ColdSafe')
  const demonstration = page.getByRole('navigation', { name: 'Navegação principal móvel' }).getByRole('link', { name: 'Gravação anterior' })
  await demonstration.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#demonstracao$/)
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
        await expect(page.getByRole('link', { name: 'Ver demonstração gravada', exact: true })).toBeVisible()
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
  for (const section of await page.locator('.hero-copy').all()) {
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
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440)
    const control = route === '/' ? page.getByRole('link', { name: 'Ver demonstração gravada', exact: true }) : page.getByRole('button', { name: '24h', exact: true })
    await control.focus()
    await expect(control).toBeFocused()
    await expect(control).toBeVisible()
  }
})

test('texto ampliado não cria rolagem horizontal nas quatro rotas', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 })
  for (const route of ['/', '/login']) {
    await page.goto(route)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth), route).toBeLessThanOrEqual(360)
  }
  await mockMonitoringApi(page, { status: 'normal' })
  await page.route('**/api/v1/environments/*/rules', (route) => route.fulfill({
    json: { success: true, data: { min_c: 2, max_c: 8, attention_margin_c: 1 } },
  }))
  for (const route of ['/dashboard', '/manage']) {
    await page.goto(route)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth), route).toBeLessThanOrEqual(360)
  }
})

test('falha real de mídia mantém alternativas e permite duas tentativas antes de recuperar', async ({ page }) => {
  let fail = true, requests = 0
  await page.route('**/media/coldsafe-demo.webm', route => {
    requests++
    return fail ? route.abort('failed') : route.continue()
  })
  await page.goto('/#demonstracao')
  const status = page.getByRole('status'), video = page.locator('video')
  await expect(status).toContainText('Vídeo indisponível')
  await expect(page.getByRole('link', { name: 'Baixar demonstração (WebM, 6,1 MB)' })).toHaveAttribute('download', '')
  await expect(page.getByRole('heading', { name: 'Demonstração em texto' })).toBeVisible()
  const retry = page.getByRole('button', { name: 'Tentar carregar vídeo' })
  await retry.focus(); await page.keyboard.press('Enter')
  await expect(status).toContainText('Vídeo indisponível')
  expect(requests).toBeGreaterThanOrEqual(2)
  fail = false
  await retry.focus(); await page.keyboard.press('Enter')
  await expect(video).toBeFocused()
  await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.readyState)).toBeGreaterThanOrEqual(1)
  await expect(status).toHaveCount(0)
  await expect(video).toHaveJSProperty('paused', true)
  await expect(video).toHaveJSProperty('autoplay', false)
  await expect(video).toHaveJSProperty('currentTime', 0)
})

test('legendas indisponíveis encaminham à alternativa textual sem esconder o vídeo', async ({ page }) => {
  await page.route('**/media/coldsafe-demo.vtt', route => route.abort())
  await page.goto('/#demonstracao')
  await expect(page.locator('.caption-error')).toContainText('As legendas não puderam ser carregadas')
  const link = page.getByRole('link', { name: 'Ler transcrição da demonstração', exact: true })
  await link.focus(); await page.keyboard.press('Enter')
  await expect(page.locator('#transcript')).toBeFocused()
  await expect(page.locator('#transcript li')).toHaveCount(8)
  await expect(page.locator('#transcript li').last()).toContainText('LED')
  await expect(page.locator('video')).toHaveJSProperty('controls', true)
})

test('reproduz o vídeo local e verifica as oito legendas nos cenários gravados', async ({ page }) => {
  await page.goto('/#demonstracao')
  const video = page.locator('video')
  await video.scrollIntoViewIfNeeded()
  await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.readyState)).toBeGreaterThanOrEqual(2)
  await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.textTracks[0]?.cues?.length)).toBe(8)
  await video.evaluate((el: HTMLVideoElement) => el.play())
  await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.currentTime)).toBeGreaterThan(0.2)
  await video.evaluate((el: HTMLVideoElement) => el.pause())
  const cues = []
  for (const [time, text] of [[5, 'Leitura simulada'], [15, '24 horas'], [25, 'Atenção'], [35, 'Crítico'], [45, 'valor antigo'], [55, 'Falha simulada'], [65, 'Recuperação simulada'], [75, 'Comando simulado']] as const) {
    await video.evaluate((el: HTMLVideoElement, time) => { el.currentTime = time }, time)
    await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.seeking)).toBe(false)
    await expect.poll(() => video.evaluate((el: HTMLVideoElement) => (el.textTracks[0]?.activeCues?.[0] as VTTCue | undefined)?.text)).toContain(text)
    cues.push(await video.evaluate((el: HTMLVideoElement) => ({ time: el.currentTime, text: (el.textTracks[0]!.activeCues![0] as VTTCue).text })))
  }
  await video.evaluate((el: HTMLVideoElement) => el.play())
  await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.currentTime)).toBeGreaterThan(75.2)
  await video.evaluate((el: HTMLVideoElement) => new Promise<void>(resolve => el.requestVideoFrameCallback(() => { el.pause(); resolve() })))
  const frame = await video.evaluate((el: HTMLVideoElement) => {
    const canvas = document.createElement('canvas'); canvas.width = 16; canvas.height = 12
    const ctx = canvas.getContext('2d')!; ctx.drawImage(el, 0, 0, 16, 12)
    const pixels = ctx.getImageData(0, 0, 16, 12).data
    return { decodedFrames: el.getVideoPlaybackQuality().totalVideoFrames, lightPixels: Array.from({ length: 192 }, (_, i) => pixels[i * 4]! > 180 && pixels[i * 4 + 1]! > 180 && pixels[i * 4 + 2]! > 180).filter(Boolean).length }
  })
  expect(frame.decodedFrames).toBeGreaterThan(0)
  expect(frame.lightPixels).toBeGreaterThan(96)
  if (process.env.RD17_CAPTURE) {
    const { mkdir, writeFile } = await import('node:fs/promises')
    const dir = new URL('../../.impeccable/review/rd-17/', import.meta.url)
    await mkdir(dir, { recursive: true })
    await writeFile(new URL('media.json', dir), JSON.stringify({ duration: await video.evaluate((el: HTMLVideoElement) => el.duration), played: true, frame, cues }, null, 2))
    await video.scrollIntoViewIfNeeded()
    await video.screenshot({ path: new URL('video-caption.png', dir).pathname })
  }
})

for (const scenario of [{ width: 1440, height: 1024, text: 100 }, { width: 390, height: 844, text: 100 }, { width: 320, height: 640, text: 200 }]) {
  test(`UX-11 propósito, gravação anterior, âncoras e reflow ${scenario.width}px texto ${scenario.text}%`, async ({ page, browser }) => {
    await page.setViewportSize({ width: scenario.width, height: scenario.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const api: string[] = []
    await page.route('**/api/**', route => { api.push(route.request().url()); return route.abort() })
    await page.goto('/')
    if (scenario.text === 200) await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Monitore ambientes refrigerados e seus equipamentos')
    await expect(page.locator('.hero-copy')).toContainText('Acompanhe a temperatura do ambiente e as medições do motor')
    const preview = page.locator('.hero-preview')
    await expect(preview).toContainText('Painel atual · captura com dados simulados')
    const access = page.getByRole('link', { name: 'Acessar painel', exact: true })
    if (scenario.width === 1440) {
      await expect(preview).toBeInViewport({ ratio: 1 })
      await expect(access).toBeInViewport({ ratio: 1 })
      await expect(page.getByText('Versão anterior · dados simulados', { exact: true })).toBeInViewport({ ratio: 1 })
    }
    await expect(page.locator('.architecture-step')).toHaveCount(3)
    expect((await page.locator('#como-funciona').boundingBox())!.y).toBeGreaterThan((await page.locator('#demonstracao').boundingBox())!.y)
    await expect(page.locator('.demo-video figcaption')).toContainText('versão anterior')
    await expect(page.locator('footer')).toContainText('Não é equipamento médico, sanitário ou regulatório certificado')
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Ir para o conteúdo', exact: true })).toBeFocused()
    await page.keyboard.press('Enter'); await expect(page.locator('main')).toBeFocused()
    await expect(page.locator('.hero-copy')).toHaveCSS('animation-name', 'none')
    await expect(access).toHaveAttribute('href', '/dashboard')
    await access.focus(); await expect(access).toBeInViewport()
    await expect(access).toHaveCSS('outline-style', 'solid')
    await page.getByRole('link', { name: 'Ver demonstração gravada', exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.locator('#demonstracao')).toBeFocused()
    await page.locator('#como-funciona').evaluate((el: HTMLElement) => el.focus())
    await expect(page.locator('#como-funciona')).toBeInViewport()
    for (const image of await page.locator('img').all()) {
      await image.scrollIntoViewIfNeeded()
      await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(scenario.width)
    for (const link of await page.locator('a:visible, summary:visible').all()) {
      if (await link.evaluate(el => el.classList.contains('skip-link'))) continue
      expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    expect(api).toEqual([])
    if (process.env.RD17_CAPTURE) {
      const { mkdir, writeFile } = await import('node:fs/promises')
      const dir = new URL('../../.impeccable/review/rd-17/', import.meta.url)
      await mkdir(dir, { recursive: true })
      const name = scenario.width === 1440 ? 'desktop' : scenario.width === 390 ? 'mobile' : 'mobile-320-text-200'
      await expect.poll(() => page.locator('video').evaluate((el: HTMLVideoElement) => el.readyState)).toBeGreaterThanOrEqual(2)
      await page.evaluate(async () => { await document.fonts.ready; (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0) })
      await page.screenshot({ path: new URL(`${name}.png`, dir).pathname, fullPage: true })
      await page.screenshot({ path: new URL(`${name}-viewport.png`, dir).pathname })
      const styles = await page.evaluate(() => Object.fromEntries(['.presentation', 'h1', '.lead', '.button-primary', '.hero-actions .button:not(.button-primary)', '.hero-preview figcaption', '.architecture-step p', '.footer p'].map(selector => {
        const el = document.querySelector(selector)!, style = getComputedStyle(el)
        let surface: Element | null = el
        while (surface && getComputedStyle(surface).backgroundColor === 'rgba(0, 0, 0, 0)') surface = surface.parentElement
        return [selector, { color: style.color, background: surface ? getComputedStyle(surface).backgroundColor : '', outline: getComputedStyle(document.querySelector('.button-primary')!).getPropertyValue('--cs-focus-ring').trim(), fontSize: style.fontSize }]
      })))
      await writeFile(new URL(`${name}.json`, dir), JSON.stringify({ scenario, browser: browser.version(), styles }, null, 2))
      await page.locator('video').evaluate(el => el.dispatchEvent(new Event('error')))
      await page.locator('.media-error').scrollIntoViewIfNeeded()
      await page.getByRole('button', { name: 'Tentar carregar vídeo' }).focus()
      await page.screenshot({ path: new URL(`${name}-video-error.png`, dir).pathname })
    }
    await access.click()
    await expect(page).toHaveURL(url => url.pathname === '/login' && url.searchParams.get('redirect') === '/dashboard')
  })
}
