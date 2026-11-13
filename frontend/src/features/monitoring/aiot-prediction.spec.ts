import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parseAiotEvent, parseAiotSnapshot } from './aiot-api'

const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8')) as { name: string; payload: Record<string, unknown> }[]
const example = (name: string) => structuredClone(examples.find((item) => item.name === name)!.payload)
const deviceId = 'esp32.lab-01'
function snapshot(prediction: unknown = example('prediction_available_zero_rul')) {
  return {
    environment: { id: '00000000-0000-4000-8000-000000000002', name: 'Laboratório' }, device: { id: deviceId },
    thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 }, telemetry: example('telemetry_received'), prediction,
    prediction_unavailable_reason: null, persistence: 'persisted',
    freshness: { last_event_id: '00000000-0000-4000-8000-000000000100', last_received_at: '2026-10-12T18:00:00.100Z', state: 'fresh', age_seconds: 4, stale_after_seconds: 30 },
    commands: { led: null, buzzer: null }, alerts: [],
  }
}

describe('previsão AIoT', () => {
  it('preserva RUL zero, versão e horário da entrada sem renovar freshness', () => {
    const result = parseAiotSnapshot(snapshot(), deviceId)
    expect(result?.prediction).toMatchObject({ type: 'prediction', data: { health_score: 12, rul_hours: 0, model_version: 'fan-model-1', features_version: 'fan-features-1', input_received_at: '2026-10-12T18:00:00.100Z' } })
    expect(result?.reading?.received_at).toBe('2026-10-12T18:00:00.100Z')
    expect(result?.freshness?.age_seconds).toBe(4)
  })

  it.each(examples.filter((item) => item.payload.type === 'prediction'))('aceita $name do contrato', ({ payload }) => {
    expect(parseAiotEvent(payload, deviceId)).toMatchObject({ type: 'prediction', data: payload.data })
  })

  it.each([
    ['saúde >100', { health_score: 101 }], ['RUL negativo', { rul_hours: -1 }], ['RUL infinito', { rul_hours: Infinity }],
    ['parcial', { rul_hours: null }], ['sem modelo', { model_id: null, model_version: null }],
    ['motivo na saída válida', { reason: 'no_model' }], ['features inválida', { features_version: 'bad/version' }],
    ['modelo sem versão', { model_version: null }], ['versão inválida', { model_version: 'bad+version' }],
  ])('rejeita %s', (_label, changes) => {
    const value = example('prediction_available_zero_rul')
    value.data = { ...(value.data as object), ...changes }
    expect(parseAiotEvent(value, deviceId)).toBeNull()
  })

  it('rejeita previsão sem correlação, anterior à entrada ou produzida vencida', () => {
    const value = example('prediction_available_zero_rul')
    expect(parseAiotEvent({ ...value, correlation_id: '00000000-0000-4000-8000-000000000999' }, deviceId)).toBeNull()
    expect(parseAiotEvent({ ...value, occurred_at: '2026-10-12T17:59:59Z' }, deviceId)).toBeNull()
    expect(parseAiotEvent({ ...value, occurred_at: '2026-10-12T18:00:31Z' }, deviceId)).toBeNull()
    const stale = example('prediction_unavailable_stale_input')
    expect(parseAiotEvent({ ...stale, occurred_at: '2026-10-12T18:00:01Z' }, deviceId)).toBeNull()
  })

  it.each(['source_event_id', 'equipment_id', 'input_received_at', 'device_record_id'])('não promove previsão de outra fonte (%s)', (field) => {
    const value = example('prediction_available_zero_rul')
    if (field === 'device_record_id') value[field] = '00000000-0000-4000-8000-000000000999'
    else {
      const data = value.data as Record<string, unknown>
      data[field] = field === 'input_received_at' ? '2026-10-12T18:00:00.050Z' : '00000000-0000-4000-8000-000000000999'
      if (field === 'source_event_id') value.correlation_id = data[field]
    }
    const result = parseAiotSnapshot(snapshot(value), deviceId)
    expect(result?.reading?.temperature_c).toBe(6.5)
    expect(result?.prediction).toBeNull()
  })

  it('suprime previsão quando entrada envelhece e mantém razão explícita sem modelo', () => {
    const value = snapshot()
    const result = parseAiotSnapshot({ ...value, freshness: { ...value.freshness, state: 'stale', age_seconds: 31 } }, deviceId)
    expect(result?.prediction).toBeNull()
    expect(result?.prediction_unavailable_reason).toBe('stale_input')
    expect(parseAiotSnapshot({ ...value, prediction: null, prediction_unavailable_reason: 'no_model' }, deviceId)?.prediction_unavailable_reason).toBe('no_model')
    expect(parseAiotSnapshot(snapshot(example('prediction_unavailable_no_model')), deviceId)?.prediction_unavailable_reason).toBe('no_model')
  })
})
