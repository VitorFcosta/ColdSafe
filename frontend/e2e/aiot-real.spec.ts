import { execFileSync } from 'node:child_process'
import { expect, test, type Page } from '@playwright/test'

const api = process.env.DASHBOARD_REAL_API_URL ?? ''
const device = process.env.DASHBOARD_REAL_DEVICE ?? ''
const environment = process.env.DASHBOARD_REAL_ENVIRONMENT ?? ''
const password = process.env.DASHBOARD_REAL_PASSWORD ?? ''

test.skip(!process.env.DASHBOARD_REAL_URL || !api || !password || !process.env.DASHBOARD_REAL_COMPOSE,
  'Run the opt-in Python disposable dashboard integration harness')

function simulator(action: 'start' | 'stop') {
  const base: string[] = JSON.parse(process.env.DASHBOARD_REAL_COMPOSE!)
  execFileSync('docker', [...base, action, 'simulator'], { stdio: 'pipe', timeout: 30_000 })
}

async function login(page: Page, email = 'writer-test@example.invalid') {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Senha').fill(password)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente' })).toBeVisible()
}

async function callApi(page: Page, path: string, method = 'GET', body?: object) {
  return page.evaluate(async ({ api, path, method, body }) => {
    const token = JSON.parse(sessionStorage.getItem('coldsafe-session')!).token
    const response = await fetch(api + path, {
      method, headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    return { status: response.status, body: await response.json() }
  }, { api, path, method, body })
}

const setRole = (role: 'viewer' | 'operator') => execFileSync(process.env.DASHBOARD_REAL_PYTHON!, ['-c',
    'import os,psycopg; c=psycopg.connect(host=os.environ["POSTGRES_HOST"],port=os.environ["POSTGRES_PORT"],dbname=os.environ["POSTGRES_DB"],user=os.environ["POSTGRES_USER"],password=os.environ["POSTGRES_PASSWORD"]); c.execute("UPDATE users SET role=%s WHERE id=%s",(os.environ["DASHBOARD_TEST_ROLE"],os.environ["DASHBOARD_REAL_OWNER"])); c.commit(); c.close()',
  ], { env: { ...process.env, DASHBOARD_TEST_ROLE: role }, stdio: 'pipe' })

test('sensor real chega a seis medições, gráfico e tabela; LED aguarda ACK; buzzer segue regra', async ({ page }) => {
  await login(page)
  // Keep the real sensor stopped so UI values and the pending command are observable.
  simulator('stop')
  const snapshot = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
  expect(snapshot.status).toBe(200)
  const measurements = snapshot.body.data.telemetry.data.measurements
  const sensors = [
    ['Temperatura', 'ambient_temperature', '°C'], ['Umidade', 'humidity', '%'],
    ['Luminosidade', 'light', '%'], ['Vibração RMS', 'vibration', 'mm/s'],
    ['Corrente do motor', 'motor_current', 'A'], ['Temperatura do motor', 'motor_temperature', '°C'],
  ] as const
  for (const [label, role, unit] of sensors) {
    const article = page.getByRole('article').filter({ hasText: label }).first()
    const precision = ['vibration', 'motor_current', 'motor_temperature'].includes(role) ? 3 : 1
    await expect(article).toContainText(`${Number(measurements[role].value).toLocaleString('pt-BR', { maximumFractionDigits: precision })} ${unit}`)
  }
  await expect(page.getByRole('heading', { name: 'Variação recente' })).toBeVisible()
  await expect(page.getByRole('img', { name: 'Gráfico de linha da temperatura no período selecionado' })).toBeVisible()
  const history = page.locator('details').filter({ hasText: /Ver \d+ leituras? em tabela/ })
  await history.locator('summary').click()
  await expect(page.getByRole('table', { name: /Leituras individuais/ })).toBeVisible()
  expect(await page.getByRole('table', { name: /Leituras individuais/ }).getByRole('row').count()).toBeGreaterThan(1)

  const actuators = page.locator('details[aria-label="Estado dos atuadores"]')
  await actuators.locator('summary').click()
  const before = snapshot.body.data.telemetry.data.actuators.led.actual_state
  const button = actuators.getByRole('button', { name: before ? 'Desligar Luz' : 'Ligar Luz' })
  await button.focus()
  await page.keyboard.press('Enter')
  await expect(actuators).toContainText('Aguardando confirmação')
  await expect(button).toBeDisabled()
  const pending = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
  expect(pending.body.data.commands.led.data.status).toBe('pending')
  expect(pending.body.data.telemetry.data.actuators.led.actual_state).toBe(before)
  expect((await callApi(page, `/api/v1/environments/${environment}/rules`, 'PUT',
    { min_c: -50, max_c: -40, attention_margin_c: 1 })).status).toBe(200)
  simulator('start')
  try {
    // MQTT publication while the clean-session device was offline is not an actuator ACK.
    await expect.poll(async () => {
      const current = await callApi(page, `/api/v3/commands/${pending.body.data.commands.led.data.command_id}`)
      return current.body.data.data.status
    }, { timeout: 35_000 }).toBe('unconfirmed')
    await expect(actuators.getByRole('button', { name: before ? 'Desligar Luz' : 'Ligar Luz' })).toBeEnabled()
    await actuators.getByRole('button', { name: before ? 'Desligar Luz' : 'Ligar Luz' }).click()
    await expect(actuators.getByRole('button', { name: before ? 'Ligar Luz' : 'Desligar Luz' })).toBeEnabled()
    await expect.poll(async () => {
      const current = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
      return {
        led: current.body.data.commands.led?.data.status,
        actual: current.body.data.telemetry.data.actuators.led.actual_state,
        buzzer: current.body.data.commands.buzzer?.data.status,
        sound: current.body.data.telemetry.data.actuators.buzzer.actual_state,
      }
    }, { timeout: 25_000 }).toEqual({ led: 'confirmed', actual: !before, buzzer: 'confirmed', sound: true })
    await expect(actuators.getByText('Ligado', { exact: true }).first()).toBeVisible()
  } finally {
    await callApi(page, `/api/v1/environments/${environment}/rules`, 'PUT',
      { min_c: 2, max_c: 8, attention_margin_c: 0.5 })
  }
})

test('mobile teclado e perda real de rede envelhecem leitura; REST recupera após reconexão', async ({ page, context }) => {
  simulator('start')
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page)
  for (const name of ['Ambiente', 'Dispositivo']) {
    const selection = page.getByRole('combobox', { name })
    await expect(selection).toBeEnabled()
    await selection.focus()
    await expect(selection).toBeFocused()
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
  }
  const history = page.locator('details').filter({ hasText: /Ver \d+ leituras? em tabela/ })
  await history.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(history).toHaveAttribute('open', '')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 390)).toBe(true)
  await expect(page.getByText('Agora mesmo', { exact: true })).toBeVisible()
  const before = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
  await context.setOffline(true)
  try {
    await expect(page.getByRole('heading', { name: 'Leitura desatualizada', exact: true })).toBeVisible({ timeout: 45_000 })
  } finally {
    const recovered = page.waitForResponse(response => response.url().includes('/api/v3/monitoring/summary') && response.ok())
    await context.setOffline(false)
    await recovered
  }
  const after = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
  expect(Date.parse(after.body.data.telemetry.received_at)).toBeGreaterThan(Date.parse(before.body.data.telemetry.received_at))
  try {
    await expect(page.getByText('Agora mesmo', { exact: true })).toBeVisible()
  } catch (error) {
    console.log('Recovery freshness:', after.body.data.freshness,
      'UI:', await page.locator('section[aria-label="Diagnóstico atual"]').innerText())
    throw error
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 390)).toBe(true)
})

test('conta visualizadora real não comanda e não acessa o dispositivo do operador', async ({ page }) => {
  await login(page, 'dashboard-viewer@example.invalid')
  await expect(page.getByRole('combobox', { name: 'Ambiente' })).toContainText('Viewer environment')
  const actuators = page.locator('details[aria-label="Estado dos atuadores"]')
  await actuators.locator('summary').click()
  await expect(page.getByText('Modo visualizador: você pode consultar o estado dos atuadores.')).toBeVisible()
  await expect(actuators.getByRole('button', { name: 'Ligar Luz' })).toBeDisabled()
  const denied = await callApi(page, '/api/v3/devices/dashboard-viewer-device/led/commands', 'POST', { desired_state: true })
  expect(denied.status).toBe(403)
  expect((await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)).status).toBe(404)
})

test('visualizador do equipamento configurado lê sensores e gráfico sem comandar', async ({ page }) => {
  setRole('viewer')
  try {
    simulator('start')
    await login(page)
    await expect(page.getByRole('heading', { name: 'Vibração RMS', exact: true })).toBeVisible()
    await expect(page.getByRole('img', { name: 'Gráfico de linha da temperatura no período selecionado' })).toBeVisible()
    const actuators = page.locator('details[aria-label="Estado dos atuadores"]')
    await actuators.locator('summary').click()
    await expect(actuators.getByRole('button', { name: /Ligar Luz|Desligar Luz/ })).toBeDisabled()
    expect((await callApi(page, `/api/v3/devices/${device}/led/commands`, 'POST', { desired_state: false })).status).toBe(403)
  } finally {
    setRole('operator')
  }
})

test('gêmeo digital real congela após parar simulador com WebSocket aberto e retoma com dados novos', async ({ page }) => {
  simulator('start')
  await login(page)
  const socketPromise = page.waitForEvent('websocket', (socket) => socket.url().includes('/api/v3/events?'))
  await page.locator('nav a[href="/digital-twin"]').click()
  const socket = await socketPromise
  let closed = false
  socket.on('close', () => { closed = true })
  const list = page.getByRole('region', { name: 'Componentes do gêmeo digital', exact: true })
  const canvas = page.locator('[data-testid=twin-scene] canvas')
  await expect(list.getByRole('button')).toHaveCount(9)
  await expect(list.getByRole('button', { name: /^Ventilador/ })).toContainText('Em operação')
  await expect(canvas).toBeVisible()
  const before = await canvas.screenshot()
  await expect.poll(async () => (await canvas.screenshot()).equals(before)).toBe(false)
  simulator('stop')
  try {
    await expect(page.getByRole('status').filter({ hasText: 'Cena congelada' })).toBeVisible({ timeout: 45_000 })
    await expect(page.getByRole('status').filter({ hasText: 'Leitura desatualizada' })).toBeVisible()
    for (const button of await list.getByRole('button').all()) await expect(button).toContainText('Sem dados atuais')
    const snapshot = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
    expect(snapshot.body.data.freshness.state).toBe('stale')
    expect(snapshot.body.data.freshness.age_seconds).toBeGreaterThan(30)
    expect(socket.isClosed()).toBe(false)
    expect(closed).toBe(false)
    const frozen = await canvas.screenshot({ path: '/tmp/coldsafe-b228/twin-real-stale.png' })
    await page.waitForTimeout(750)
    expect((await canvas.screenshot()).equals(frozen)).toBe(true)
  } finally {
    simulator('start')
  }
  await expect(page.getByRole('status').filter({ hasText: 'Cena congelada' })).toHaveCount(0)
  await expect(list.getByRole('button', { name: /^Ventilador/ })).toContainText('Em operação')
  const resumed = await canvas.screenshot({ path: '/tmp/coldsafe-b228/twin-real-resumed.png' })
  await expect.poll(async () => (await canvas.screenshot()).equals(resumed)).toBe(false)
  expect(closed).toBe(false)
})

test('painel 3D real inspeciona nove IDs, comanda LED e servidor recusa papel revogado', async ({ page }) => {
  simulator('start')
  await login(page)
  await page.locator('nav a[href="/digital-twin"]').click()
  const list = page.getByRole('region', { name: 'Componentes do gêmeo digital', exact: true })
  const panel = page.getByRole('region', { name: 'Detalhes do componente', exact: true })
  await expect(list.getByRole('button')).toHaveCount(9)
  for (const button of await list.getByRole('button').all()) {
    await button.click()
    const name = (await button.locator('strong').textContent())!
    await expect(panel.getByRole('heading', { level: 2 }).first()).toHaveText(name)
    await expect(panel).toContainText('Idade da leitura')
    await expect(panel.getByRole('img', { name: /Gráfico de linha/ })).toHaveCount(1)
    if (name !== 'Ventilador') await expect(panel).toContainText('Saúde/RUL deste item: não aplicável')
    await expect(panel.getByText('Saúde estimada', { exact: true })).toHaveCount(0)
  }
  await list.getByRole('button', { name: /^LED/ }).click()
  const control = panel.getByRole('region', { name: 'Controle do LED selecionado' })
  const snapshot = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
  const before = snapshot.body.data.commands.led?.data.confirmed_state === true
  await control.getByRole('button', { name: before ? 'Desligar Luz' : 'Ligar Luz' }).click()
  await expect(control.getByRole('button', { name: before ? 'Ligar Luz' : 'Desligar Luz' })).toBeEnabled({ timeout: 25_000 })
  await expect(list.getByRole('button', { name: /^LED/ })).toContainText(!before ? 'Ligado' : 'Desligado')
  const ack = await callApi(page, `/api/v3/monitoring/summary?device_id=${device}`)
  expect(ack.body.data.commands.led.data.status).toBe('confirmed')
  expect(ack.body.data.telemetry.data.actuators.led.actual_state).toBe(!before)
  await page.screenshot({ path: '/tmp/coldsafe-b229/twin-real-led.png', fullPage: true })
  setRole('viewer')
  try {
    // The browser still caches operator; current server-side role must reject the POST.
    await control.getByRole('button', { name: before ? 'Ligar Luz' : 'Desligar Luz' }).click()
    await expect(control).toContainText('Não foi possível enviar o comando')
    expect((await callApi(page, `/api/v3/devices/${device}/led/commands`, 'POST', { desired_state: before })).status).toBe(403)
    await page.reload()
    await list.getByRole('button', { name: /^LED/ }).click()
    await expect(control).toContainText('Modo visualizador')
    await expect(control.getByRole('button', { name: /Ligar Luz|Desligar Luz/ })).toBeDisabled()
    expect((await callApi(page, '/api/v3/monitoring/summary?device_id=dashboard-viewer-device')).status).toBe(404)
  } finally {
    setRole('operator')
  }
})
