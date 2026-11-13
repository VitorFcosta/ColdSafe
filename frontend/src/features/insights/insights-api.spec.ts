import { readFileSync } from 'node:fs'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchInsights, InsightsAccessError, parseInsights, parsePredictiveRules, savePredictiveRules } from './insights-api'

const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8')) as { name: string; payload: Record<string, unknown> }[]
const prediction = examples.find((item) => item.name === 'prediction_available_zero_rul')!.payload
const device = { id: String(prediction.device_record_id), mqtt_device_id: String(prediction.device_id), environment_id: String(prediction.environment_id), name: 'Motor', is_active: true }
const rules = { health_critical: 30, health_recovery: 40, rul_critical_hours: 24, rul_recovery_hours: 48, open_count: 3, close_count: 10 }
const snapshot = () => ({ device_id: device.mqtt_device_id, equipment_id: (prediction.data as Record<string, unknown>).equipment_id, rules: { ...rules }, prediction: structuredClone(prediction), availability: 'available', age_seconds: 4, trend: 'declining', active_alerts: [] })
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } })
afterEach(() => vi.unstubAllGlobals())

describe('contrato Insights', () => {
  it('preserva RUL zero, previsão correlacionada e regras', () => {
    expect(parseInsights(snapshot(), device)).toMatchObject({ availability: 'available', prediction: { data: { rul_hours: 0 } }, rules })
  })
  it.each([
    { device_id: 'other' }, { equipment_id: 'invalid' }, { age_seconds: -1 }, { age_seconds: Infinity }, { trend: 'wrong' },
    { availability: 'available', prediction: null }, { availability: 'no_data' }, { availability: 'unavailable' },
    { availability: 'stale', age_seconds: 4 }, { rules: { ...rules, health_critical: 50 } },
    { active_alerts: [{}] }, { active_alerts: [null] }, { active_alerts: 'bad' },
  ])('rejeita resposta externa incoerente %j', (changes) => {
    expect(parseInsights({ ...snapshot(), ...changes }, device)).toBeNull()
  })
  it.each(['environment_id', 'device_record_id'])('rejeita previsão de outro cadastro: %s', (field) => {
    expect(parseInsights({ ...snapshot(), prediction: { ...prediction, [field]: '00000000-0000-4000-8000-000000000999' } }, device)).toBeNull()
  })
  it('valida alertas persistentes e rejeita IDs duplicados', () => {
    const alert = { alert_id: '00000000-0000-4000-8000-000000000999', kind: 'predictive_failure', opened_at: prediction.received_at, source_event_id: prediction.correlation_id, prediction_event_id: prediction.event_id }
    expect(parseInsights({ ...snapshot(), active_alerts: [alert] }, device)?.active_alerts).toEqual([alert])
    expect(parseInsights({ ...snapshot(), active_alerts: [alert, alert] }, device)).toBeNull()
  })
  it('aceita ausência explícita e previsão vencida sem convertê-las em recuperação', () => {
    expect(parseInsights({ ...snapshot(), prediction: null, age_seconds: null, availability: 'no_data', trend: 'unknown' }, device)?.availability).toBe('no_data')
    expect(parseInsights({ ...snapshot(), age_seconds: 31, availability: 'stale', trend: 'unknown' }, device)?.availability).toBe('stale')
    expect(parseInsights({ ...snapshot(), prediction: null, age_seconds: 4, availability: 'no_data', trend: 'unknown' }, device)?.availability).toBe('no_data')
    expect(parseInsights({ ...snapshot(), prediction: null, age_seconds: 31, availability: 'stale', trend: 'unknown' }, device)?.availability).toBe('stale')
  })
  it.each([
    null, {}, { ...rules, extra: 1 }, { ...rules, open_count: 0 }, { ...rules, close_count: 1.5 },
    { ...rules, health_critical: -1 }, { ...rules, health_recovery: 101 }, { ...rules, rul_critical_hours: -1 },
    { ...rules, rul_recovery_hours: 24 }, { ...rules, open_count: true },
  ])('rejeita regras inválidas %j', (value) => expect(parsePredictiveRules(value)).toBeNull())
  it('consulta com Bearer, MQTT ID e cancelamento; valida envelope', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ success: true, meta: { schema_version: 3 }, data: snapshot() }))
    vi.stubGlobal('fetch', fetch)
    const signal = new AbortController().signal
    expect(await fetchInsights('secret', device, signal)).toMatchObject({ device_id: device.mqtt_device_id })
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining(`/api/v3/insights?device_id=${device.mqtt_device_id}`), expect.objectContaining({ signal, headers: expect.objectContaining({ authorization: 'Bearer secret' }) }))
    fetch.mockResolvedValueOnce(json({ success: true, meta: { schema_version: 2 }, data: snapshot() }))
    await expect(fetchInsights('secret', device)).rejects.toThrow('inválida')
  })
  it.each([401, 403, 404])('expõe revogação %s para a página apagar dados', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ success: false }, status)))
    await expect(fetchInsights('secret', device)).rejects.toBeInstanceOf(InsightsAccessError)
  })
  it('salva somente regras válidas e valida a resposta', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ success: true, meta: { schema_version: 3 }, data: rules }))
    vi.stubGlobal('fetch', fetch)
    expect(await savePredictiveRules('token', device, rules)).toEqual(rules)
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/insights/rules?device_id='), expect.objectContaining({ method: 'PUT', body: JSON.stringify(rules) }))
    await expect(savePredictiveRules('token', device, { ...rules, open_count: 0 })).rejects.toThrow('Regras inválidas')
    expect(fetch).toHaveBeenCalledOnce()
    fetch.mockResolvedValueOnce(json({ success: true, meta: { schema_version: 3 }, data: {} }))
    await expect(savePredictiveRules('token', device, rules)).rejects.toThrow('inválida')
  })
  it('não divulga diagnóstico externo ou payload inválido', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ error: { message: 'secret' } }, 500))
    vi.stubGlobal('fetch', fetch)
    await expect(fetchInsights('token', device)).rejects.toThrow('Não foi possível')
    fetch.mockResolvedValueOnce(new Response('bad json'))
    await expect(fetchInsights('token', device)).rejects.toThrow('inválida')
    fetch.mockResolvedValueOnce(json({ success: true, meta: { schema_version: 3 }, data: null }))
    await expect(fetchInsights('token', device)).rejects.toThrow('inválida')
  })
})
