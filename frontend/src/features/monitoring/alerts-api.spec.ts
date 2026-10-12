import { describe, expect, it, vi } from 'vitest'

import { fetchAlerts } from './alerts-api'

const alert = {
  alert_id: 'alert-1', device_id: 'esp32-1', kind: 'temperature_high',
  opened_at: '2026-09-24T12:00:00Z', closed_at: null, status: 'open',
}

const options = {
  baseUrl: 'http://localhost:8000/', deviceId: 'esp32-1',
  start: '2026-09-24T11:00:00Z', end: '2026-09-24T12:00:00Z', auth: 'test-session',
}

describe('fetchAlerts', () => {
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
