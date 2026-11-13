import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parseAiotSnapshot } from '../monitoring/aiot-api'
import type { InsightsSnapshot } from '../insights/insights-api'
import { buildTwinItems, buildTwinVisualState } from './twin-state'

const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8'))
const telemetry = examples.find((item: { name: string }) => item.name === 'telemetry_received').payload
const inventory = { equipment_id: telemetry.data.equipment.equipment_id,
  sensors: Object.fromEntries(Object.entries(telemetry.data.measurements).map(([key, value]) => [key, (value as { sensor_id: string }).sensor_id])),
  actuators: { led: telemetry.data.actuators.led.actuator_id, buzzer: telemetry.data.actuators.buzzer.actuator_id } }
function summary() {
  return parseAiotSnapshot({ environment: { id: telemetry.environment_id, name: 'Lab' }, device: { id: telemetry.device_id },
    inventory, telemetry, prediction: null, persistence: 'persisted', thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
    freshness: { state: 'fresh', age_seconds: 0, last_event_id: telemetry.event_id, last_received_at: telemetry.received_at, stale_after_seconds: 30 },
    commands: { led: null, buzzer: null } })!
}
const insights = { device_id: telemetry.device_id, equipment_id: inventory.equipment_id,
  rules: { health_critical: 20, health_recovery: 30, rul_critical_hours: 24, rul_recovery_hours: 48, open_count: 3, close_count: 10 },
  active_alerts: [], prediction: null, availability: 'no_data', age_seconds: null, trend: 'unknown' } satisfies InsightsSnapshot

describe('inventário do gêmeo digital', () => {
  it('entrega números/estados observados para animação, preserva zero e bloqueia leitura vencida', () => {
    const base = summary()
    const current = { ...base, reading: { ...base.reading!, temperature_c: 0, light_percent: 0, vibration_rms_mm_s: 0 },
      equipment: { ...base.equipment!, running: false } }
    expect(buildTwinVisualState(current, true)).toEqual({ temperature: 0, light: 0, vibration: 0, running: false, led: false, buzzer: false })
    expect(buildTwinVisualState(base, false)).toBeNull()
    expect(buildTwinVisualState(null, true)).toBeNull()
    expect(buildTwinVisualState({ ...base, reading: null }, true)).toBeNull()
    expect(buildTwinVisualState({ ...base, equipment: undefined }, true)).toBeNull()
    expect(buildTwinVisualState({ ...base, reading: { ...base.reading!, light_percent: null, vibration_rms_mm_s: undefined } }, true))
      .toMatchObject({ light: null, vibration: null, running: true })
  })
  it('representa nove IDs únicos do cadastro e posições independentes dos valores', () => {
    const items = buildTwinItems(summary(), true, insights)
    expect(items).toHaveLength(9)
    expect(new Set(items.map((item) => item.id)).size).toBe(9)
    expect(items.find((item) => item.key === 'temperature_c')).toMatchObject({ id: inventory.sensors.ambient_temperature, value: '6,5 °C', status: 'normal' })
    expect(items.find((item) => item.key === 'led')).toMatchObject({ value: 'Desligado', status: 'normal' })
    expect(items.find((item) => item.key === 'fan')).toMatchObject({ value: 'Em operação' })
    expect(new Set(items.map((item) => item.position.join(','))).size).toBe(9)
  })
  it('mantém os IDs sem telemetria e oculta valores vencidos', () => {
    const stale = buildTwinItems(summary(), false, insights)
    const noData = buildTwinItems({ ...summary(), reading: null, equipment: undefined }, false, null)
    for (const items of [stale, noData]) {
      expect(items.every((item) => item.id && item.status === 'no_data' && item.value === 'Sem dados atuais')).toBe(true)
    }
    expect(buildTwinItems(null, false, null).every((item) => item.id === null)).toBe(true)
  })
  it('preserva zero real e não cria faixas de risco para outros sensores', () => {
    const base = summary()
    const items = buildTwinItems({ ...base, reading: { ...base.reading!, vibration_rms_mm_s: 0, motor_temperature_c: 190 } }, true, insights)
    expect(items.find((item) => item.key === 'vibration_rms_mm_s')).toMatchObject({ value: '0 mm/s', status: 'normal' })
    expect(items.find((item) => item.key === 'motor_temperature_c')?.status).toBe('normal')
  })
  it.each([[7.5, 'attention'], [9, 'critical']])('reutiliza limites térmicos: %s → %s', (temperature, status) => {
    const base = summary()
    expect(buildTwinItems({ ...base, reading: { ...base.reading!, temperature_c: Number(temperature) } }, true, insights)
      .find((item) => item.key === 'temperature_c')?.status).toBe(status)
  })
  it('prioriza alerta persistente do equipamento e buzzer observado', () => {
    const base = summary()
    const alert = { alert_id: 'alert', kind: 'predictive_failure', opened_at: telemetry.received_at, source_event_id: telemetry.event_id, prediction_event_id: 'prediction' } as const
    const items = buildTwinItems({ ...base, equipment: { ...base.equipment!, buzzer: { ...base.equipment!.buzzer, actual_state: true } } }, true, { ...insights, active_alerts: [alert] })
    expect(items.find((item) => item.key === 'fan')?.status).toBe('critical')
    expect(items.find((item) => item.key === 'buzzer')).toMatchObject({ value: 'Ligado', status: 'critical' })
    expect(buildTwinItems(base, true, null).find((item) => item.key === 'fan')?.status).toBe('no_data')
    expect(buildTwinItems(base, true, { ...insights, equipment_id: 'foreign', active_alerts: [alert] }).find((item) => item.key === 'fan')?.status).toBe('no_data')
  })
  it('usa faixa preditiva recebida para atenção e preserva ausência parcial', () => {
    const base = summary()
    const prediction = examples.find((item: { name: string }) => item.name === 'prediction_available_zero_rul').payload
    const items = buildTwinItems({ ...base, prediction, reading: { ...base.reading!, light_percent: null } }, true,
      { ...insights, prediction, availability: 'available', age_seconds: 0 })
    expect(items.find((item) => item.key === 'fan')?.status).toBe('attention')
    expect(items.find((item) => item.key === 'light_percent')?.status).toBe('no_data')
  })
})
