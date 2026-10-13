import { expect, test } from '@playwright/test'

import { mockDashboardAccount, mockMonitoringApi, type DashboardStatus } from './monitoring-api'

const statusCases: ReadonlyArray<
  Readonly<{
    status: Exclude<DashboardStatus, 'no_data'>
    label: string
    temperature: number
    ageSeconds: number
    freshnessLabel: string
  }>
> = [
  {
    status: 'normal',
    label: 'Normal',
    temperature: 5,
    ageSeconds: 2,
    freshnessLabel: 'Agora mesmo',
  },
  {
    status: 'attention',
    label: 'Atenção',
    temperature: 2.5,
    ageSeconds: 8,
    freshnessLabel: 'Há 8 s',
  },
  {
    status: 'critical',
    label: 'Crítico',
    temperature: 9,
    ageSeconds: 12,
    freshnessLabel: 'Há 12 s',
  },
  {
    status: 'stale',
    label: 'Leitura desatualizada',
    temperature: 5,
    ageSeconds: 45,
    freshnessLabel: 'Há 45 s',
  },
]

test.describe('dashboard operacional', () => {
  for (const scenario of statusCases) {
    test(`exibe o fluxo ${scenario.label.toLocaleLowerCase('pt-BR')}`, async ({ page }) => {
      await mockMonitoringApi(page, {
        status: scenario.status,
        temperature: scenario.temperature,
        ageSeconds: scenario.ageSeconds,
      })

      await page.goto('/dashboard')

      await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente' })).toBeVisible()
      await expect(page.getByText(scenario.label, { exact: true })).toBeVisible()
      await expect(page.getByText('Laboratório Refrigerado / esp32-lab-01', { exact: true })).toBeVisible()
      await expect(page.getByText(scenario.freshnessLabel, { exact: true })).toBeVisible()
      await expect(
        page
          .getByRole('article')
          .filter({ hasText: 'Temperatura' })
          .getByText(`${scenario.temperature.toLocaleString('pt-BR')} °C`, { exact: true }),
      ).toBeVisible()
      await expect(
        page.getByRole('article').filter({ hasText: 'Umidade' }).getByText('65 %', { exact: true }),
      ).toBeVisible()
      await expect(
        page.getByRole('img', {
          name: 'Gráfico de linha da temperatura no período selecionado',
        }),
      ).toBeVisible()
    })
  }

  test('abre a tabela de leituras pelo teclado sem criar rolagem horizontal no celular', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 700 })
    await mockMonitoringApi(page, { status: 'normal' })
    await page.goto('/dashboard')

    const details = page.locator('details').filter({ hasText: 'Ver 1 leitura em tabela' })
    await expect(details).toBeVisible()
    await details.locator('summary').focus()
    await page.keyboard.press('Enter')
    await expect(details).toHaveAttribute('open', '')
    const table = page.getByRole('table', { name: /Leituras individuais do período selecionado/ })
    await expect(table.getByRole('row')).toHaveCount(2)
    await expect(table.getByRole('cell', { name: '5 °C' })).toBeVisible()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('region', { name: 'Leituras individuais de temperatura' })).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  })

  test('exibe o fluxo sem dados sem inventar medições', async ({ page }) => {
    await mockMonitoringApi(page, { status: 'no_data' })

    await page.goto('/dashboard')

    await expect(page.getByText('Sem dados', { exact: true })).toBeVisible()
    await expect(page.getByText('Sem leitura recebida', { exact: true })).toBeVisible()
    await expect(page.getByText('Recebida em —', { exact: true })).toBeVisible()
    await expect(
      page
        .getByRole('article')
        .filter({ hasText: 'Temperatura' })
        .getByText('—', { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole('article').filter({ hasText: 'Umidade' }).getByText('—', { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText(/Não há leituras de temperatura nas últimas 1 hora/),
    ).toBeVisible()
  })

  test('exibe o fluxo de erro e permite tentar novamente', async ({ page }) => {
    await mockDashboardAccount(page)
    await page.route('**/api/v1/monitoring/summary**', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'DEPENDENCY_UNAVAILABLE', message: 'Serviço indisponível.' },
        }),
      })
    })

    await page.goto('/dashboard')

    const alert = page.getByRole('alert')
    await expect(alert).toContainText('Diagnóstico indisponível')
    await expect(alert.getByRole('button', { name: 'Tentar novamente' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Medições do ambiente' })).toHaveCount(0)

    await mockMonitoringApi(page, { status: 'normal' })
    await alert.getByRole('button', { name: 'Tentar novamente' }).click()

    await expect(page.getByText('Normal', { exact: true })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
})

for (const scenario of [
  { status: 'normal', label: 'Normal', age: 'Agora mesmo' },
  { status: 'stale', label: 'Leitura desatualizada', age: 'Há 1 h' },
] as const) {
  test(`mostra temperatura, estado e atualidade juntos na primeira tela móvel: ${scenario.status}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await mockMonitoringApi(page, { status: scenario.status, temperature: 5, ageSeconds: scenario.status === 'stale' ? 3600 : 2 })
    await page.goto('/dashboard')

    const primary = page.getByRole('article').filter({ hasText: 'Temperatura' }).first()
    await expect(primary).toContainText('5 °C')
    await expect(primary).toContainText(scenario.label)
    await expect(primary).toContainText(scenario.age)
    const bounds = await primary.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(844)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

    if (scenario.status === 'stale') {
      await expect(page.getByText(/Conexão com servidor: conectada\. O sensor não enviou leitura recente\./)).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Umidade da última leitura' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Luminosidade da última leitura' })).toBeVisible()
    }

    if (scenario.status === 'normal') {
      await page.setViewportSize({ width: 1440, height: 900 })
      const secondary = page.getByRole('region', { name: 'Medições do ambiente' }).locator('article')
      await expect(secondary).toHaveCount(2)
      const tops = await secondary.evaluateAll((articles) => articles.map((article) => article.getBoundingClientRect().top))
      expect(tops[0]).toBe(tops[1])
    }
  })
}

test('mantém nomes longos e temperatura extrema legíveis em 320 px', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await mockMonitoringApi(page, {
    status: 'critical',
    temperature: -123.5,
    environmentName: 'Laboratório de amostras ultracongeladas do bloco experimental',
    deviceName: 'Sensor de monitoramento da câmara ultracongelada',
  })
  await page.goto('/dashboard')

  const primary = page.getByRole('article').filter({ hasText: 'Temperatura' }).first()
  await expect(primary).toContainText('-123,5 °C')
  await expect(primary).toContainText('Crítico')
  await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)

  for (const locator of [page.locator('.dashboard-heading'), page.locator('.selection-panel'), primary]) {
    const bounds = await locator.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320)
  }
})

test('mostra carregamento até receber uma leitura válida', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  let releaseSummary = () => {}
  const summaryReady = new Promise<void>((resolve) => { releaseSummary = resolve })
  await page.route('**/api/v1/monitoring/summary**', async (route) => {
    await summaryReady
    await route.fallback()
  })

  await page.goto('/dashboard')
  try {
    await expect(page.getByLabel('Carregando diagnóstico atual')).toHaveAttribute('aria-busy', 'true')
    await expect(page.getByText('Normal', { exact: true })).toHaveCount(0)
  } finally {
    releaseSummary()
  }
  await expect(page.getByText('Normal', { exact: true })).toBeVisible()
})

test('recupera o catálogo sem clique quando a API volta', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  let apiUnavailable = true
  await page.route('**/api/v1/environments', async (route) => {
    if (apiUnavailable) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({
        success: false, error: { message: 'Serviço indisponível.' },
      }) })
    } else {
      await route.fallback()
    }
  })

  await page.goto('/dashboard')
  await expect(page.getByText('Não foi possível carregar ambientes ou dispositivos.')).toBeVisible()
  apiUnavailable = false
  await expect(page.getByRole('combobox', { name: 'Dispositivo' })).toBeEnabled()
  await expect(page.getByText('Laboratório Refrigerado / esp32-lab-01', { exact: true })).toBeVisible()
})

test('troca de dispositivo e só mostra LED ligado após confirmação', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  await page.route('**/api/v1/monitoring/summary**', async (route) => {
    const deviceId = new URL(route.request().url()).searchParams.get('device_id')
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      success: true, data: {
        environment: { id: 'lab-refrigerado', name: 'Laboratório Refrigerado' },
        device: { id: deviceId },
        reading: { temperature_c: deviceId === 'esp32-lab-02' ? 4 : 5, humidity_percent: 65,
          light_percent: 42, received_at: '2026-09-09T12:00:00Z' },
        status: 'normal', freshness: { is_stale: false, age_seconds: 2 },
        thresholds: { min_c: 2, max_c: 8, attention_margin_c: 1 },
      },
    }) })
  })
  await page.route('**/api/v1/readings?**', async (route) => {
    const deviceId = new URL(route.request().url()).searchParams.get('device_id')
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      success: true, data: { readings: [] },
      meta: { device_id: deviceId, start: '2026-09-09T11:00:00Z', end: '2026-09-09T12:00:00Z', count: 0, limit: 300 },
    }) })
  })
  await page.route('**/api/v1/devices/uuid-02/led/commands', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: {
      schema_version: 2, command_id: 'command-02', device_id: 'esp32-lab-02', actuator: 'led',
      desired_state: true, confirmed_state: null, status: 'pending',
    } }),
  }))
  await page.route('**/api/v1/commands/command-02', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: {
      schema_version: 2, command_id: 'command-02', device_id: 'esp32-lab-02', actuator: 'led',
      desired_state: true, confirmed_state: true, status: 'confirmed',
    } }),
  }))

  await page.goto('/dashboard')
  await expect(page.getByText('Laboratório Refrigerado / esp32-lab-01', { exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Dispositivo' }).selectOption('uuid-02')
  await expect(page.getByText('Laboratório Refrigerado / esp32-lab-02', { exact: true })).toBeVisible()
  await expect(page.getByRole('article').filter({ hasText: 'Temperatura' }).getByText('4 °C')).toBeVisible()
  await page.locator('details[aria-label="Estado dos atuadores"] summary').click()
  await page.getByRole('button', { name: 'Ligar Luz' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('Aguardando confirmação', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Desligar Luz' })).toBeVisible()
})

test('abre os atuadores por teclado sem enviar comandos', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  const commandRequests: string[] = []
  await page.route('**/api/v1/devices/*/led/commands', (route) => {
    commandRequests.push(route.request().url())
    return route.abort()
  })
  await page.goto('/dashboard')

  const details = page.locator('details[aria-label="Estado dos atuadores"]')
  const summary = details.locator('summary')
  await expect(details).not.toHaveAttribute('open')
  await expect(summary).toContainText('Luz manual: Sem confirmação registrada')
  await expect(summary).toContainText('Som de aviso automático: Sem confirmação registrada')
  await summary.focus()
  await page.keyboard.press('Enter')
  await expect(details).toHaveAttribute('open', '')
  await expect(details.getByRole('button', { name: 'Atualizar estado' })).toBeVisible()
  await expect(details.getByRole('button', { name: 'Ligar Luz' })).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(details).not.toHaveAttribute('open')
  await page.goto('/manage')
  await page.goto('/dashboard')
  expect(commandRequests).toEqual([])
})

test('troca o período do histórico sem perder a leitura atual', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  await page.goto('/dashboard')
  await expect(page.getByRole('button', { name: '1h', exact: true })).toHaveAttribute('aria-pressed', 'true')

  for (const period of ['15m', '6h', '24h']) {
    const historyRequest = page.waitForRequest((request) => {
      const url = new URL(request.url())
      return url.pathname === '/api/v1/readings' && url.searchParams.get('period') === period
    })
    await page.getByRole('button', { name: period, exact: true }).click()
    await historyRequest
    await expect(page.getByRole('button', { name: period, exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('img', { name: 'Gráfico de linha da temperatura no período selecionado' })).toBeVisible()
  }

  await expect(page.getByRole('button', { name: '1h', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByText('Normal', { exact: true })).toBeVisible()
})

test('preserva leitura válida quando apenas o histórico falha', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  await page.route('**/api/v1/readings?**', (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ success: false, error: { code: 'DEPENDENCY_UNAVAILABLE', message: 'Serviço indisponível.' } }),
  }))

  await page.goto('/dashboard')

  await expect(page.getByText('Normal', { exact: true })).toBeVisible()
  await expect(page.getByText('Agora mesmo', { exact: true })).toBeVisible()
  await expect(page.getByRole('article').filter({ hasText: 'Temperatura' }).getByText('5 °C', { exact: true })).toBeVisible()
  await expect(page.getByText(/histórico de temperatura não pôde ser carregado/)).toBeVisible()
})


test('visualizador consulta diagnóstico e atuadores sem emitir comandos', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
    success: true, data: { user_id: 'viewer-user', email: 'viewer@example.com', role: 'viewer' },
  } }))
  let writes = 0
  await page.route('**/api/v1/devices/*/led/commands', (route) => {
    writes += 1
    return route.abort()
  })
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Normal', exact: true })).toBeVisible()
  await page.getByRole('group', { name: 'Estado dos atuadores' }).locator('summary').click()
  await expect(page.getByText('Modo visualizador: você pode consultar o estado dos atuadores.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ligar Luz' })).toBeDisabled()
  expect(writes).toBe(0)
})
