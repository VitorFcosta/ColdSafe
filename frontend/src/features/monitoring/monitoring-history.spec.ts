import { describe, expect, it, vi } from 'vitest'

import { fetchMonitoringHistory } from './monitoring-history'

const historyResponse = {
  success: true,
  data: {
    readings: [
      {
        temperature_c: 5.2,
        humidity_percent: 62.4,
        received_at: '2026-09-09T18:00:00Z',
        status: 'normal',
      },
      {
        temperature_c: 5.6,
        humidity_percent: 61.9,
        received_at: '2026-09-09T18:05:00Z',
        status: 'attention',
      },
    ],
  },
  meta: {
    schema_version: 1,
    device_id: 'esp32-lab-01',
    start: '2026-09-09T17:00:00Z',
    end: '2026-09-09T18:00:00Z',
    count: 2,
    limit: 300,
  },
} as const

describe('fetchMonitoringHistory', () => {
  it('consulta o histórico do período selecionado no contrato versionado', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(historyResponse), { status: 200 }),
    )

    await expect(
      fetchMonitoringHistory({
        baseUrl: 'http://localhost:8000/',
        deviceId: 'esp32-lab-01',
        period: '1h',
        fetcher,
      }),
    ).resolves.toEqual({
      deviceId: 'esp32-lab-01',
      end: '2026-09-09T18:00:00Z',
      limit: 300,
      readings: historyResponse.data.readings,
      start: '2026-09-09T17:00:00Z',
    })

    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/readings?device_id=esp32-lab-01&period=1h&limit=300',
      { headers: { accept: 'application/json' } },
    )
  })

  it('rejeita uma resposta que não cumpre o contrato do histórico', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...historyResponse,
          meta: { ...historyResponse.meta, count: 3 },
        }),
        { status: 200 },
      ),
    )

    await expect(
      fetchMonitoringHistory({
        baseUrl: 'http://localhost:8000',
        deviceId: 'esp32-lab-01',
        period: '15m',
        fetcher,
      }),
    ).rejects.toThrow('histórico inválido')
  })
})
