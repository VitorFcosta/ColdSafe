import { mkdirSync, writeFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const api = process.env.ASSISTANT_REAL_API_URL ?? ''
const control = process.env.ASSISTANT_REAL_CONTROL_URL ?? ''
test.skip(!process.env.ASSISTANT_REAL_URL || !api || !control || !process.env.ASSISTANT_REAL_PASSWORD,
  'Run through disposable B2-32 PostgreSQL/HTTP integration harness; Ollama protocol is a declared double')

test('streaming antes do terminal, texto seguro, cancelamento e duas contas com HTTP real', async ({ page, request }) => {
  const output = process.env.ASSISTANT_REAL_EVIDENCE_DIR!
  mkdirSync(output, { recursive: true })
  const login = async (email: string) => {
    const response = await request.post(`${api}/api/v1/auth/login`, {
      data: { email, password: process.env.ASSISTANT_REAL_PASSWORD },
    })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const first = await login(process.env.ASSISTANT_REAL_EMAIL!)
  const second = await login(process.env.ASSISTANT_REAL_OTHER_EMAIL!)
  await page.addInitScript((value) => sessionStorage.setItem('coldsafe-session', JSON.stringify(value)), first)
  let remoteRequests = 0
  await page.route('https://remote.invalid/**', async (route) => { remoteRequests++; await route.abort() })
  await page.goto('/assistant')
  const question = page.getByRole('textbox', { name: 'Sua pergunta', exact: true })
  const send = page.getByRole('button', { name: 'Enviar pergunta', exact: true })
  await question.fill('Qual é o contexto autorizado?')
  await expect(send).toBeEnabled()
  await send.click()
  await expect(page.getByTestId('answer')).toContainText('browser-private-a')
  const upstream = await (await request.get(`${control}/test/state`)).json()
  expect(upstream.entered).toBe(true)
  expect(upstream.released).toBe(false)
  await expect(page.getByText('Resposta em andamento', { exact: true })).toBeVisible()
  await expect(page.getByText('Resposta concluída', { exact: true })).toHaveCount(0)
  await request.post(`${control}/test/release`)
  await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible()
  const chat = page.getByRole('list', { name: 'Conversa desta sessão', exact: true })
  await expect(chat.locator('script,img,iframe,a')).toHaveCount(0)
  await expect(page.getByTestId('answer')).toContainText('<img src="https://remote.invalid/pixel">')
  expect(remoteRequests).toBe(0)
  expect(await page.evaluate(() => (window as Window & { __assistantExecuted?: number }).__assistantExecuted)).toBeUndefined()
  await page.screenshot({ path: `${output}/assistant-desktop.png`, fullPage: true })

  await request.post(`${control}/test/reset`)
  await question.fill('Pergunta para cancelar')
  await expect(send).toBeEnabled()
  await send.click()
  await expect(chat.locator('li').last().getByTestId('answer')).toContainText('browser-private-a')
  expect((await (await request.get(`${control}/test/state`)).json()).entered).toBe(true)
  await page.getByRole('button', { name: 'Cancelar resposta', exact: true }).click()
  await expect(page.getByText('Resposta incompleta', { exact: true })).toBeVisible()
  await expect.poll(async () => (await (await request.get(`${control}/test/state`)).json()).unloaded).toBe(true)

  await request.post(`${control}/test/reset`)
  await page.evaluate(async (session) => {
    const modulePath = '/src/features/account/session.ts'
    const { setSession } = await import(modulePath)
    setSession(session.token, session.expires_at)
  }, second)
  await expect(chat.locator('li')).toHaveCount(0)
  await expect(question).toHaveValue('')
  await question.fill('Qual é o contexto desta conta?')
  await expect(send).toBeEnabled()
  await send.click()
  await expect(page.getByTestId('answer')).toContainText('browser-private-b')
  await expect(page.getByTestId('answer')).not.toContainText('browser-private-a')
  await request.post(`${control}/test/release`)
  await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 320, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: `${output}/assistant-mobile320.png`, fullPage: true })
  writeFileSync(`${output}/browser-wire.json`, JSON.stringify({
    real_postgres_http_sse_browser: true,
    ollama: 'explicit local protocol double; no language-model quality claim',
    delta_visible_before_upstream_terminal: true, html_and_remote_images_plain_text: true,
    remote_image_requests: remoteRequests, cancellation_confirmed_unload: true,
    real_jwt_accounts_isolated: true, session_switch_wipes_history: true,
    mobile320_without_overflow: true,
  }, null, 2))
})
