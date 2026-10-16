import { execFileSync } from 'node:child_process'
import { expect, test, type Page } from '@playwright/test'

const api = process.env.MESSAGING_REAL_API_URL ?? ''
const password = process.env.MESSAGING_REAL_PASSWORD ?? ''
const admin = process.env.MESSAGING_REAL_ADMIN_EMAIL ?? 'messaging-admin@example.invalid'

test.skip(!process.env.MESSAGING_REAL_URL || !api || !password || !process.env.MESSAGING_REAL_COMPOSE,
  'Run the opt-in disposable messaging integration harness')

function broker(action: 'pause' | 'unpause') {
  const base: string[] = JSON.parse(process.env.MESSAGING_REAL_COMPOSE!)
  execFileSync('docker', [...base, action, 'rabbitmq'], { stdio: 'pipe', timeout: 45_000 })
}
async function login(page: Page, email = admin) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Senha').fill(password)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente' })).toBeVisible()
  await page.getByRole('link', { name: 'Mensageria', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Mensageria', exact: true })).toBeVisible()
}
async function messagingStatus(page: Page) {
  return page.evaluate(async (api) => {
    const token = JSON.parse(sessionStorage.getItem('coldsafe-session')!).token
    const response = await fetch(`${api}/api/v3/messaging`, { headers: { authorization: `Bearer ${token}` } })
    return response.status
  }, api)
}

test('métricas reais, atualização e navegação por teclado no mobile; navegador usa apenas ColdSafe', async ({ page }) => {
  const origins = new Set<string>()
  page.on('request', (request) => origins.add(new URL(request.url()).origin))
  await page.setViewportSize({ width: 390, height: 844 })
  const firstSample = page.waitForResponse((response) => response.url() === `${api}/api/v3/messaging` && response.status() === 200)
  await login(page)
  const data = (await (await firstSample).json()).data
  expect(data.queues).toHaveLength(9)
  await expect(page.getByRole('heading', { name: 'Mensageria', exact: true })).toBeFocused()
  await expect(page.locator('tbody tr')).toHaveCount(data.queues.length)
  for (const queue of data.queues) {
    const row = page.getByRole('row').filter({ has: page.getByRole('rowheader', { name: queue.name, exact: true }) })
    await expect(row).toBeVisible()
    const cells = row.getByRole('cell')
    for (const [index, key] of ['messages', 'messages_ready', 'messages_unacknowledged', 'consumers'].entries()) {
      await expect(cells.nth(index)).toHaveText(String(queue[key]))
    }
    for (const [index, key] of ['publish_rate', 'deliver_rate'].entries()) {
      const label = queue[key] === null ? 'Indisponível' : `${Number(queue[key]).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} /s`
      await expect(cells.nth(index + 4)).toHaveText(label)
    }
  }
  const updated = page.waitForResponse((response) => response.url() === `${api}/api/v3/messaging` && response.status() === 200)
  await updated
  const region = page.getByRole('region', { name: /Métricas por fila/ })
  await region.focus()
  await expect(region).toBeFocused()
  await page.keyboard.press('ArrowRight')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect([...origins].sort()).toEqual([...new Set([new URL(api).origin, new URL(process.env.MESSAGING_REAL_URL!).origin])].sort())
})

test('queda real do RabbitMQ mantém última amostra, idade e falha; recupera automaticamente', async ({ page }) => {
  test.setTimeout(120_000)
  await login(page)
  await expect(page.locator('tbody tr')).toHaveCount(9)
  const before = await page.locator('time').getAttribute('datetime')
  // Keep Docker's ephemeral host mapping stable while the real broker is unavailable.
  broker('pause')
  try {
    await expect(page.getByRole('alert')).toContainText('Não foi possível atualizar', { timeout: 20_000 })
    await expect(page.getByRole('alert')).toContainText('Última consulta bem-sucedida')
    await expect(page.locator('tbody tr')).toHaveCount(9)
    await expect(page.locator('time')).toHaveAttribute('datetime', before!)
    await expect(page.getByRole('status')).toContainText('Informação desatualizada', { timeout: 20_000 })
    expect(await messagingStatus(page)).toBe(503)
  } finally {
    broker('unpause')
  }
  await expect(page.getByRole('alert')).toHaveCount(0, { timeout: 40_000 })
  await expect(page.locator('time')).not.toHaveAttribute('datetime', before!)
})

for (const role of ['operator', 'viewer'] as const) {
  test(`${role} não vê métricas globais e API real recusa acesso`, async ({ page }) => {
    const calls: string[] = []
    page.on('request', (request) => { if (request.url() === `${api}/api/v3/messaging`) calls.push(request.url()) })
    await login(page, process.env[`MESSAGING_REAL_${role.toUpperCase()}_EMAIL`] ?? `messaging-${role}@example.invalid`)
    await expect(page.getByRole('status')).toContainText('apenas para administradores')
    await expect(page.getByRole('table')).toHaveCount(0)
    expect(calls).toHaveLength(0)
    expect(await messagingStatus(page)).toBe(403)
  })
}
