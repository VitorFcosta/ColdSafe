import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'

import { fetchMonitoringSummary } from './monitoring-summary'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

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
  it('usa v3 somente após habilitação explícita e valida o dispositivo selecionado', async () => {
    vi.stubEnv('VITE_AIOT_ENABLED', 'true')
    vi.resetModules()
    const { fetchMonitoringSummary: fetchV3 } = await import('./monitoring-summary')
    const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8')) as { name: string; payload: Record<string, unknown> }[]
    const telemetry = examples.find((item) => item.name === 'telemetry_received')!.payload
    const data = { environment: { id: telemetry.environment_id, name: 'Laboratório' }, device: { id: telemetry.device_id }, telemetry, persistence: 'pending', thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 }, freshness: { last_event_id: telemetry.event_id, last_received_at: telemetry.received_at, state: 'fresh', age_seconds: 1, stale_after_seconds: 30 }, commands: { led: null, buzzer: null } }
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ success: true, data })))
    await expect(fetchV3({ baseUrl: 'http://localhost:8000/', fetcher, deviceId: 'esp32.lab-01', token: 'private' })).resolves.toMatchObject({ status: 'normal', reading: { motor_current_a: 1.4 } })
    expect(fetcher.mock.calls[0]?.[0]).toBe('http://localhost:8000/api/v3/monitoring/summary?device_id=esp32.lab-01')
    await expect(fetchV3({ baseUrl: '', fetcher, deviceId: 'other' })).rejects.toThrow('diagnóstico inválido')
  })
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
