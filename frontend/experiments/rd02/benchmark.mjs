import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import os from 'node:os'
import { chromium } from '@playwright/test'

const base = process.env.RD02_BASE_URL ?? 'http://127.0.0.1:4173/experiments/rd02/'
const output = resolve(process.env.RD02_OUTPUT ?? resolve(dirname(fileURLToPath(import.meta.url)), '../../../.impeccable/review/rd-02'))
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: process.env.RD02_HEADLESS === 'true' })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2, reducedMotion: 'no-preference' })
const page = await context.newPage()
page.setDefaultTimeout(10_000)
const report = { date: new Date().toISOString(), hardware: process.env.RD02_HARDWARE ?? 'Não identificado pelo executor',
  os: { type: os.type(), release: os.release(), arch: os.arch() }, browser: browser.version(), headed: process.env.RD02_HEADLESS !== 'true',
  viewport: { width: 1440, height: 1000 }, requestedDpr: 2, durationPerSceneSeconds: 60, warmupSeconds: 3,
  build: process.env.RD02_BUILD ?? 'Build não identificado pelo executor',
  data: 'Fixtures controladas no harness; sem API, atuadores ou medição física.', scenes: {}, selection: [], inactivity: [], cycles: [] }
const api = (fn, arg) => page.evaluate(fn, arg)
const snapshot = () => api(() => ({ candidate: window.rd02.snapshot(), probe: window.rd02.probe.snapshot() }))

async function inactive(name, change) {
  await change()
  await page.waitForTimeout(300)
  const before = await snapshot()
  await page.waitForTimeout(1000)
  const after = await snapshot()
  const renders = after.probe.totalRenders - before.probe.totalRenders
  const result = { name, rendersDuring1s: renders, passed: renders === 0, before: before.candidate, after: after.candidate }
  report.inactivity.push(result)
  return result
}

try {
  await page.goto(base)
  await page.waitForFunction(() => Boolean(window.rd02))
  report.userAgent = await api(() => navigator.userAgent)
  for (const scene of ['baseline', 'candidate']) {
    console.log(`RD-02: aquecimento ${scene}; medição real de 60 s a seguir.`)
    await api((name) => window.rd02.setScene(name), scene)
    await api(() => window.rd02.setVisual('active'))
    await page.locator('canvas').waitFor({ state: 'visible' })
    await page.waitForTimeout(3000)
    await api(() => window.rd02.probe.start())
    for (let part = 0; part < 6; part++) await page.waitForTimeout(10_000)
    const result = await api(() => window.rd02.probe.stop())
    const gpu = result.gpu?.renderer ?? ''
    result.hardwareAccelerationObserved = gpu ? !/swiftshader|llvmpipe|softpipe|software|basic render/i.test(gpu) : null
    result.criteria = { hardwareObserved: result.hardwareAccelerationObserved === true,
      duration: result.durationMs >= 60_000, fps: result.fps >= 30,
      p95: result.p95IntervalMs !== null && result.p95IntervalMs <= 40,
      triangles: result.maxTriangles <= 50_000, calls: result.maxCalls <= 100, dpr: result.dpr <= 2 }
    report.scenes[scene] = result
    await api(() => window.scrollTo(0, 0))
    await page.screenshot({ path: resolve(output, `${scene}-desktop.png`), fullPage: true })
    console.log(`RD-02: ${scene}: ${result.fps.toFixed(2)} FPS; p95 ${result.p95IntervalMs?.toFixed(2)} ms; ${result.maxCalls} calls; ${result.maxTriangles} triângulos.`)
  }

  // A capture listener starts before Vue's click handler; the next frame checks visible DOM feedback.
  await page.evaluate(() => {
    window.addEventListener('pointerup', (event) => {
      if (!(event.target instanceof HTMLCanvasElement)) return
      const started = performance.now(), expected = window.__rd02Expected
      requestAnimationFrame(() => {
        window.__rd02Click = { id: expected, actual: document.querySelector('[data-selected-id]')?.getAttribute('data-selected-id'),
          pointerupToNextFrameMs: performance.now() - started }
      })
    }, { capture: true })
  })
  const points = await api(() => window.rd02.projection())
  assert.equal(points.length, 9, 'A candidata deve expor nove âncoras por ID')
  for (const point of points) {
    await page.evaluate((id) => { window.__rd02Expected = id; window.__rd02Click = null }, point.id)
    await page.locator('canvas').click({ position: { x: point.x, y: point.y } })
    await page.waitForFunction(() => Boolean(window.__rd02Click))
    const feedback = await api(() => window.__rd02Click)
    report.selection.push({ key: point.key, ...feedback, passed: feedback.actual === point.id && feedback.pointerupToNextFrameMs <= 100 })
  }
  await inactive('pausa manual', () => page.getByRole('button', { name: 'Pausar animação', exact: true }).click())
  await api(() => window.rd02.setVisual('changed'))
  report.pauseAfterData = await snapshot()
  await page.getByRole('button', { name: 'Retomar animação', exact: true }).click()
  await inactive('leitura vencida', () => api(() => window.rd02.setVisual('stale')))
  await inactive('equipamento parado', () => api(() => window.rd02.setVisual('stopped')))
  await api(() => window.rd02.setVisual('active'))
  await inactive('movimento reduzido', () => page.emulateMedia({ reducedMotion: 'reduce' }))
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  const otherTab = await context.newPage()
  await otherTab.bringToFront()
  let actuallyHidden = await api(() => document.hidden)
  const cdp = await context.newCDPSession(page)
  const { windowId } = await cdp.send('Browser.getWindowForTarget')
  if (!actuallyHidden) {
    // Headed pages may be separate windows; minimizing tests real visibility without overriding document.hidden.
    await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'minimized' } })
    await page.waitForTimeout(300)
    actuallyHidden = await api(() => document.hidden)
  }
  if (actuallyHidden) await inactive('aba realmente oculta', async () => {})
  else report.inactivity.push({ name: 'aba realmente oculta', passed: null, reason: 'Navegador não ocultou a aba; não simular como prova real.' })
  await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal' } })
  await cdp.detach()
  await otherTab.close()
  await page.bringToFront()

  await api(() => window.rd02.mount(false))
  for (let cycle = 1; cycle <= 10; cycle++) {
    await api(() => window.rd02.mount(true))
    await page.locator('canvas').waitFor({ state: 'visible' })
    await page.waitForTimeout(150)
    const mounted = await snapshot()
    await api(() => window.rd02.mount(false))
    await page.waitForTimeout(150)
    const unmounted = await snapshot()
    report.cycles.push({ cycle, mounted: mounted.probe, unmounted: unmounted.probe })
  }
  report.cycleCriteria = { tenCycles: report.cycles.length === 10,
    allContextsReleased: report.cycles.every((cycle) => cycle.unmounted.liveContexts === 0),
    stableMountedResources: new Set(report.cycles.map((cycle) => JSON.stringify(cycle.mounted.resources))).size === 1,
    trackingComplete: report.cycles.every((cycle) => !cycle.unmounted.trackingTruncated) }
  report.mobilePhysical = { measured: false, reason: 'Este protocolo foi executado no desktop; viewport móvel não comprova GPU móvel.' }
  report.passedDesktopCriteria = Object.values(report.scenes.candidate.criteria).every(Boolean)
    && report.selection.every((sample) => sample.passed)
    && report.inactivity.every((sample) => sample.passed === true)
    && Object.values(report.cycleCriteria).every(Boolean)
  await writeFile(resolve(output, 'benchmark.json'), JSON.stringify(report, null, 2))
  console.log(`RD-02: relatório salvo em ${resolve(output, 'benchmark.json')}; critérios desktop: ${report.passedDesktopCriteria}.`)
  if (!report.passedDesktopCriteria) process.exitCode = 1
} catch (error) {
  report.failure = error instanceof Error ? error.stack : String(error)
  await writeFile(resolve(output, 'benchmark.json'), JSON.stringify(report, null, 2))
  throw error
} finally {
  await browser.close()
}
