import assert from 'node:assert/strict'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, expect, type Page } from '@playwright/test'

import { mockMonitoringApi, type DashboardStatus } from '../e2e/monitoring-api.ts'

// Node 24: node scripts/capture-demo.ts [http://127.0.0.1:4175]
const baseUrl = new URL(process.argv[2] ?? process.env.CAPTURE_BASE_URL ?? 'http://127.0.0.1:4175')
assert(['http:', 'https:'].includes(baseUrl.protocol), 'A URL precisa usar HTTP ou HTTPS.')
const output = fileURLToPath(new URL('../public/media/', import.meta.url))
const receivedAt = Date.parse('2026-09-09T12:00:00Z')

type Scene = Readonly<{
  status: DashboardStatus
  label: string
  caption: string
  seconds: number
  temperature?: number
  ageSeconds?: number
  historyError?: boolean
  period?: '24h'
  image?: string
}>

const scenes: readonly Scene[] = [
  { status: 'normal', label: 'Normal', seconds: 8, image: 'dashboard-normal.png',
    caption: 'Leitura simulada: temperatura, estado e idade da leitura aparecem juntos.' },
  { status: 'normal', label: 'Normal', seconds: 10, period: '24h',
    caption: 'O período de 24 horas ajuda a observar a variação da temperatura simulada.' },
  { status: 'attention', label: 'Atenção', seconds: 9, temperature: 2.5, ageSeconds: 8,
    caption: 'Atenção: a temperatura simulada se aproxima do limite demonstrativo.' },
  { status: 'critical', label: 'Crítico', seconds: 9, temperature: 9, ageSeconds: 12, image: 'dashboard-critical.png',
    caption: 'Crítico: uma leitura simulada fora da faixa ganha destaque com texto e cor.' },
  { status: 'stale', label: 'Leitura desatualizada', seconds: 11, ageSeconds: 45, image: 'dashboard-stale.png',
    caption: 'Um valor antigo dentro da faixa não confirma a condição atual do ambiente.' },
  { status: 'normal', label: 'Normal', seconds: 11, historyError: true,
    caption: 'Falha simulada no histórico: o diagnóstico atual continua disponível.' },
  { status: 'normal', label: 'Normal', seconds: 10,
    caption: 'Recuperação simulada: o histórico volta na atualização automática, a cada 5 segundos.' },
]
assert.equal(scenes.reduce((total, scene) => total + scene.seconds, 0), 68)

async function installScenario(page: Page, scene: Scene) {
  await page.unroute('**/api/v1/monitoring/summary')
  await page.unroute('**/api/v1/readings?**')
  await mockMonitoringApi(page, scene)
  await page.route('**/api/v1/readings?**', async (route) => {
    if (scene.historyError) {
      await route.fulfill({ status: 503, json: { success: false, error: {
        code: 'DEPENDENCY_UNAVAILABLE', message: 'Falha simulada no histórico.',
      } } })
      return
    }
    const period = new URL(route.request().url()).searchParams.get('period')
    const duration = period === '24h' ? 86_400_000 : period === '6h' ? 21_600_000 : period === '15m' ? 900_000 : 3_600_000
    const readings = Array.from({ length: 40 }, (_, index) => {
      const temperature = index === 39 ? scene.temperature ?? 5 : Number((4.7 + Math.sin(index * 0.45) * 0.65).toFixed(1))
      return {
        temperature_c: temperature,
        humidity_percent: 65,
        received_at: new Date(receivedAt - duration + duration * index / 39).toISOString(),
        status: temperature < 2 || temperature > 8 ? 'critical' : temperature < 3 || temperature > 7 ? 'attention' : 'normal',
      }
    })
    await route.fulfill({ json: {
      success: true, data: { readings },
      meta: { device_id: 'esp32-lab-01', start: new Date(receivedAt - duration).toISOString(),
        end: new Date(receivedAt).toISOString(), count: readings.length, limit: 300 },
    } })
  })
}

async function addCaptureBanner(page: Page) {
  await page.addStyleTag({ content: `
    body { padding-top: 90px !important; }
    [data-capture-banner] { position:fixed; inset:0 0 auto; z-index:9999; padding:16px 28px;
      background:#102c32; color:#fff; border-bottom:2px solid #70e8da;
      font:14px/1.5 system-ui,sans-serif; box-sizing:border-box; }
    [data-capture-banner] strong { display:block; color:#70e8da; font:600 11px/1.5 monospace;
      letter-spacing:.12em; margin-bottom:5px; }
    @media(max-width:600px) { body {padding-top:112px!important;}
      [data-capture-banner] {padding:12px 18px; font-size:12px;} }
  ` })
  await page.evaluate(() => {
    const banner = document.createElement('aside')
    banner.dataset.captureBanner = ''
    const title = document.createElement('strong')
    title.textContent = 'COLDSAFE / DEMONSTRAÇÃO SIMULADA'
    const caption = document.createElement('span')
    caption.dataset.captureCaption = ''
    caption.textContent = 'Dados fictícios para apresentação do protótipo acadêmico.'
    banner.append(title, caption)
    document.body.append(banner)
  })
}

async function caption(page: Page, text: string) {
  await page.locator('[data-capture-caption]').evaluate((element, value) => { element.textContent = value }, text)
}

async function ready(page: Page, scene: Scene) {
  await expect(page.getByText(scene.label, { exact: true })).toBeVisible({ timeout: 12_000 })
  if (scene.historyError) {
    await expect(page.getByRole('status')).toContainText('histórico de temperatura não pôde ser carregado', { timeout: 12_000 })
  } else {
    await expect(page.getByRole('img', { name: 'Gráfico de linha da temperatura no período selecionado' })).toBeVisible({ timeout: 12_000 })
  }
}

function timestamp(milliseconds: number) {
  return new Date(Math.round(Math.max(0, milliseconds))).toISOString().slice(11, 23)
}

await mkdir(output, { recursive: true })
const temporaryVideoDirectory = await mkdtemp(join(tmpdir(), 'coldsafe-video-'))
const browser = await chromium.launch()
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1080 }, reducedMotion: 'reduce', locale: 'pt-BR', timezoneId: 'UTC',
    recordVideo: { dir: temporaryVideoDirectory, size: { width: 1440, height: 1080 } },
  })
  const recordingStart = Date.now()
  const page = await context.newPage()
  await installScenario(page, scenes[0]!)
  await page.goto(new URL('/dashboard', baseUrl).href)
  await ready(page, scenes[0]!)
  await page.evaluate(() => document.fonts.ready)
  await addCaptureBanner(page)
  let targetEnd = Date.now()
  const cues: { start: number; end: number; text: string }[] = []

  for (const [index, scene] of scenes.entries()) {
    targetEnd += scene.seconds * 1000
    if (index > 0) {
      await caption(page, 'Próximo cenário simulado: aguardando a atualização automática…')
      await installScenario(page, scene)
      if (scene.period) await page.getByRole('button', { name: scene.period, exact: true }).click()
      await ready(page, scene)
    }
    const start = Date.now() - recordingStart
    await caption(page, scene.caption)
    if (scene.period || scene.historyError) {
      await page.locator('#temperature-history-title').scrollIntoViewIfNeeded()
    } else {
      await page.evaluate(() => window.scrollTo(0, 0))
    }
    if (scene.image) await page.screenshot({ path: join(output, scene.image), fullPage: true })
    console.log(`Cena ${index + 1}/${scenes.length}: ${scene.label}${scene.historyError ? ' / histórico indisponível' : ''}`)
    await page.waitForTimeout(Math.max(0, targetEnd - Date.now()))
    cues.push({ start, end: Date.now() - recordingStart, text: `DEMONSTRAÇÃO SIMULADA — ${scene.caption}` })
  }

  const video = page.video()
  assert(video, 'O Playwright não iniciou a gravação.')
  await context.close()
  await video.saveAs(join(output, 'coldsafe-demo.webm'))
  await writeFile(join(output, 'coldsafe-demo.vtt'), 'WEBVTT\n\n' + cues.map((cue, index) =>
    `${index + 1}\n${timestamp(cue.start)} --> ${timestamp(cue.end)}\n${cue.text}\n`,
  ).join('\n'))

  const mobile = await browser.newContext({ viewport: { width: 375, height: 900 }, reducedMotion: 'reduce', locale: 'pt-BR', timezoneId: 'UTC' })
  const mobilePage = await mobile.newPage()
  await installScenario(mobilePage, scenes[0]!)
  await mobilePage.goto(new URL('/dashboard', baseUrl).href)
  await ready(mobilePage, scenes[0]!)
  await addCaptureBanner(mobilePage)
  await mobilePage.screenshot({ path: join(output, 'dashboard-mobile.png'), fullPage: true })
  await mobile.close()
  console.log(`Mídia salva em ${output}`)
} finally {
  await browser.close()
  await rm(temporaryVideoDirectory, { recursive: true, force: true })
}
