import { expect, test } from '@playwright/test'

import { mockMonitoringApi, type DashboardStatus } from './monitoring-api'

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
    await page.route('**/api/v1/monitoring/summary', async (route) => {
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
    await expect(page.getByText('Laboratório Refrigerado', { exact: true })).toHaveCount(0)

    await mockMonitoringApi(page, { status: 'normal' })
    await alert.getByRole('button', { name: 'Tentar novamente' }).click()

    await expect(page.getByText('Normal', { exact: true })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
})

test('mostra carregamento até receber uma leitura válida', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  let releaseSummary = () => {}
  const summaryReady = new Promise<void>((resolve) => { releaseSummary = resolve })
  await page.route('**/api/v1/monitoring/summary', async (route) => {
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

test('troca o período do histórico sem perder a leitura atual', async ({ page }) => {
  await mockMonitoringApi(page, { status: 'normal' })
  await page.goto('/dashboard')
  await expect(page.getByRole('button', { name: '1h', exact: true })).toHaveAttribute('aria-pressed', 'true')

  const historyRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return url.pathname === '/api/v1/readings' && url.searchParams.get('period') === '24h'
  })
  await page.getByRole('button', { name: '24h', exact: true }).click()
  await historyRequest

  await expect(page.getByRole('button', { name: '24h', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('button', { name: '1h', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByText('Normal', { exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: 'Gráfico de linha da temperatura no período selecionado' })).toBeVisible()
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
  await expect(page.getByRole('status')).toContainText('histórico de temperatura não pôde ser carregado')
})
