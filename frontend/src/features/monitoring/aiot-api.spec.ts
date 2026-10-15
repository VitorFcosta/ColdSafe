import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { calculateReadingStatus, isThresholds, isUtcTime, parseAiotCommand, parseAiotEvent, parseAiotSnapshot } from './aiot-api'

const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8')) as { name: string; payload: Record<string, unknown> }[]
function example(name: string) {
  return structuredClone(examples.find((item) => item.name === name)!.payload)
}
const deviceId = 'esp32.lab-01'
const environmentId = '00000000-0000-4000-8000-000000000002'
const thresholds = { min_c: 2, max_c: 8, attention_margin_c: 0.5 }
function snapshot() {
  return {
    environment: { id: environmentId, name: 'Laboratório' }, device: { id: deviceId }, thresholds,
    telemetry: example('telemetry_received'), prediction: null, persistence: 'pending',
    freshness: { last_event_id: '00000000-0000-4000-8000-000000000100', last_received_at: '2026-10-12T18:00:00.100Z', state: 'fresh', age_seconds: 4, stale_after_seconds: 30 },
    commands: { led: null, buzzer: null }, alerts: [],
  }
}

describe('AIoT API boundary', () => {
  it('usa as mesmas bordas inclusivas da classificação de temperatura do backend', () => {
    expect(calculateReadingStatus(2.5, thresholds)).toBe('attention')
    expect(calculateReadingStatus(7.5, thresholds)).toBe('attention')
    expect(calculateReadingStatus(2, thresholds)).toBe('attention')
    expect(calculateReadingStatus(1.9, thresholds)).toBe('critical')
    expect(calculateReadingStatus(8.1, thresholds)).toBe('critical')
    expect(isThresholds({ ...thresholds, attention_margin_c: 3 })).toBe(false)
  })
  it('normaliza os seis sensores e estados reais, preservando zeros e IDs', () => {
    const telemetry = example('telemetry_received')
    const data = telemetry.data as { measurements: { vibration: { value: number } } }
    data.measurements.vibration.value = 0
    const event = parseAiotEvent(telemetry, deviceId, environmentId)
    expect(event?.type).toBe('telemetry')
    if (event?.type !== 'telemetry') throw new Error('telemetry expected')
    expect(event.data.reading).toMatchObject({ temperature_c: 6.5, humidity_percent: 60, light_percent: 45, vibration_rms_mm_s: 0, motor_current_a: 1.4, motor_temperature_c: 38, event_id: telemetry.event_id, device_record_id: telemetry.device_record_id, environment_id: environmentId, equipment_id: '00000000-0000-4000-8000-000000000003' })
    expect(event.data.equipment).toMatchObject({ running: true, led: { actual_state: false }, buzzer: { actual_state: false } })
  })

  it.each([
    ['dispositivo', (event: Record<string, unknown>) => { event.device_id = 'outro' }],
    ['ambiente', (event: Record<string, unknown>) => { event.environment_id = '00000000-0000-4000-8000-000000000999' }],
    ['UUID', (event: Record<string, unknown>) => { event.event_id = 'invalid' }],
    ['horário local', (event: Record<string, unknown>) => { event.received_at = '2026-10-12T18:00:00-03:00' }],
    ['sensor ausente', (event: Record<string, unknown>) => { delete (event.data as { measurements: Record<string, unknown> }).measurements.vibration }],
    ['valor fora da faixa', (event: Record<string, unknown>) => { ((event.data as { measurements: Record<string, { value: number }> }).measurements.humidity!).value = 101 }],
    ['infinito', (event: Record<string, unknown>) => { ((event.data as { measurements: Record<string, { value: number }> }).measurements.motor_current!).value = Infinity }],
  ])('rejeita %s sem inventar medições', (_label, change) => {
    const event = example('telemetry_received')
    change(event)
    expect(parseAiotEvent(event, deviceId, environmentId)).toBeNull()
  })

  it('normaliza snapshot, frescor e persistência sem expor previsão futura', () => {
    const result = parseAiotSnapshot(snapshot(), deviceId)
    expect(result).toMatchObject({ environment: { id: environmentId }, device: { id: deviceId }, status: 'normal', freshness: { is_stale: false, age_seconds: 4 }, persistence: 'pending', reading: { motor_current_a: 1.4 } })
    expect(result).not.toHaveProperty('prediction')
    expect(parseAiotSnapshot({ ...snapshot(), persistence: 'persisted' }, deviceId)?.persistence).toBe('persisted')
    expect(parseAiotSnapshot({ ...snapshot(), telemetry: null, persistence: null, freshness: { state: 'no_data', last_event_id: null, last_received_at: null, age_seconds: null, stale_after_seconds: 30 } }, deviceId)).toMatchObject({ reading: null, status: 'no_data', freshness: null })
  })

  it('rejeita snapshot de outro dispositivo e limites incoerentes', () => {
    expect(parseAiotSnapshot(snapshot(), 'outro')).toBeNull()
    expect(parseAiotSnapshot({ ...snapshot(), thresholds: { ...thresholds, max_c: 1 } }, deviceId)).toBeNull()
    expect(parseAiotSnapshot({ ...snapshot(), freshness: { ...snapshot().freshness, last_event_id: '00000000-0000-4000-8000-000000000999' } }, deviceId)).toBeNull()
  })

  it('valida frescor na fronteira de 30 segundos e ignora IA', () => {
    expect(parseAiotEvent(example('fresh_boundary'), deviceId)?.type).toBe('freshness')
    const invalid = example('fresh_boundary')
    ;(invalid.data as { age_seconds: number }).age_seconds = 31
    expect(parseAiotEvent(invalid, deviceId)).toBeNull()
    expect(parseAiotEvent(example('prediction_available_zero_rul'), deviceId)).toBeNull()
    expect(parseAiotEvent(example('temperature_alert_closed'), deviceId)?.type).toBe('alert')
  })

  it('valida todos os estados de comando dos exemplos oficiais sem confundir envelope e domínio', () => {
    const commands = examples.filter((item) => item.payload.type === 'command_status')
    expect(commands.length).toBeGreaterThan(0)
    for (const item of commands) {
      const command = parseAiotCommand(item.payload, deviceId, environmentId)
      expect(command, item.name).toMatchObject({ schema_version: 3, ...(item.payload.data as object) })
    }
    expect(parseAiotCommand(example('telemetry_received'))).toBeNull()
    expect(parseAiotCommand(null)).toBeNull()
    const command = structuredClone(commands[0]!.payload)
    command.correlation_id = '00000000-0000-4000-8000-000000000999'
    expect(parseAiotCommand(command)).toBeNull()
  })

  it('rejeita dados de confirmação incompletos e horários UTC inexistentes', () => {
    const command = structuredClone(examples.find((item) => item.payload.type === 'command_status')!.payload)
    ;(command.data as { status: string }).status = 'confirmed'
    ;(command.data as { confirmed_state: unknown }).confirmed_state = null
    expect(parseAiotCommand(command)).toBeNull()
    expect(isUtcTime('2026-02-30T18:00:00Z')).toBe(false)
    expect(isUtcTime('2026-10-12T24:00:00Z')).toBe(false)
    expect(isUtcTime('2026-10-12T18:00:00+00:00')).toBe(true)
    expect(parseAiotEvent([], deviceId)).toBeNull()
    expect(parseAiotEvent({ ...example('telemetry_received'), schema_version: 2 }, deviceId)).toBeNull()
  })

  it('mantém leitura antiga como stale e rejeita relações incoerentes no snapshot', () => {
    const stale = { ...snapshot(), freshness: { ...snapshot().freshness, age_seconds: 31, state: 'stale' } }
    expect(parseAiotSnapshot(stale, deviceId)).toMatchObject({ status: 'stale', freshness: { is_stale: true, age_seconds: 31 } })
    expect(parseAiotSnapshot({ ...snapshot(), commands: { led: {}, buzzer: null } }, deviceId)).toBeNull()
    expect(parseAiotSnapshot({ ...snapshot(), freshness: { ...snapshot().freshness, last_received_at: '2026-10-12T17:00:00Z' } }, deviceId)).toBeNull()
    expect(parseAiotSnapshot({ ...snapshot(), persistence: undefined }, deviceId)).toBeNull()
    expect(parseAiotSnapshot(null, deviceId)).toBeNull()
  })
})
