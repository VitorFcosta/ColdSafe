import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchAlerts } from './alerts-api'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

const alert = {
  alert_id: 'alert-1', device_id: 'esp32-1', kind: 'temperature_high',
  opened_at: '2026-09-24T12:00:00Z', closed_at: null, status: 'open',
}

const options = {
  baseUrl: 'http://localhost:8000/', deviceId: 'esp32-1',
  start: '2026-09-24T11:00:00Z', end: '2026-09-24T12:00:00Z', auth: 'test-session',
}

describe('fetchAlerts', () => {
  it('consulta alertas v3 somente quando habilitado e rejeita IDs inválidos', async () => {
    vi.stubEnv('VITE_AIOT_ENABLED', 'true')
    vi.resetModules()
    const { fetchAlerts: fetchV3 } = await import('./alerts-api')
    const body = { success: true, data: { alerts: [{ ...alert, alert_id: '00000000-0000-4000-8000-000000000001' }] }, meta: { device_id: 'esp32-1', count: 1 } }
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(body)))
    await expect(fetchV3({ ...options, fetcher })).resolves.toHaveLength(1)
    expect(fetcher.mock.calls[0]?.[0]).toContain('/api/v3/alerts?')
    body.data.alerts[0]!.alert_id = 'invalid'
    await expect(fetchV3({ ...options, fetcher })).rejects.toThrow('alertas inválidos')
  })
  it('envia dispositivo, intervalo e sessão e valida o resultado', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true, data: { alerts: [alert] }, meta: { device_id: 'esp32-1', count: 1 },
    })))

    await expect(fetchAlerts({ ...options, fetcher })).resolves.toEqual([alert])
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit]
    expect(url.split('?')[0]).toBe('http://localhost:8000/api/v1/alerts')
    expect(Object.fromEntries(new URL(url).searchParams)).toEqual({
      device_id: 'esp32-1', start: options.start, end: options.end, limit: '300',
    })
    expect(init.headers).toMatchObject({ authorization: 'Bearer test-session' })
  })

  it('rejeita alerta de outro dispositivo', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true, data: { alerts: [{ ...alert, device_id: 'esp32-2' }] },
      meta: { device_id: 'esp32-1', count: 1 },
    })))

    await expect(fetchAlerts({ ...options, fetcher })).rejects.toThrow('alertas inválidos')
  })
})
