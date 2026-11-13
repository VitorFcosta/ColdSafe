import { mkdir, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import examples from '../../contracts/examples/aiot.valid.json' with { type: 'json' }
import { mockDashboardAccount } from './monitoring-api'

const evidence = new URL('../../.impeccable/review/ux-05/', import.meta.url)
const original = examples.find((item) => item.name === 'prediction_available_zero_rul')!.payload
const rules = { health_critical: 20, health_recovery: 40, rul_critical_hours: 10, rul_recovery_hours: 30, open_count: 2, close_count: 2 }
const panel = (page: Page) => page.getByRole('region', { name: 'Previsão do equipamento', exact: true })
const limits = (page: Page) => page.getByRole('region', { name: 'Limites preditivos', exact: true })
const alerts = (page: Page) => page.getByRole('region', { name: 'Alertas em aberto', exact: true })
const edit = (page: Page) => limits(page).getByRole('button', { name: 'Editar regras', exact: true })
const input = (page: Page, name: string) => limits(page).getByRole('spinbutton', { name, exact: true })

async function mockInsights(page: Page, role = 'operator') {
  await page.route('**/api/**', (route) => route.fulfill({ status: 503, json: { success: false } }))
  await mockDashboardAccount(page)
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { success: true, data: { user_id: 'test-user', email: 'test@example.com', role } } }))
  await page.route('**/api/v1/environments', (route) => route.fulfill({ json: { success: true, data: [{ id: original.environment_id, name: 'Laboratório refrigerado' }] } }))
  await page.route(`**/api/v1/environments/${original.environment_id}/devices`, (route) => route.fulfill({ json: { success: true, data: [{ id: original.device_record_id, environment_id: original.environment_id, name: 'Ventilador 01', mqtt_device_id: original.device_id, is_active: true }] } }))
  const state = { gets: 0, puts: 0, mode: 'available' as 'available' | 'unavailable' | 'no_data' | 'stale' | 'error', rules: { ...rules } }
  const receivedAt = new Date(Date.now() - 4000).toISOString()
  await page.route('**/api/v3/insights**', (route) => {
    if (route.request().method() === 'PUT') {
      state.puts++
      state.rules = route.request().postDataJSON()
      return route.fulfill({ json: { success: true, data: state.rules, meta: { schema_version: 3 } } })
    }
    state.gets++
    if (state.mode === 'error') return route.fulfill({ status: 503, json: { success: false } })
    const inputAt = state.mode === 'stale' ? new Date(Date.now() - 45000).toISOString() : receivedAt
    const prediction = { ...original, occurred_at: inputAt, received_at: inputAt, data: { ...original.data,
      input_received_at: inputAt, health_score: state.mode === 'unavailable' ? null : 0,
      rul_hours: state.mode === 'unavailable' ? null : 0, status: state.mode === 'unavailable' ? 'unavailable' : 'available',
      reason: state.mode === 'unavailable' ? 'insufficient_history' : null } }
    return route.fulfill({ json: { success: true, data: {
      device_id: original.device_id, equipment_id: original.data.equipment_id, rules: state.rules,
      prediction: state.mode === 'no_data' ? null : prediction, availability: state.mode,
      age_seconds: state.mode === 'stale' ? 45 : state.mode === 'no_data' ? null : 4,
      trend: state.mode === 'available' ? 'declining' : 'unknown', active_alerts: [{
        alert_id: '00000000-0000-4000-8000-000000000999', kind: 'predictive_failure',
        opened_at: new Date(Date.parse(receivedAt) - 120000).toISOString(), source_event_id: original.data.source_event_id, prediction_event_id: original.event_id,
      }],
    }, meta: { schema_version: 3 } } })
  })
  return state
}

async function capture(page: Page, name: string) {
  await mkdir(evidence, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.evaluate(() => scrollTo(0, 0))
  await page.screenshot({ path: new URL(`${name}.png`, evidence).pathname, fullPage: true })
  await page.screenshot({ path: new URL(`${name}-viewport.png`, evidence).pathname, fullPage: false })
}

for (const width of [1440, 390]) {
  test(`estimativas, origem, eventos e seis regras completas (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const state = await mockInsights(page)
    await page.goto(width === 390 ? '/insights/' : '/insights')
    await expect(page.getByRole('heading', { name: 'Saúde e previsões', exact: true })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Navegação da área', exact: true })).toHaveCount(1)
    await expect(panel(page)).toContainText('0 / 100')
    await expect(panel(page)).toContainText('0 h')
    await expect(panel(page)).toContainText('dados gerados para teste')
    await expect(panel(page)).toContainText('Idade da leitura')
    await expect(panel(page)).toContainText('Situação da última previsão Em queda')
    await expect(limits(page).getByRole('spinbutton')).toHaveCount(0)
    await expect(limits(page)).toContainText('2 previsões críticas seguidas com saúde ≤ 20 ou vida útil ≤ 10 h')
    await expect(limits(page)).toContainText('2 previsões de recuperação seguidas com saúde ≥ 40 e vida útil ≥ 30 h')
    const { prediction, alerts: eventsTop, rules: rulesTop } = await page.evaluate(() => ({
      prediction: document.querySelector('.estimates')!.getBoundingClientRect().top,
      alerts: document.querySelector('.alerts-panel')!.getBoundingClientRect().top,
      rules: document.querySelector('.rules-panel')!.getBoundingClientRect().top,
    }))
    if (width === 1440) {
      expect(eventsTop).toBe(prediction)
      expect(rulesTop).toBeLessThan(900)
    } else {
      expect(eventsTop).toBeGreaterThan(prediction)
    }
    expect(rulesTop).toBeGreaterThan(eventsTop)
    if (width === 1440) {
      await page.evaluate(() => document.querySelector('h1')?.blur())
      await capture(page, 'desktop')
    }
    const summary = panel(page).locator('summary')
    await expect(panel(page).getByText(original.data.model_version!, { exact: true })).toBeHidden()
    await summary.focus(); await page.keyboard.press('Enter')
    await expect(panel(page).getByText(original.data.model_version!, { exact: true })).toBeVisible()
    await expect(panel(page).getByText(original.data.equipment_id, { exact: true })).toBeVisible()
    await expect(panel(page).getByText(original.data.features_version!, { exact: true })).toBeVisible()
    const timeZone = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)
    await expect(panel(page)).toContainText(timeZone)
    const events = alerts(page)
    await events.locator('summary').focus(); await page.keyboard.press('Enter')
    await expect(events.getByText(original.data.source_event_id, { exact: true })).toBeVisible()
    await events.locator('summary').focus(); await page.keyboard.press('Enter')
    await summary.focus(); await page.keyboard.press('Enter')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await edit(page).focus()
    await page.keyboard.press('Enter')
    await expect(input(page, 'Saúde crítica')).toBeFocused()
    await expect(limits(page).getByRole('spinbutton')).toHaveCount(6)
    await expect(input(page, 'Saúde de recuperação')).toHaveValue('40')
    expect(state.puts).toBe(0)
    if (width === 1440) {
      await capture(page, 'edicao-desktop')
      const colors = await page.evaluate(() => ['.estimate-values dt', '.estimate-values dd', '.origin', '.persistent-alert', '.primary'].map((selector) => {
        const element = document.querySelector(selector)!, style = getComputedStyle(element)
        let ancestor: Element | null = element, background = 'rgba(0, 0, 0, 0)'
        while (ancestor && background === 'rgba(0, 0, 0, 0)') { background = getComputedStyle(ancestor).backgroundColor; ancestor = ancestor.parentElement }
        return { selector, color: style.color, background, fontSize: style.fontSize }
      }))
      await writeFile(new URL('rendered-colors.json', evidence), JSON.stringify({ browser: page.context().browser()!.version(), colors }, null, 2))
    }
  })
}

test('validação orienta foco; polling preserva rascunho; cancelar e salvar são ações distintas', async ({ page }) => {
  const state = await mockInsights(page)
  await page.goto('/insights')
  await edit(page).click()
  await input(page, 'Saúde de recuperação').fill('20')
  await page.getByRole('button', { name: 'Salvar regras', exact: true }).click()
  await expect(input(page, 'Saúde de recuperação')).toBeFocused()
  await expect(input(page, 'Saúde de recuperação')).toHaveAttribute('aria-invalid', 'true')
  await expect(page.getByText('A saúde de recuperação deve superar a saúde crítica.', { exact: true })).toBeVisible()
  expect(state.puts).toBe(0)
  await input(page, 'Saúde de recuperação').fill('45')
  await input(page, 'Previsões para abrir').fill('1.5')
  await page.getByRole('button', { name: 'Salvar regras', exact: true }).click()
  await expect(input(page, 'Previsões para abrir')).toBeFocused()
  await expect(page.getByText('Informe um número inteiro entre 1 e 100.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Cancelar edição', exact: true }).click()
  await expect(edit(page)).toBeFocused()
  await expect(limits(page).getByRole('form')).toHaveCount(0)
  await edit(page).click()
  await expect(input(page, 'Saúde de recuperação')).toHaveValue('40')
  await expect(input(page, 'Previsões para abrir')).toHaveValue('2')
  expect(state.puts).toBe(0)
  await input(page, 'Previsões para abrir').fill('4')
  state.rules = { ...state.rules, open_count: 6 }
  await expect(limits(page)).toContainText('6 previsões críticas')
  await expect(input(page, 'Previsões para abrir')).toBeFocused()
  await expect(input(page, 'Previsões para abrir')).toHaveValue('4')
  await expect(limits(page)).toContainText('Há alterações não salvas')
  await page.getByRole('navigation', { name: 'Navegação da área', exact: true }).getByRole('link', { name: 'Visão geral', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Descartar alterações?', exact: true })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Permanecer', exact: true }).click()
  await expect(input(page, 'Previsões para abrir')).toHaveValue('4')
  await page.getByRole('button', { name: 'Salvar regras', exact: true }).click()
  await expect(limits(page)).toContainText('Regras salvas')
  expect(state.puts).toBe(1)
  await expect(limits(page)).toContainText('4 previsões críticas')
  await expect(limits(page).getByRole('form')).toHaveCount(0)
  await expect(edit(page)).toBeFocused()
})

test('ausência, warm-up, expiração e falha não encerram alerta persistido', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  const state = await mockInsights(page)
  await page.goto('/insights')
  await expect(panel(page)).toContainText('0 h')
  for (const mode of ['no_data', 'unavailable', 'stale', 'error'] as const) {
    state.mode = mode
    const label = mode === 'no_data' ? 'Sem previsão' : mode === 'unavailable' ? 'Histórico insuficiente' : mode === 'stale' ? 'Previsão desatualizada' : 'Não foi possível atualizar'
    await expect(panel(page)).toContainText(label)
    await expect(panel(page)).not.toContainText('0 h')
    await expect(panel(page)).not.toContainText('0 / 100')
    await expect(alerts(page).getByText('Alerta preditivo', { exact: true })).toBeVisible()
    await expect(alerts(page)).not.toContainText(/crític|limite|vida útil/i)
    if (mode === 'no_data') await expect(panel(page)).toContainText('Sem leitura confirmada')
    if (mode === 'stale') {
      await expect(panel(page)).toContainText(/Há \d+ s/)
      await page.evaluate(() => document.querySelector('h1')?.blur())
      await capture(page, 'leitura-antiga')
    }
    if (mode === 'error') await expect(alerts(page)).toContainText('A lista é da última consulta.')
  }
})

test('viewer consulta os seis limites e eventos sem oferecer edição', async ({ page }) => {
  const state = await mockInsights(page, 'viewer')
  await page.goto('/insights')
  await expect(panel(page)).toContainText('0 h')
  await expect(limits(page).getByRole('spinbutton')).toHaveCount(0)
  await expect(limits(page).getByRole('button')).toHaveCount(0)
  await expect(limits(page)).toContainText('2 previsões críticas seguidas com saúde ≤ 20 ou vida útil ≤ 10 h')
  await expect(limits(page)).toContainText('2 previsões de recuperação seguidas com saúde ≥ 40 e vida útil ≥ 30 h')
  await expect(limits(page)).toContainText('Seu acesso é de leitura')
  expect(state.puts).toBe(0)
})

test('320 px/texto 200% conserva regras, erro associado, teclado e foco após polling', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const state = await mockInsights(page)
  state.mode = 'unavailable'
  await page.goto('/insights')
  await expect(panel(page)).toContainText('Histórico insuficiente')
  await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
  await edit(page).click()
  await input(page, 'Limite de recuperação (h)').fill('10')
  await page.getByRole('button', { name: 'Salvar regras', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(input(page, 'Limite de recuperação (h)')).toBeFocused()
  await expect(input(page, 'Limite de recuperação (h)')).toHaveAttribute('aria-describedby', /rule-rul_recovery_hours-error/)
  const before = state.gets
  await expect.poll(() => state.gets).toBeGreaterThan(before)
  await expect(input(page, 'Limite de recuperação (h)')).toHaveValue('10')
  await expect(input(page, 'Limite de recuperação (h)')).toBeFocused()
  const reflow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, fontSize: getComputedStyle(document.documentElement).fontSize, reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches }))
  expect(reflow.scrollWidth).toBe(320)
  await capture(page, 'mobile-320-text-200')
  await input(page, 'Limite de recuperação (h)').evaluate((element) => element.scrollIntoView({ block: 'center' }))
  await page.screenshot({ path: new URL('rule-error-320-text-200.png', evidence).pathname, fullPage: false })
  await writeFile(new URL('reflow.json', evidence), JSON.stringify(reflow, null, 2))
  expect(state.puts).toBe(0)
})
