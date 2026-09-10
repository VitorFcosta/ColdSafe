import { expect, test, type Page } from '@playwright/test'

type DashboardStatus = 'normal' | 'attention' | 'critical' | 'stale' | 'no_data'

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

      await page.goto('/')

      await expect(page.getByRole('heading', { name: 'Diagnóstico do ambiente' })).toBeVisible()
      await expect(page.getByText(scenario.label, { exact: true })).toBeVisible()
      await expect(page.getByText('Laboratório Refrigerado', { exact: true })).toBeVisible()
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

    await page.goto('/')

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

    await page.goto('/')

    const alert = page.getByRole('alert')
    await expect(alert).toContainText('Diagnóstico indisponível')
    await expect(alert.getByRole('button', { name: 'Tentar novamente' })).toBeVisible()
    await expect(page.getByText('Laboratório Refrigerado', { exact: true })).toHaveCount(0)
  })
})

async function mockMonitoringApi(
  page: Page,
  scenario: Readonly<{
    status: DashboardStatus
    temperature?: number
    ageSeconds?: number
  }>,
) {
  await page.route('**/api/v1/monitoring/summary', async (route) => {
    const hasReading = scenario.status !== 'no_data'
    const receivedAt = '2026-09-09T12:00:00Z'

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          environment: { id: 'lab-refrigerado', name: 'Laboratório Refrigerado' },
          device: { id: 'esp32-lab-01' },
          reading: hasReading
            ? {
                temperature_c: scenario.temperature,
                humidity_percent: 65,
                received_at: receivedAt,
              }
            : null,
          status: scenario.status,
          freshness: hasReading
            ? {
                is_stale: scenario.status === 'stale',
                age_seconds: scenario.ageSeconds,
              }
            : null,
          thresholds: { min_c: 2, max_c: 8, attention_margin_c: 1 },
        },
      }),
    })
  })

  await page.route('**/api/v1/readings?**', async (route) => {
    const hasReading = scenario.status !== 'no_data'
    const receivedAt = '2026-09-09T12:00:00Z'
    const requestUrl = new URL(route.request().url())

    expect(requestUrl.searchParams.get('device_id')).toBe('esp32-lab-01')
    expect(requestUrl.searchParams.get('period')).toBe('1h')
    expect(requestUrl.searchParams.get('limit')).toBe('300')

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          readings: hasReading
            ? [
                {
                  temperature_c: scenario.temperature,
                  humidity_percent: 65,
                  received_at: receivedAt,
                  status: scenario.status,
                },
              ]
            : [],
        },
        meta: {
          device_id: 'esp32-lab-01',
          start: '2026-09-09T11:00:00Z',
          end: '2026-09-09T12:00:00Z',
          count: hasReading ? 1 : 0,
          limit: 300,
        },
      }),
    })
  })
}
