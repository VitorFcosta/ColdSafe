import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchMessaging } from './messaging-api'

const queue = { name: 'telemetry.api.q', messages: 3, messages_ready: 2, messages_unacknowledged: 1,
  consumers: 1, publish_rate: null, deliver_rate: 0 }
const data = { sampled_at: '2026-10-15T12:00:00Z', queues: [queue] }
function reply(value: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(value), { status })))
}
afterEach(() => vi.unstubAllGlobals())

describe('fetchMessaging', () => {
  it('consulta somente a API ColdSafe, com bearer e cancelamento, preservando taxa desconhecida', async () => {
    reply({ success: true, data })
    const signal = new AbortController().signal
    expect(await fetchMessaging('session', signal)).toEqual(data)
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/v3\/messaging$/), {
      signal, headers: { accept: 'application/json', authorization: 'Bearer session' },
    })
  })
  it.each([
    { ...data, sampled_at: 'ontem' },
    { ...data, queues: [{ ...queue, messages: -1 }] },
    { ...data, queues: [{ ...queue, consumers: 1.5 }] },
    { ...data, queues: [{ ...queue, publish_rate: -1 }] },
    { ...data, queues: [{ ...queue, deliver_rate: undefined }] },
    { ...data, queues: [queue, queue] },
    { ...data, queues: null },
  ])('rejeita métricas inválidas: %j', async (invalid) => {
    reply({ success: true, data: invalid })
    await expect(fetchMessaging('session')).rejects.toThrow('Resposta inválida')
  })
  it.each([401, 403, 503])('não propaga conteúdo operacional de erro HTTP %s', async (status) => {
    reply({ error: { message: 'secret upstream http://broker:15672' } }, status)
    await expect(fetchMessaging('session')).rejects.toThrow('Não foi possível consultar a mensageria')
  })
})
