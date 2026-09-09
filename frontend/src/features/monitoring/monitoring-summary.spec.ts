import { describe, expect, it, vi } from 'vitest'

import { fetchMonitoringSummary } from './monitoring-summary'

const summaryResponse = {
  success: true,
  data: {
    environment: { id: 'lab-01', name: 'Laboratório Refrigerado' },
    device: { id: 'esp32-lab-01' },
    reading: {
      temperature_c: 5.2,
      humidity_percent: 62.4,
      received_at: '2026-09-09T18:00:00Z',
    },
    status: 'normal',
    freshness: { is_stale: false, age_seconds: 4 },
    thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
  },
  meta: { schema_version: 1 },
} as const

describe('fetchMonitoringSummary', () => {
  it('consulta o diagnóstico atual no contrato versionado', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(summaryResponse), { status: 200 }),
    )

    await expect(
      fetchMonitoringSummary({
        baseUrl: 'http://localhost:8000/',
        fetcher,
      }),
    ).resolves.toEqual(summaryResponse.data)

    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/monitoring/summary',
      { headers: { accept: 'application/json' } },
    )
  })

  it('rejeita resposta de sucesso que não segue o contrato', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ success: true, data: {} }), { status: 200 }),
    )

    await expect(
      fetchMonitoringSummary({
        baseUrl: 'http://localhost:8000',
        fetcher,
      }),
    ).rejects.toThrow('diagnóstico inválido')
  })
})
