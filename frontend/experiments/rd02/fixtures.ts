import examples from '../../../contracts/examples/aiot.valid.json'
import { parseAiotSnapshot } from '../../src/features/monitoring/aiot-api'
import type { MonitoringSummary } from '../../src/features/monitoring/monitoring-summary'

export type ExperimentState = 'active' | 'stale' | 'stopped' | 'zero' | 'changed' | 'empty'
const entry = examples.find((entry) => entry.name === 'telemetry_received')
if (!entry) throw new Error('Fixture de telemetria ausente no ensaio RD-02.')
const telemetry = entry.payload as { event_id: string; device_id: string; environment_id: string; received_at: string; data: { equipment: { equipment_id: string }; measurements: Record<string, { sensor_id: string }>; actuators: Record<'led' | 'buzzer', { actuator_id: string }> } }
const inventory = {
  equipment_id: telemetry.data.equipment.equipment_id,
  sensors: Object.fromEntries(Object.entries(telemetry.data.measurements).map(([key, value]) => [key, value.sensor_id])),
  actuators: { led: telemetry.data.actuators.led.actuator_id, buzzer: telemetry.data.actuators.buzzer.actuator_id },
}
const parsed = parseAiotSnapshot({
  environment: { id: telemetry.environment_id, name: 'Laboratório de ensaio — dados simulados' }, device: { id: telemetry.device_id },
  inventory, telemetry, prediction: null, persistence: 'persisted', thresholds: { min_c: 2, max_c: 8, attention_margin_c: .5 },
  freshness: { state: 'fresh', age_seconds: 0, last_event_id: telemetry.event_id, last_received_at: telemetry.received_at, stale_after_seconds: 30 },
  commands: { led: null, buzzer: null },
})
if (!parsed?.reading || !parsed.equipment) throw new Error('Fixture AIoT inválida para o experimento RD-02.')
const base = parsed

export function controlledSummary(state: ExperimentState): MonitoringSummary {
  if (state === 'empty') return { ...base, reading: null, equipment: undefined }
  const zero = state === 'zero'
  const stopped = state === 'stopped' || zero
  return { ...base,
    reading: { ...base.reading!, temperature_c: zero ? 0 : state === 'changed' ? 7.5 : 6.5,
      light_percent: zero ? 0 : 65, vibration_rms_mm_s: stopped ? 0 : 2,
      motor_current_a: zero ? 0 : 1.2, motor_temperature_c: zero ? 0 : 36, humidity_percent: zero ? 0 : 65 },
    equipment: { ...base.equipment!, running: !stopped,
      led: { ...base.equipment!.led, actual_state: state === 'changed' },
      buzzer: { ...base.equipment!.buzzer, actual_state: state === 'changed' } },
    freshness: { is_stale: state === 'stale', age_seconds: state === 'stale' ? 35 : 0 },
  }
}
