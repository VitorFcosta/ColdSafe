import { mkdirSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

// HTTP fixtures exercise the real Vue view and SSE parser; no model quality claim.
const requestId = '12345678-1234-4234-9234-123456789abc'
const token = 'assistant-browser-fixture'
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
const delta = (text: string) => `event: delta\ndata: ${JSON.stringify({ text })}\n\n`
const done = `event: done\ndata: ${JSON.stringify({ request_id: requestId })}\n\n`

async function account(page: Page, state: () => string = () => 'ready') {
  await page.addInitScript((value) => sessionStorage.setItem('coldsafe-session', JSON.stringify({
    token: value, expires_at: '2099-01-01T00:00:00Z',
  })), token)
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
    success: true, data: { user_id: requestId, email: 'viewer@example.invalid', role: 'viewer' },
  } }))
  await page.route('**/api/v3/llm/status', (route) => route.fulfill({ json: envelope({
    state: state(), model: 'llama3.2:3b-instruct-q4_K_M',
  }) }))
}

test('texto não executável, seis perguntas e teclado em desktop e320px (HTTP simulado)', async ({ page }) => {
  await account(page)
  const unsafe = '<script>window.__assistantExecuted=1</script> <img src="https://remote.invalid/pixel">\n![imagem](https://remote.invalid/markdown) **texto literal**'
  let posts = 0
  let remoteRequests = 0
  await page.route('https://remote.invalid/**', async (route) => { remoteRequests++; await route.abort() })
  await page.route('**/api/v3/llm/ask', async (route) => {
    posts++
    expect(route.request().headers().authorization).toBe(`Bearer ${token}`)
    expect(Object.keys(route.request().postDataJSON())).toEqual(['question'])
    await route.fulfill({ contentType: 'text/event-stream', body: delta(unsafe) + done })
  })
  await page.goto('/assistant')
  await expect(page.getByRole('heading', { name: 'Assistente', exact: true })).toBeVisible()
  await expect(page.getByTestId('suggestion')).toHaveCount(6)
  const question = page.getByRole('textbox', { name: 'Sua pergunta', exact: true })
  await page.getByTestId('suggestion').first().click()
  await expect(question).not.toHaveValue('')
  expect(posts).toBe(0)
  await question.focus()
  await question.press('Tab')
  const send = page.getByRole('button', { name: 'Enviar pergunta', exact: true })
  await expect(send).toBeFocused()
  await send.press('Enter')
  await expect(page.getByTestId('answer')).toHaveText(unsafe)
  await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible()
  const chat = page.getByRole('list', { name: 'Conversa desta sessão', exact: true })
  await expect(chat.locator('script,img,iframe,a')).toHaveCount(0)
  expect(await page.evaluate(() => (window as Window & { __assistantExecuted?: number }).__assistantExecuted)).toBeUndefined()
  expect(remoteRequests).toBe(0)
  mkdirSync('/tmp/coldsafe-b232', { recursive: true })
  await page.screenshot({ path: '/tmp/coldsafe-b232/assistant-fixture-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 320, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '/tmp/coldsafe-b232/assistant-fixture-mobile320.png', fullPage: true })
  expect(posts).toBe(1)
})

test('preparação, indisponibilidade e recuperação não enviam perguntas automaticamente', async ({ page }) => {
  let state = 'loading'
  let posts = 0
  await account(page, () => state)
  await page.route('**/api/v3/llm/ask', (route) => { posts++; return route.abort() })
  await page.goto('/assistant')
  await expect(page.getByText('Preparando o modelo local. Aguarde o carregamento para perguntar.', { exact: true })).toBeVisible()
  const question = page.getByRole('textbox', { name: 'Sua pergunta', exact: true })
  await question.fill('Qual o estado?')
  const send = page.getByRole('button', { name: 'Enviar pergunta', exact: true })
  await expect(send).toBeDisabled()
  state = 'unavailable'
  await expect(page.getByText(/assistente local indisponível/i)).toBeVisible()
  await expect(send).toBeDisabled()
  state = 'ready'
  await expect(send).toBeEnabled()
  expect(posts).toBe(0)
})

test('streaming interrompido conserva texto parcial como incompleto sem reenvio', async ({ page }) => {
  await account(page)
  let posts = 0
  await page.route('**/api/v3/llm/ask', (route) => {
    posts++
    return route.fulfill({ contentType: 'text/event-stream', body: delta('Texto parcial da conta') })
  })
  await page.goto('/assistant')
  await page.getByRole('textbox', { name: 'Sua pergunta', exact: true }).fill('Qual a vida útil?')
  await page.getByRole('button', { name: 'Enviar pergunta', exact: true }).click()
  await expect(page.getByTestId('answer')).toContainText('Texto parcial da conta')
  await expect(page.getByText('Resposta incompleta', { exact: true })).toBeVisible()
  await expect(page.getByText('Resposta concluída', { exact: true })).toHaveCount(0)
  await expect(page.locator('.notice')).toContainText(/interrompida|incompleto/i)
  await page.waitForTimeout(2200)
  expect(posts).toBe(1)
})

test('limite429 tem espera explícita e só tenta de novo por ação do usuário', async ({ page }) => {
  await account(page)
  await page.clock.install()
  let posts = 0
  await page.route('**/api/v3/llm/ask', (route) => {
    posts++
    if (posts === 1) return route.fulfill({ status: 429, headers: { 'Retry-After': '60' }, json: {
      success: false, error: { code: 'RATE_LIMITED', message: 'Limite de perguntas.' },
    } })
    return route.fulfill({ contentType: 'text/event-stream', body: delta('Resposta após nova ação') + done })
  })
  await page.goto('/assistant')
  const question = page.getByRole('textbox', { name: 'Sua pergunta', exact: true })
  const send = page.getByRole('button', { name: 'Enviar pergunta', exact: true })
  await question.fill('Qual o estado?')
  await send.click()
  await expect(page.locator('.notice')).toContainText(/limite|aguarde/i)
  await expect(send).toBeDisabled()
  await question.fill('Qual o estado agora?')
  await page.clock.fastForward(61_000)
  await expect(send).toBeEnabled({ timeout: 6000 })
  expect(posts).toBe(1)
  await send.click()
  await expect(page.getByTestId('answer').last()).toHaveText('Resposta após nova ação')
  expect(posts).toBe(2)
})

test('troca de sessão apaga conversa e ignora401 atrasado da conta anterior', async ({ page }) => {
  await account(page)
  let release!: () => void
  const held = new Promise<void>((resolve) => { release = resolve })
  let oldRequest = false
  await page.route('**/api/v3/llm/ask', async (route) => {
    if (route.request().headers().authorization === `Bearer ${token}`) {
      oldRequest = true
      await held
      await route.fulfill({ status: 401, json: { success: false, error: { code: 'UNAUTHORIZED' } } }).catch(() => {})
      return
    }
    await route.fulfill({ contentType: 'text/event-stream', body: delta('Somente conta nova') + done })
  })
  await page.goto('/assistant')
  await page.getByRole('textbox', { name: 'Sua pergunta', exact: true }).fill('Pergunta privada antiga')
  await page.getByRole('button', { name: 'Enviar pergunta', exact: true }).click()
  await expect.poll(() => oldRequest).toBe(true)
  await page.evaluate(async () => {
    const modulePath = '/src/features/account/session.ts'
    const { setSession } = await import(modulePath)
    setSession('assistant-new-account', '2099-01-01T00:00:00Z')
  })
  release()
  await expect(page.getByRole('list', { name: 'Conversa desta sessão', exact: true }).locator('li')).toHaveCount(0)
  const question = page.getByRole('textbox', { name: 'Sua pergunta', exact: true })
  await expect(question).toHaveValue('')
  await question.fill('Pergunta da conta nova')
  await page.getByRole('button', { name: 'Enviar pergunta', exact: true }).click()
  await expect(page.getByTestId('answer')).toHaveText('Somente conta nova')
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('coldsafe-session')!).token)).toBe('assistant-new-account')
  await expect(page.getByText('Pergunta privada antiga', { exact: true })).toHaveCount(0)
})
