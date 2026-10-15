import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'

import { fetchMonitoringHistory } from './monitoring-history'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

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
  it('normaliza histórico v3 real do período com sensores e limites, rejeitando escopo errado', async () => {
    vi.stubEnv('VITE_AIOT_ENABLED', 'true')
    vi.resetModules()
    const { fetchMonitoringHistory: fetchV3 } = await import('./monitoring-history')
    const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8')) as { name: string; payload: Record<string, unknown> }[]
    const telemetry = examples.find((item) => item.name === 'telemetry_received')!.payload
    const body = { success: true, data: [{ telemetry, persistence: 'persisted', prediction: null }], meta: { device_id: 'esp32.lab-01', start: '2026-10-12T17:00:00Z', end: '2026-10-12T18:01:00Z', count: 1, limit: 300, thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 } } }
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(body)))
    await expect(fetchV3({ baseUrl: '', fetcher, deviceId: 'esp32.lab-01', period: '1h' })).resolves.toMatchObject({ readings: [{ status: 'normal', motor_current_a: 1.4, persistence: 'persisted' }] })
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v3/readings?device_id=esp32.lab-01&period=1h&limit=300')
    await expect(fetchV3({ baseUrl: '', fetcher, deviceId: 'other', period: '1h' })).rejects.toThrow('histórico inválido')
    body.meta.thresholds.max_c = 2
    await expect(fetchV3({ baseUrl: '', fetcher, deviceId: 'esp32.lab-01', period: '1h' })).rejects.toThrow('histórico inválido')
  })
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
