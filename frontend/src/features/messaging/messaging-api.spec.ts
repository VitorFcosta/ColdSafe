import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchMessaging, fetchMessageSamples } from './messaging-api'

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

const sample = { event_id: '11111111-1111-4111-8111-111111111111', type: 'telemetry',
  occurred_at: data.sampled_at, observed_at: data.sampled_at,
  device_record_id: '22222222-2222-4222-8222-222222222222', device_id: 'cold-01',
  environment_id: '33333333-3333-4333-8333-333333333333', correlation_id: '44444444-4444-4444-8444-444444444444',
  source_queue: null, reason: null, error_code: null }
const samples = { sampled_at: data.sampled_at, connected: true, last_observed_at: data.sampled_at,
  stale: false, stale_after_seconds: 30, capacity_per_kind: 100, messages: [sample], dead_letters: [] }

describe('fetchMessageSamples', () => {
  it('consulta metadados privados somente pela API ColdSafe', async () => {
    reply({ success: true, data: samples })
    const signal = new AbortController().signal
    expect(await fetchMessageSamples('session', signal)).toEqual(samples)
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/v3\/messaging\/messages$/), {
      signal, headers: { accept: 'application/json', authorization: 'Bearer session' },
    })
  })
  it('aceita ausência de amostra e observador desconectado', async () => {
    const empty = { ...samples, connected: false, stale: true, last_observed_at: null, messages: [] }
    reply({ success: true, data: empty })
    expect(await fetchMessageSamples('session')).toEqual(empty)
  })
  it.each([
    { ...samples, connected: 'true' }, { ...samples, last_observed_at: 'ontem' },
    { ...samples, stale: null }, { ...samples, capacity_per_kind: 101 },
    { ...samples, stale_after_seconds: 0 }, { ...samples, messages: Array(101).fill(sample) },
    { ...samples, messages: [sample, sample] },
    { ...samples, messages: [{ ...sample, environment_id: 'invalid' }] },
    { ...samples, messages: [{ ...sample, observed_at: 'invalid' }] },
    { ...samples, dead_letters: [{ ...sample, reason: '<'.repeat(256) }] },
    { ...samples, dead_letters: [{ ...sample, source_queue: 1 }] },
  ])('rejeita amostra inválida ou sem limite: %j', async (invalid) => {
    reply({ success: true, data: invalid })
    await expect(fetchMessageSamples('session')).rejects.toThrow('Resposta inválida')
  })
  it.each([401, 403, 503])('não mostra diagnóstico bruto HTTP %s', async (status) => {
    reply({ error: { message: 'secret upstream' } }, status)
    await expect(fetchMessageSamples('session')).rejects.toThrow('Não foi possível consultar')
  })
})
