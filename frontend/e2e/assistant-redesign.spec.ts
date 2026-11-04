import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'

const requestId = '12345678-1234-4234-9234-123456789abc'
const token = 'rd15-account'
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
const evidence = new URL('../../.impeccable/review/rd-15/', import.meta.url)
type FixtureWindow = Window & { rd15Stream: { enabled: boolean; posts: string[]; tokens: (string | null)[]; aborts: number; controller?: ReadableStreamDefaultController<Uint8Array> } }
const question = (page: Page) => page.getByRole('textbox', { name: 'Sua pergunta', exact: true })
const sendButton = (page: Page) => page.getByRole('button', { name: 'Enviar pergunta', exact: true })
const exitDialog = (page: Page) => page.getByRole('dialog', { name: 'Sair e apagar a conversa?', exact: true })
const checkLink = (page: Page) => page.getByRole('link', { name: 'Saúde e previsões', exact: true })

async function assistant(page: Page) {
  await page.addInitScript(({ token }) => {
    if (!sessionStorage.getItem('coldsafe-session')) sessionStorage.setItem('coldsafe-session', JSON.stringify({ token, expires_at: '2099-01-01T00:00:00Z' }))
    // Stream controlado no navegador: o cliente e o parser SSE de produção permanecem reais.
    const fixture = (window as FixtureWindow).rd15Stream = { enabled: true, posts: [], tokens: [], aborts: 0 }
    const originalFetch = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : input.href
      if (!fixture.enabled || !new URL(url, location.href).pathname.endsWith('/api/v3/llm/ask')) return originalFetch(input, init)
      fixture.posts.push(JSON.parse(String(init?.body)).question)
      fixture.tokens.push(new Headers(init?.headers).get('authorization'))
      const stream = new ReadableStream<Uint8Array>({ start(controller) { fixture.controller = controller } })
      init?.signal?.addEventListener('abort', () => {
        fixture.aborts++
        fixture.controller?.error(new DOMException('Cancelled', 'AbortError'))
      }, { once: true })
      return new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
    }
  }, { token })
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { success: false } }))
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: requestId, email: 'viewer@example.invalid', role: 'viewer' } } }))
  await page.route('**/api/v1/auth/logout', route => route.fulfill({ status: 200 }))
  await page.route('**/api/v3/llm/status', route => route.fulfill({ json: envelope({ state: 'ready', model: 'test-model' }) }))
}
async function frame(page: Page, kind: string, data: unknown, close = false) {
  await page.evaluate(({ kind, data, close }) => {
    const controller = (window as FixtureWindow).rd15Stream.controller!
    controller.enqueue(new TextEncoder().encode(`event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`))
    if (close) controller.close()
  }, { kind, data, close })
}
async function start(page: Page, text = 'Qual a vida útil restante?') {
  await question(page).fill(text); await sendButton(page).click()
  await expect(page.getByText('Resposta em andamento', { exact: true }).last()).toBeVisible()
}
async function settleCapture(page: Page) {
  await page.evaluate(async () => {
    window.scrollTo(0, 0)
    await document.fonts.ready
    await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  })
}
async function postCount(page: Page) { return page.evaluate(() => (window as FixtureWindow).rd15Stream.posts.length) }

for (const scenario of [{ width: 1440, text: 100 }, { width: 390, text: 100 }, { width: 320, text: 200 }]) {
  test(`M-10 stream, foco e saída consciente: ${scenario.width}px texto ${scenario.text}% (stream simulado)`, async ({ page }) => {
    await page.setViewportSize({ width: scenario.width, height: 1024 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await assistant(page)
    await page.goto('/assistant?environment=ignored&device=ignored')
    if (scenario.text === 200) await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    await expect(page.getByText('Modelo local pronto. Você já pode perguntar.', { exact: true })).toBeVisible()
    await expect(question(page)).toHaveAccessibleDescription(/inclusive respostas concluídas/)
    await expect(page.getByTestId('suggestion')).toHaveCount(6)
    await mkdir(evidence, { recursive: true })
    const name = scenario.width === 1440 ? 'desktop' : scenario.width === 390 ? 'mobile' : 'mobile-320-text-200'
    await expect(page.locator('.model-status')).toHaveClass(/ready/)
    await expect(question(page)).toHaveCSS('font-size', scenario.text === 200 ? '32px' : '16px')
    await settleCapture(page)
    const palette = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement)
      return Object.fromEntries(['ink', 'ink-muted', 'surface', 'surface-muted', 'control-border', 'accent', 'accent-ink', 'status-normal', 'normal-surface', 'status-attention', 'attention-surface'].map(name => [name, root.getPropertyValue(`--cs-color-${name}`).trim()]))
    })
    await page.screenshot({ path: new URL(`${name}.png`, evidence).pathname, fullPage: true })
    await page.getByTestId('suggestion').first().click()
    await expect(question(page)).toBeFocused(); expect(await postCount(page)).toBe(0)
    await question(page).press('Tab'); await expect(sendButton(page)).toBeFocused(); await page.keyboard.press('Enter')
    await expect(page.getByText('Resposta em andamento', { exact: true })).toBeVisible()
    await question(page).focus()
    const text = 'Estimativa parcial <img src="https://remote.invalid/pixel"> **texto literal**.'
    await frame(page, 'delta', { text })
    await expect(page.getByTestId('answer')).toHaveText(text)
    await expect(question(page)).toBeFocused()
    await frame(page, 'delta', { text: ' Segundo fragmento.' })
    await expect(page.getByTestId('answer')).toContainText('Segundo fragmento.')
    await expect(question(page)).toBeFocused()
    expect(await page.getByTestId('answer').evaluate(el => el.closest('[aria-live], [role="status"], [role="log"]') === null)).toBe(true)
    await expect(page.getByRole('list', { name: 'Conversa desta sessão', exact: true }).locator('img,script,a')).toHaveCount(0)
    await settleCapture(page)
    await page.screenshot({ path: new URL(`${name}-stream.png`, evidence).pathname, fullPage: true })
    await page.getByTestId('cancel').focus(); await page.keyboard.press('Enter')
    await expect(question(page)).toBeFocused()
    await expect(page.getByText('Resposta incompleta', { exact: true })).toBeVisible()
    await expect(page.getByText('Resposta concluída', { exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => (window as FixtureWindow).rd15Stream.aborts)).toBeGreaterThan(0)
    await settleCapture(page)
    await page.screenshot({ path: new URL(`${name}-incomplete.png`, evidence).pathname, fullPage: true })
    await start(page, 'Pergunta de navegação')
    await frame(page, 'delta', { text: 'Ainda recebendo.' })
    await checkLink(page).click()
    const dialog = exitDialog(page), stay = dialog.getByRole('button', { name: 'Permanecer', exact: true })
    await expect(stay).toBeFocused()
    expect(await dialog.evaluate(el => el.matches(':modal'))).toBe(true)
    await question(page).evaluate(el => (el as HTMLTextAreaElement).focus())
    await expect(stay).toBeFocused()
    await page.screenshot({ path: new URL(`${name}-leave.png`, evidence).pathname })
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible(); await expect(checkLink(page)).toBeFocused()
    await expect(page).toHaveURL('/assistant?environment=ignored&device=ignored')
    await expect(page.getByTestId('answer').last()).toHaveText('Ainda recebendo.')
    const layout = await page.evaluate(() => {
      const input = getComputedStyle(document.querySelector('textarea')!), scope = getComputedStyle(document.querySelector('#assistant-scope')!)
      return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth, rootFont: getComputedStyle(document.documentElement).fontSize,
        input: { color: input.color, background: input.backgroundColor, border: input.borderColor }, scope: { color: scope.color },
        panels: [...document.querySelectorAll('.workspace > *')].map(el => ({ name: el.getAttribute('aria-label'), width: el.clientWidth, scrollWidth: el.scrollWidth })) }
    })
    expect(layout.scrollWidth).toBe(scenario.width)
    await writeFile(new URL(`${name}-layout.json`, evidence), JSON.stringify({ ...layout, palette }, null, 2))
    await checkLink(page).click()
    await dialog.getByRole('button', { name: 'Sair do assistente', exact: true }).click()
    await expect(page).toHaveURL('/insights')
    expect(await postCount(page)).toBe(2)
    await page.goBack()
    await expect(page.getByTestId('answer')).toHaveCount(0)
    expect(await postCount(page)).toBe(2)
  })
}

test('resposta concluída continua local e saída não abre aviso de resposta em andamento', async ({ page }) => {
  await assistant(page); await page.goto('/assistant'); await start(page)
  await frame(page, 'delta', { text: 'Resultado controlado.' }); await frame(page, 'done', { request_id: requestId }, true)
  await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible()
  await checkLink(page).click(); await expect(page).toHaveURL('/insights')
  await expect(exitDialog(page)).not.toBeVisible()
  await page.goBack(); await expect(page.getByTestId('answer')).toHaveCount(0)
  expect(await postCount(page)).toBe(1)
})

test('logout já solicitado termina com aviso aberto e remove conteúdo privado', async ({ page }) => {
  await assistant(page)
  let release!: () => void, started = false
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/auth/logout', async route => { started = true; await held; await route.fulfill({ status: 200 }) })
  await page.goto('/assistant'); await start(page, 'Pergunta privada de logout')
  await frame(page, 'delta', { text: 'Dados privados.' })
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect.poll(() => started).toBe(true)
  await checkLink(page).click(); await expect(exitDialog(page)).toBeVisible()
  release()
  await expect(page).toHaveURL(/\/login/)
  await expect(exitDialog(page)).toHaveCount(0)
  await expect(page.getByText('Dados privados.', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('coldsafe-session'))).toBeNull()
})

test('401 no stream prevalece sobre decisão pendente de saída', async ({ page }) => {
  await assistant(page); await page.goto('/assistant'); await start(page)
  await frame(page, 'delta', { text: 'Dados privados.' })
  await checkLink(page).click(); await expect(exitDialog(page)).toBeVisible()
  await frame(page, 'error', { code: 'UNAUTHORIZED' }, true)
  await expect(page).toHaveURL(/\/login/)
  await expect(exitDialog(page)).toHaveCount(0)
  await expect(page.getByText('Dados privados.', { exact: true })).toHaveCount(0)
})

test('403 HTTP do pedido pendente fecha o aviso mesmo conservando o token', async ({ page }) => {
  await assistant(page)
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v3/llm/ask', async route => { await held; await route.fulfill({ status: 403, json: { success: false, error: { code: 'FORBIDDEN' } } }) })
  await page.goto('/assistant')
  await page.evaluate(() => { (window as FixtureWindow).rd15Stream.enabled = false })
  await start(page, 'Pergunta privada sem permissão')
  await checkLink(page).click(); await expect(exitDialog(page)).toBeVisible()
  release()
  await expect(exitDialog(page)).not.toBeVisible()
  await expect(page.getByText('Seu acesso ao assistente não está autorizado.', { exact: true })).toBeVisible()
  await expect(page.getByText('Pergunta privada sem permissão', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('coldsafe-session')!).token)).toBe(token)
})

test('trocar conta com aviso aberto aborta stream e limpa conversa', async ({ page }) => {
  await assistant(page); await page.goto('/assistant'); await start(page, 'Pergunta antiga privada')
  await frame(page, 'delta', { text: 'Resposta da conta antiga.' })
  await checkLink(page).click(); await expect(exitDialog(page)).toBeVisible()
  await page.evaluate(async () => {
    const path = '/src/features/account/session.ts'
    const { setSession } = await import(path)
    setSession('rd15-new-account', '2099-01-01T00:00:00Z')
  })
  await expect(exitDialog(page)).not.toBeVisible()
  await expect(page.getByTestId('answer')).toHaveCount(0)
  await expect(question(page)).toHaveValue('')
  expect(await page.evaluate(() => (window as FixtureWindow).rd15Stream.aborts)).toBeGreaterThan(0)
})

test('recarregar durante resposta usa aviso nativo e permanecer conserva stream', async ({ page }) => {
  await assistant(page); await page.goto('/assistant'); await start(page)
  const native = page.waitForEvent('dialog')
  const reload = page.reload({ timeout: 2000 }).catch(() => null)
  const warning = await native
  expect(warning.type()).toBe('beforeunload'); await warning.dismiss(); await reload
  await expect(page.getByText('Resposta em andamento', { exact: true })).toBeVisible()
  await frame(page, 'delta', { text: 'A resposta continuou.' })
  await expect(page.getByTestId('answer')).toHaveText('A resposta continuou.')
  expect(await postCount(page)).toBe(1)
  await page.getByTestId('cancel').click()
})
