import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { createHash, randomUUID } from 'node:crypto'
import { mkdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { chromium, expect } from '@playwright/test'

// Runs only against the explicitly supplied private rehearsal state; never installs a session.
const phases = ['roles', 'docs', 'dashboard', 'actuators', 'messaging', 'laboratory', 'training', 'fault', 'assistant']
const labels = ['Umidade', 'Luminosidade', 'Vibração RMS', 'Corrente do motor', 'Temperatura do motor']
const phase = process.argv[2]
let browser
let checkpoint = 'input'
const sensitive = []
const captureId = `${Date.now()}-${randomUUID().slice(0, 8)}`
const output = { phase, real_browser: true, mocked_requests: false, session_injection: false }

function validateState(value) {
  const url = new URL(value.url)
  assert(['http:', 'https:'].includes(url.protocol) && !url.username && !url.password)
  assert(['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname), 'Rehearsal URL must use loopback')
  assert(typeof value.output_dir === 'string' && value.output_dir.length)
  for (const role of ['admin', 'operator', 'viewer']) {
    assert(typeof value.accounts?.[role]?.email === 'string')
    assert(typeof value.accounts[role].password === 'string' && value.accounts[role].password.length)
  }
  assert(value.catalog?.device_id && value.catalog.environment_id && value.catalog.device_record_id)
  return value
}

function composeBase(state) {
  assert(/^coldsafe-b236-[a-f0-9]{8}$/.test(state.project), 'Disposable rehearsal project required')
  const base = state.base
  assert(Array.isArray(base) && base.every(value => typeof value === 'string'))
  assert.deepEqual(base.slice(0, 4), ['docker', 'compose', '-p', state.project])
  assert.equal((base.length - 4) % 2, 0)
  for (let index = 4; index < base.length; index += 2) {
    assert(['--env-file', '-f', '--profile'].includes(base[index]))
    assert(base[index + 1] && !base[index + 1].startsWith('-'))
    if (base[index] === '--profile') assert(['aiot', 'simulator'].includes(base[index + 1]))
  }
  return base
}

function loginRetryMilliseconds(header) {
  const seconds = Number(header)
  assert(Number.isInteger(seconds) && seconds >= 1 && seconds <= 900, 'Invalid login Retry-After')
  return seconds * 1000
}

async function main() {
  if (phase === '--self-check') {
    assert.equal(new Set(phases).size, 9)
    const fixture = { url: 'http://127.0.0.1:5173', output_dir: '/tmp/rehearsal',
      accounts: Object.fromEntries(['admin', 'operator', 'viewer'].map(role => [role, { email: `${role}@example.invalid`, password: 'fixture-only' }])),
      catalog: { device_id: 'sim-lab-01', environment_id: 'environment', device_record_id: 'device' } }
    assert.equal(validateState(fixture), fixture)
    assert.throws(() => validateState({ ...fixture, url: 'http://user:secret@localhost' }))
    assert.throws(() => validateState({ ...fixture, accounts: {} }))
    assert.throws(() => validateState({ ...fixture, url: 'https://example.com' }))
    assert.throws(() => validateState({ ...fixture, url: 'http://localhost.example.com' }))
    assert.equal(validateState({ ...fixture, url: 'http://[::1]:5173' }).url, 'http://[::1]:5173')
    const docker = { project: 'coldsafe-b236-1234abcd', base: ['docker', 'compose', '-p', 'coldsafe-b236-1234abcd'] }
    assert.deepEqual(composeBase(docker), docker.base)
    assert.throws(() => composeBase({ ...docker, project: 'personal-project' }))
    assert.throws(() => composeBase({ ...docker, base: [...docker.base, 'down', '--volumes'] }))
    assert.equal(loginRetryMilliseconds('60'), 60_000)
    for (const value of [undefined, '', '0', '-1', '901', 'later', '1.5']) assert.throws(() => loginRetryMilliseconds(value))
    console.log(JSON.stringify({ self_check: 'passed', cases: 18 }))
    return
  }
  assert(phases.includes(phase))
  assert(process.env.COLDSAFE_REHEARSAL_STATE)
  const state = validateState(JSON.parse(await readFile(process.env.COLDSAFE_REHEARSAL_STATE, 'utf8')))
  sensitive.push(...Object.values(state.accounts).flatMap(account => [account.password, account.email]))
  const origin = new URL(state.url).origin
  await mkdir(state.output_dir, { recursive: true })
  browser = await chromium.launch({ headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
  const started = Date.now()

  async function login(role = 'admin') {
    checkpoint = `login-${role}`
    const context = await browser.newContext({ baseURL: state.url, viewport: { width: 1440, height: 1000 },
      reducedMotion: phase === 'fault' ? 'no-preference' : 'reduce' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.name))
    await page.goto('/login')
    const loginDeadline = Date.now() + 600_000
    let authenticated
    while (true) {
      await page.getByLabel('Email', { exact: true }).fill(state.accounts[role].email)
      await page.getByLabel('Senha', { exact: true }).fill(state.accounts[role].password)
      const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/auth/login' && r.request().method() === 'POST')
      await page.getByRole('button', { name: 'Entrar', exact: true }).click()
      authenticated = await response
      if (authenticated.status() !== 429) break
      const delay = loginRetryMilliseconds(authenticated.headers()['retry-after'])
      assert(Date.now() + delay <= loginDeadline, 'Login rate-limit wait exceeds the rehearsal budget')
      output.login_rate_limit_waits = [...(output.login_rate_limit_waits ?? []), { role, at: new Date().toISOString(), seconds: delay / 1000 }]
      for (let remaining = delay; remaining > 0; remaining -= 30_000) await page.waitForTimeout(Math.min(30_000, remaining))
    }
    assert.equal(authenticated.status(), 200, `UI login HTTP ${authenticated.status()}; Retry-After=${authenticated.headers()['retry-after'] ?? 'absent'}`)
    const token = (await authenticated.json()).data.token
    assert(typeof token === 'string' && token.length)
    sensitive.push(token)
    await expect(page.getByRole('heading', { name: 'Visão geral', exact: true })).toBeVisible({ timeout: 30_000 })
    const api = (path, method = 'GET', body) => page.evaluate(async ({ origin, path, token, method, body }) => {
      const result = await fetch(origin + path, { method,
        headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
      return { status: result.status, body: await result.json() }
    }, { origin, path, token, method, body })
    const identity = await api('/api/v1/auth/me')
    assert.equal(identity.status, 200)
    assert.equal(identity.body.data.role, role)
    return { page, api, context, errors }
  }

  async function shot(page, suffix = phase) {
    const filename = `${suffix}-${captureId}.png`
    // Long message samples can exceed Chromium's full-page capture surface.
    await page.screenshot({ path: join(state.output_dir, filename), fullPage: false })
    output.screenshots = [...(output.screenshots ?? []), filename]
  }

  async function select(page) {
    const environment = page.getByRole('combobox', { name: 'Ambiente', exact: true })
    await expect(environment).toBeEnabled({ timeout: 30_000 })
    await environment.selectOption(state.catalog.environment_id)
    const device = page.getByRole('combobox', { name: 'Dispositivo', exact: true })
    await expect(device).toBeEnabled()
    await device.selectOption(state.catalog.device_record_id)
  }

  if (phase === 'roles') {
    output.roles = []
    for (const role of ['viewer', 'operator', 'admin']) {
      const { page, api, context } = await login(role)
      checkpoint = `permissions-${role}`
      await page.goto('/laboratory')
      if (role === 'admin') {
        await expect(page.getByRole('heading', { name: 'Dados sintéticos', exact: true })).toBeVisible()
        await expect(page.getByRole('button', { name: 'Gerar dados de teste', exact: true })).toBeVisible()
      } else {
        await expect(page.getByRole('heading', { name: 'Acesso restrito', exact: true })).toBeVisible()
        await expect(page.getByRole('link', { name: 'Voltar ao Monitoramento', exact: true })).toBeVisible()
        await expect(page.getByRole('button', { name: 'Gerar dados de teste', exact: true })).toHaveCount(0)
      }
      const metrics = await api('/api/v3/messaging')
      assert.equal(metrics.status, role === 'admin' ? 200 : 403)
      const privateSnapshot = await api(`/api/v3/monitoring/summary?device_id=${encodeURIComponent(state.catalog.device_id)}`)
      assert.equal(privateSnapshot.status, role === 'admin' ? 200 : 404)
      let writeStatus = null
      if (role === 'viewer') {
        writeStatus = (await api(`/api/v3/devices/${encodeURIComponent(state.catalog.device_id)}/led/commands`, 'POST', { desired_state: true })).status
        assert.equal(writeStatus, 403)
      }
      await shot(page, `roles-${role}`)
      await page.goto('/manage')
      const addEnvironment = page.getByRole('button', { name: 'Adicionar ambiente', exact: true })
      if (role === 'viewer') await expect(addEnvironment).toHaveCount(0)
      else { await expect(addEnvironment).toBeVisible(); await expect(addEnvironment).toBeEnabled() }
      await shot(page, `roles-${role}-cadastro`)
      output.roles.push({ role, ui_login: true, administrative_metrics_status: metrics.status,
        live_owner_snapshot_status: privateSnapshot.status, viewer_write_status: writeStatus,
        own_catalog_write_controls_enabled: role !== 'viewer' })
      await context.close()
    }
  } else {
    const { page, api, context, errors } = await login()
    checkpoint = phase
    const monitoring = `/api/v3/monitoring/summary?device_id=${encodeURIComponent(state.catalog.device_id)}`
    if (phase === 'docs') {
      const externalRequests = []
      await page.route('**/*', route => {
        const url = new URL(route.request().url())
        if (url.origin === origin) return route.continue()
        externalRequests.push({ origin: url.origin, path: url.pathname })
        return route.abort('blockedbyclient')
      })
      const response = await page.goto('/docs')
      assert.equal(response.status(), 200)
      await expect(page.getByRole('heading', { name: /ColdSafe Monitoring API/ })).toBeVisible({ timeout: 30_000 })
      await expect(page.locator('.opblock').first()).toBeVisible()
      const schema = await api('/openapi.json')
      assert.equal(schema.status, 200)
      for (const path of ['/api/v1/auth/login', '/api/v3/monitoring/summary', '/api/v3/jobs', '/api/v3/llm/ask']) assert(schema.body.paths[path])
      const sources = await page.locator('script[src],link[href]').evaluateAll(elements => elements.map(element => element.src || element.href))
      assert(sources.every(source => new URL(source).origin === origin))
      const assets = []
      for (const [path, mime] of [['/docs-assets/swagger-ui-bundle.js', /javascript/], ['/docs-assets/swagger-ui.css', /text\/css/], ['/docs-assets/favicon-32x32.png', /image\/png/]]) {
        assert(sources.some(source => new URL(source).pathname === path))
        const asset = await context.request.get(path)
        assert.equal(asset.status(), 200)
        assert.match(asset.headers()['content-type'], mime)
        assets.push({ path, status: asset.status(), content_type: asset.headers()['content-type'] })
      }
      assert.equal(await page.evaluate(() => ui.getConfigs().validatorUrl), null)
      assert.equal(externalRequests.length, 0)
      output.openapi = { title: schema.body.info.title, version: schema.body.info.version,
        route_count: Object.keys(schema.body.paths).length, sources, assets, external_requests: externalRequests,
        external_network_blocked: true, validator_url: null }
    } else if (phase === 'dashboard') {
      const telemetry = []
      const sockets = []
      page.on('websocket', socket => {
        sockets.push(socket)
        socket.on('framereceived', ({ payload }) => {
          try {
            const frame = JSON.parse(String(payload))
            if (frame.type === 'telemetry' && frame.device_id === state.catalog.device_id) telemetry.push(frame)
          } catch { /* Non-JSON WebSocket control frames are not telemetry evidence. */ }
        })
      })
      await page.goto('/dashboard')
      await select(page)
      for (const label of labels) await expect(page.getByRole('heading', { name: label, exact: true })).toBeVisible()
      await expect(page.getByRole('img', { name: 'Gráfico de linha da temperatura no período selecionado', exact: true })).toBeVisible()
      await expect(page.getByText('Conexão com servidor: conectada.', { exact: false })).toBeVisible()
      await expect.poll(() => new Set(telemetry.map(item => item.event_id)).size, { timeout: 35_000 }).toBeGreaterThanOrEqual(2)
      const snapshot = await api(monitoring)
      assert.equal(snapshot.status, 200)
      assert.equal(snapshot.body.data.freshness.state, 'fresh')
      assert.equal(Object.keys(snapshot.body.data.telemetry.data.measurements).length, 6)
      const history = page.locator('details').filter({ hasText: /Ver \d+ leituras? em tabela/ })
      await history.locator('summary').click()
      await expect(page.getByRole('table', { name: /Leituras individuais/ })).toBeVisible()
      assert(await page.getByRole('table', { name: /Leituras individuais/ }).getByRole('row').count() > 1)
      output.dashboard = { snapshot: snapshot.body.data, websocket_telemetry_events: telemetry.slice(-2).map(({ event_id, received_at }) => ({ event_id, received_at })) }
      checkpoint = 'dashboard-reconnect'
      const base = composeBase(state)
      const frontendPort = async () => (await promisify(execFile)(base[0], [...base.slice(1), 'port', 'frontend', '8080'], { timeout: 15_000 })).stdout.trim()
      const frontend = action => promisify(execFile)(base[0], [...base.slice(1), action, ...(action === 'stop' ? ['--timeout', '10'] : []), 'frontend'], { timeout: 40_000 })
      const portBefore = await frontendPort()
      assert.equal(Number(portBefore.split(':').at(-1)), Number(new URL(state.url).port), 'Frontend must match the explicit rehearsal URL')
      const connectedSocket = sockets.at(-1)
      assert(connectedSocket && !connectedSocket.isClosed())
      const socketsBefore = sockets.length
      try {
        // Chromium offline emulation retains established sockets; stop only this disposable proxy.
        await frontend('stop')
        await expect.poll(() => connectedSocket.isClosed(), { timeout: 15_000 }).toBe(true)
        await expect(page.getByText(/Conexão com servidor: desconectada/)).toBeVisible({ timeout: 15_000 })
      } finally { await frontend('start') }
      assert.equal(await frontendPort(), portBefore, 'Pin the disposable frontend port before testing reconnection')
      await expect(page.getByText('Conexão com servidor: conectada.', { exact: false })).toBeVisible({ timeout: 30_000 })
      assert(sockets.length > socketsBefore)
      assert(!sockets.at(-1).isClosed())
      await expect.poll(async () => (await api(monitoring)).body.data.telemetry.event_id,
        { timeout: 30_000 }).not.toBe(snapshot.body.data.telemetry.event_id)
      const restored = await api(monitoring)
      assert.equal(restored.body.data.freshness.state, 'fresh')
      output.dashboard.restored_http_snapshot = restored.body.data
      output.dashboard.network_reconnect = true
      output.dashboard.frontend_port_preserved = true
      output.dashboard.reconnect_mechanism = 'stop/start disposable frontend proxy; backend and simulator remain running'
    } else if (phase === 'actuators') {
      assert.equal(typeof state.desired_led_state, 'boolean')
      await page.goto('/dashboard')
      await select(page)
      const actuators = page.locator('details[aria-label="Estado da luz e do som de aviso"]')
      await actuators.locator('summary').click()
      const button = actuators.getByRole('button', { name: state.desired_led_state ? 'Ligar Luz' : 'Desligar Luz', exact: true })
      await expect(button).toBeEnabled({ timeout: 30_000 })
      const submitted = page.waitForResponse(response => new URL(response.url()).pathname ===
        `/api/v3/devices/${encodeURIComponent(state.catalog.device_id)}/led/commands` && response.request().method() === 'POST')
      await button.click()
      const response = await submitted
      assert.equal(response.status(), 200)
      const command = (await response.json()).data.data
      assert.equal(command.desired_state, state.desired_led_state)
      assert(command.command_id)
      await expect(actuators.getByRole('button', { name: state.desired_led_state ? 'Desligar Luz' : 'Ligar Luz', exact: true })).toBeEnabled({ timeout: 35_000 })
      await expect(actuators).toContainText(`Luz observada na última leitura: ${state.desired_led_state ? 'Ligado' : 'Desligado'}`, { timeout: 35_000 })
      await expect.poll(async () => (await api(monitoring)).body.data.telemetry.data.actuators.led.actual_state,
        { timeout: 35_000 }).toBe(state.desired_led_state)
      output.command_id = command.command_id
      output.actuators = { ui_button_clicked: true, desired_state: state.desired_led_state,
        confirmed: (await api(`/api/v3/commands/${command.command_id}`)).body.data,
        observed: (await api(monitoring)).body.data.telemetry }
    } else if (phase === 'messaging') {
      await page.goto('/messaging')
      const table = page.getByRole('region', { name: /Métricas por fila/ })
      await expect(table).toBeVisible({ timeout: 30_000 })
      await expect(table.getByRole('rowheader').getByText('coldsafe.writer', { exact: true })).toBeVisible()
      const metrics = await api('/api/v3/messaging')
      const samples = await api('/api/v3/messaging/messages')
      assert.equal(metrics.status, 200)
      assert.equal(samples.status, 200)
      const writer = metrics.body.data.queues.find(queue => queue.name === 'coldsafe.writer')
      assert(writer)
      if (state.expect_writer_backlog !== undefined) assert.equal(writer.messages_ready > 0, state.expect_writer_backlog)
      output.messaging = { metrics: metrics.body.data, observed_messages: samples.body.data.messages.length,
        observed_dead_letters: samples.body.data.dead_letters.length }
    } else if (phase === 'laboratory' || phase === 'training') {
      const generation = phase === 'laboratory'
      let id = generation ? state.generation_job_id : state.training_job_id
      await page.goto(`/${phase}${id ? `?job=${encodeURIComponent(id)}` : state.dataset_id && !generation ? `?dataset=${encodeURIComponent(state.dataset_id)}` : ''}`)
      await expect(page.getByRole('heading', { name: generation ? 'Dados sintéticos' : 'Treinamento de modelos', exact: true })).toBeVisible()
      if (!id && state.action === 'create') {
        if (generation) {
          await page.getByLabel('Linhas', { exact: true }).fill('1000000')
          await page.getByText('Opções avançadas', { exact: true }).click()
          await page.getByLabel('Semente', { exact: true }).fill(String(state.seed ?? 42))
        } else {
          assert(state.dataset_id)
          await page.getByLabel('Dataset', { exact: true }).selectOption(state.dataset_id)
        }
        const submitted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v3/jobs' && response.request().method() === 'POST')
        const submit = page.getByRole('button', { name: generation ? 'Gerar dados de teste' : 'Iniciar treinamento', exact: true })
        await expect(submit).toBeEnabled()
        const llmStates = []
        let sampling = true
        const observeLlm = generation ? (async () => {
          while (sampling) {
            const status = await api('/api/v3/llm/status')
            llmStates.push({ at: new Date().toISOString(), state: status.body?.data?.state ?? 'unavailable' })
            await new Promise(resolve => setTimeout(resolve, 150))
          }
        })() : Promise.resolve()
        try {
          await submit.click()
          const response = await submitted
          assert.equal(response.status(), 202)
          id = (await response.json()).data.id
          if (generation) await expect.poll(() => llmStates.some(item => item.state === 'paused'),
            { timeout: 10_000, intervals: [150] }).toBe(true)
        } finally { sampling = false; await observeLlm }
        output.llm_states = llmStates
      }
      assert(id, 'An existing job ID or explicit action=create is required')
      await expect(page.getByText(id, { exact: false }).first()).toBeVisible()
      if (state.wait_for_completion !== false) {
        await expect(page.getByRole('heading', { name: generation ? 'Dataset concluído' : 'Resultado do pacote', exact: true })).toBeVisible({ timeout: generation ? 180_000 : 600_000 })
      }
      const job = await api(`/api/v3/jobs/${id}`)
      assert.equal(job.status, 200)
      output.job = job.body.data
      output.job_id = id
      if (state.wait_for_completion !== false) {
        assert.equal(job.body.data.status, 'completed')
        const result = await api(generation ? `/api/v3/datasets/${job.body.data.result_id}` : `/api/v3/jobs/${id}/result`)
        assert.equal(result.status, 200)
        if (generation) {
          assert(result.body.data.row_count >= 1_000_000)
          await page.getByRole('button', { name: 'Ver amostra', exact: true }).click()
          await expect(page.getByRole('heading', { name: 'Amostra sintética separada', exact: true })).toBeVisible()
        } else {
          for (const name of ['Saúde', 'Vida útil restante (RUL)']) {
            const region = page.getByRole('region', { name: `Resultados de ${name}`, exact: true })
            await expect(region).toBeVisible()
            await expect(region.getByRole('img').first()).toBeVisible()
            await expect(region).toContainText('RMSE')
          }
        }
        output.result = result.body.data
      }
    } else if (phase === 'fault') {
      let uiInsights = null
      page.on('response', async response => {
        const url = new URL(response.url())
        if (url.origin === origin && url.pathname === '/api/v3/insights' &&
            url.searchParams.get('device_id') === state.catalog.device_id && response.request().method() === 'GET' && response.status() === 200) {
          try { uiInsights = (await response.json()).data }
          catch {
            uiInsights = null
            output.insights_response_read_failures = (output.insights_response_read_failures ?? 0) + 1
          }
        }
      })
      await page.goto('/insights')
      await select(page)
      const panel = page.getByRole('region', { name: 'Previsão do equipamento', exact: true })
      await expect(panel).toBeVisible()
      const metric = label => panel.locator('dl > div').filter({ has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) }).locator('dd')
      let observedInsights
      await expect.poll(async () => {
        const observed = uiInsights
        if (!observed) return false
        if (observed.availability === 'available') {
          const prediction = observed.prediction.data
          const format = value => value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })
          const expected = [`${format(prediction.health_score)} / 100`, `${format(prediction.rul_hours)} h`, prediction.model_version,
            { improving: 'Em recuperação', declining: 'Em queda', stable: 'Estável', unknown: 'Desconhecida' }[observed.trend]]
          const actual = await Promise.all(['Saúde', 'RUL', 'Versão do modelo', 'Tendência'].map(label => metric(label).innerText()))
          if (JSON.stringify(actual) !== JSON.stringify(expected)) return false
        } else if (observed.availability === 'stale') {
          if (await metric('Saúde').innerText() !== '—' || await metric('RUL').innerText() !== '—') return false
        }
        observedInsights = observed
        return true
      }, { timeout: 30_000 }).toBe(true)
      const insights = { body: { data: observedInsights } }
      if (state.require_prediction) assert.equal(observedInsights.availability, 'available')
      const availability = observedInsights.availability
      if (availability === 'available') {
        await expect(panel.getByText('Previsão disponível', { exact: true })).toBeVisible()
      } else if (availability === 'stale') {
      await expect(panel.getByText('Previsão desatualizada. Aguardando uma leitura recente.', { exact: true })).toBeVisible()
      }
      if (state.require_alert) {
        assert(insights.body.data.active_alerts.length > 0)
      }
      if (insights.body.data.active_alerts.length) {
        await expect(page.getByText('Alerta preditivo persistente', { exact: true }).first()).toBeVisible()
      }
      output.insights = insights.body.data
      output.insights_source = 'GET response consumed by the UI; four visible fields matched together'
      await shot(page, `fault-insights-${availability}`)
      await page.goto('/digital-twin')
      await select(page)
      const items = page.getByRole('region', { name: 'Componentes do gêmeo digital', exact: true })
      await expect(items.getByRole('button')).toHaveCount(9)
      const canvas = page.locator('[data-testid=twin-scene] canvas')
      await expect(canvas).toBeVisible()
      const snapshot = (await api(monitoring)).body.data
      const fresh = snapshot.freshness.state === 'fresh'
      const fan = items.getByRole('button', { name: /^Ventilador/ })
      if (!fresh) {
        await expect(page.getByText('Leitura desatualizada. Aguardando dados recentes.', { exact: true })).toBeVisible()
        await expect(page.getByRole('status').filter({ hasText: 'Cena congelada:' })).toBeVisible()
        for (const button of await items.getByRole('button').all()) await expect(button).toContainText('Sem dados atuais')
      } else if (state.require_alert) await expect(fan).toContainText('Crítico')
      const ids = [state.catalog.equipment_id, ...Object.values(state.catalog.sensors), ...Object.values(state.catalog.actuators)]
      const inspected = []
      for (const [index, button] of (await items.getByRole('button').all()).entries()) {
        await button.click()
        const details = page.getByRole('region', { name: 'Detalhes do componente', exact: true })
        if (index === 0) await details.getByText('Histórico e identificação', { exact: true }).click()
        const id = await details.locator('dl > div').filter({ has: page.locator('dt', { hasText: /^ID$/ }) }).locator('dd').innerText()
        assert(ids.includes(id))
        await expect(details).toContainText('Idade da leitura')
        inspected.push(id)
      }
      assert.equal(new Set(inspected).size, 9)
      const renderer = await canvas.evaluate(canvas => {
        const gl = canvas.getContext('webgl2')
        return gl ? { context_lost: gl.isContextLost(), renderer: String(gl.getParameter(gl.RENDERER)) } : null
      })
      assert(renderer && !renderer.context_lost)
      const firstFrame = `fault-canvas-${availability}-first-${captureId}.png`
      const secondFrame = `fault-canvas-${availability}-second-${captureId}.png`
      const before = await canvas.screenshot({ path: join(state.output_dir, firstFrame) })
      await page.waitForTimeout(250)
      const after = await canvas.screenshot({ path: join(state.output_dir, secondFrame) })
      const changed = !before.equals(after)
      if (!fresh) assert.equal(changed, false)
      else if (snapshot.telemetry.data.equipment.running) assert.equal(changed, true)
      output.screenshots = [...output.screenshots, firstFrame, secondFrame]
      output.twin = { inspected_ids: inspected, webgl: renderer, snapshot,
        reduced_motion: 'no-preference', canvas_sample_interval_ms: 250, canvas_changed: changed,
        first_frame_sha256: createHash('sha256').update(before).digest('hex'),
        second_frame_sha256: createHash('sha256').update(after).digest('hex') }
    } else if (phase === 'assistant') {
      await page.goto('/assistant')
      const question = state.question ?? 'Qual a situação do meu equipamento?'
      await page.getByRole('textbox', { name: 'Sua pergunta', exact: true }).fill(question)
      const send = page.getByRole('button', { name: 'Enviar pergunta', exact: true })
      await expect(send).toBeEnabled({ timeout: 120_000 })
      const responsePromise = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v3/llm/ask' && r.request().method() === 'POST', { timeout: 140_000 })
      const askStarted = Date.now()
      await send.click()
      const response = await responsePromise
      assert.equal(response.status(), 200)
      assert(response.headers()['content-type'].startsWith('text/event-stream'))
      await expect(page.getByTestId('answer').last()).not.toBeEmpty({ timeout: 140_000 })
      const firstTextMs = Date.now() - askStarted
      const visibleBeforeDone = !await page.getByText('Resposta concluída', { exact: true }).isVisible()
      await expect(page.getByText('Resposta concluída', { exact: true })).toBeVisible({ timeout: Math.max(1000, 140_000 - firstTextMs) })
      const answer = await page.getByTestId('answer').last().innerText()
      assert(answer.trim().length > 0)
      const wire = await response.text()
      assert.match(wire, /event: done\r?\n/)
      assert.match(wire, /event: delta\r?\n/)
      output.assistant = { question, answer, first_text_ms: firstTextMs, completed_ms: Date.now() - askStarted,
        real_http_sse: true, delta_visible_before_done: visibleBeforeDone,
        delta_events: (wire.match(/event: delta\r?\n/g) ?? []).length, ui_terminal: 'Resposta concluída' }
    }
    await shot(page)
    assert.equal(errors.length, 0)
    output.page_errors = errors.length
  }
  output.duration_ms = Date.now() - started
  output.status = 'passed'
  console.log(JSON.stringify(output))
}

try { await main() }
catch (error) {
  // Playwright diagnostics can contain filled credentials; emit only a safe checkpoint.
  const message = String(error.message ?? 'Verification failed').split('\n')[0]
  const safeMessage = sensitive.reduce((text, value) => value ? text.replaceAll(value, '[private]') : text, message)
  console.log(JSON.stringify({ ...output, status: 'failed', checkpoint, error: safeMessage.slice(0, 500) }))
  process.exitCode = 1
} finally { await browser?.close() }
