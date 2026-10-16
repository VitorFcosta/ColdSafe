import { expect, test } from '@playwright/test'

const api = process.env.MESSAGING_REAL_API_URL ?? ''
const password = process.env.MESSAGING_REAL_PASSWORD ?? ''
const eventId = process.env.OBSERVATION_REAL_EVENT_ID ?? ''
const deadId = process.env.OBSERVATION_REAL_DEAD_ID ?? ''
test.skip(!process.env.MESSAGING_REAL_URL || !api || !password || !eventId || !deadId,
  'Run the opt-in disposable observation integration harness')

test('amostras reais privadas e DLQ preservada são legíveis no mobile via ColdSafe', async ({ page }) => {
  const origins = new Set<string>()
  page.on('request', (request) => origins.add(new URL(request.url()).origin))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/login')
  await page.getByLabel('Email').fill(process.env.MESSAGING_REAL_ADMIN_EMAIL ?? 'messaging-admin@example.invalid')
  await page.getByLabel('Senha').fill(password)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente' })).toBeVisible()
  const response = page.waitForResponse((value) => value.url() === `${api}/api/v3/messaging/messages` && value.status() === 200)
  await page.getByRole('link', { name: 'Mensageria', exact: true }).click()
  const body = await (await response).json()
  expect(body.success).toBe(true)
  expect(body.data.messages.length).toBeLessThanOrEqual(100)
  expect(body.data.dead_letters.length).toBeLessThanOrEqual(100)
  for (const sample of [...body.data.messages, ...body.data.dead_letters]) {
    expect(Object.keys(sample).sort()).toEqual(['event_id', 'type', 'occurred_at', 'observed_at',
      'device_record_id', 'device_id', 'environment_id', 'correlation_id', 'source_queue', 'reason', 'error_code'].sort())
  }
  const messages = page.getByRole('region', { name: 'Últimas mensagens', exact: true })
  const dead = page.getByRole('region', { name: 'Mensagens mortas (DLQ)', exact: true })
  await expect(messages.getByText(eventId, { exact: true })).toBeVisible()
  await expect(dead.getByText(deadId, { exact: true })).toBeVisible()
  const letter = dead.getByRole('listitem').filter({ hasText: deadId })
  await expect(letter).toContainText('coldsafe.writer')
  await expect(letter).toContainText('rejected')
  await expect(letter).toContainText(process.env.OBSERVATION_REAL_ERROR_CODE ?? 'INVALID_SCHEMA')
  await expect(page.getByText('Confirme o estado do serviço no terminal.', { exact: false })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Mensageria', exact: true })).toBeFocused()
  const table = page.getByRole('region', { name: /Métricas por fila/ })
  await table.focus()
  await expect(table).toBeFocused()
  await page.keyboard.press('ArrowRight')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect([...origins].sort()).toEqual([...new Set([new URL(api).origin, new URL(process.env.MESSAGING_REAL_URL!).origin])].sort())
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText(eventId, { exact: true })).toHaveCount(0)
  await expect(page.getByText(deadId, { exact: true })).toHaveCount(0)
})
