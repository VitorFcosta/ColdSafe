import type { ActuatorCommand } from './actuators'
import type { MonitoringSummary } from './monitoring-summary'
import type { ReadingStatus } from './monitoring-state'

export type MonitoringEquipment = Readonly<{
  equipment_id: string
  running: boolean
  led: Readonly<{ actuator_id: string; actual_state: boolean }>
  buzzer: Readonly<{ actuator_id: string; actual_state: boolean }>
}>

type Freshness = Readonly<{
  state: 'fresh' | 'stale' | 'no_data'
  last_event_id: string | null
  last_received_at: string | null
  age_seconds: number | null
  stale_after_seconds: 30
}>
type TemperatureAlert = Readonly<{
  alert_id: string
  equipment_id: string
  kind: 'temperature_low' | 'temperature_high'
  state: 'opened' | 'closed'
  source_event_id: string
}>
type Envelope = Readonly<{
  schema_version: 3
  event_id: string
  device_id: string
  device_record_id: string
  environment_id: string
  correlation_id: string
  occurred_at: string
  received_at: string
}>
export const predictionUnavailableReasons = ['no_model', 'insufficient_history', 'invalid_features', 'model_unavailable', 'stale_input'] as const
export type PredictionUnavailableReason = typeof predictionUnavailableReasons[number]
export type Prediction = Envelope & Readonly<{ type: 'prediction'; data: PredictionData }>
type PredictionData = Readonly<{
  equipment_id: string
  source_event_id: string
  input_received_at: string
  features_version: string
}> & (
  | Readonly<{ status: 'available'; model_id: string; model_version: string; health_score: number; rul_hours: number; reason: null }>
  | Readonly<{ status: 'unavailable'; model_id: string | null; model_version: string | null; health_score: null; rul_hours: null; reason: PredictionUnavailableReason }>
)
export type AiotEvent = Envelope & (
  | { type: 'telemetry'; data: { reading: NonNullable<MonitoringSummary['reading']>; equipment: MonitoringEquipment } }
  | { type: 'command_status'; data: ActuatorCommand }
  | { type: 'alert'; data: TemperatureAlert }
  | { type: 'freshness'; data: Freshness }
  | { type: 'prediction'; data: PredictionData }
)

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)
}
export function isDeviceId(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9._-]{1,64}$/.test(value)
}
export function isUtcTime(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|\+00:00)$/.test(value)) return false
  const time = Date.parse(value)
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value.slice(0, 10)
}
function inRange(value: unknown, min: number, max = Infinity): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
}
export function isThresholds(value: unknown): value is MonitoringSummary['thresholds'] {
  return isRecord(value) && inRange(value.min_c, -Infinity) && inRange(value.max_c, -Infinity) &&
    value.min_c < value.max_c && inRange(value.attention_margin_c, 0) &&
    value.attention_margin_c * 2 < value.max_c - value.min_c
}
export function calculateReadingStatus(temperature: number, thresholds: MonitoringSummary['thresholds']): ReadingStatus {
  if (temperature < thresholds.min_c || temperature > thresholds.max_c) return 'critical'
  if (temperature <= thresholds.min_c + thresholds.attention_margin_c || temperature >= thresholds.max_c - thresholds.attention_margin_c) return 'attention'
  return 'normal'
}
function isMeasurement(value: unknown, unit: string, min: number, max: number): value is { sensor_id: string; value: number; unit: string } {
  return isRecord(value) && isUuid(value.sensor_id) && value.unit === unit && inRange(value.value, min, max)
}
function isActuator(value: unknown): value is MonitoringEquipment['led'] {
  return isRecord(value) && isUuid(value.actuator_id) && typeof value.actual_state === 'boolean'
}
function parseFreshness(value: unknown): Freshness | null {
  if (!isRecord(value) || value.stale_after_seconds !== 30) return null
  if (value.state === 'no_data' && value.age_seconds === null && value.last_event_id === null && value.last_received_at === null) {
    return { state: 'no_data', age_seconds: null, last_event_id: null, last_received_at: null, stale_after_seconds: 30 }
  }
  if (!isUuid(value.last_event_id) || !isUtcTime(value.last_received_at) || !inRange(value.age_seconds, 0) ||
    !((value.state === 'fresh' && value.age_seconds <= 30) || (value.state === 'stale' && value.age_seconds > 30))) return null
  return { state: value.state, last_event_id: value.last_event_id, last_received_at: value.last_received_at, age_seconds: value.age_seconds, stale_after_seconds: 30 }
}

export function parseAiotEvent(value: unknown, deviceId: string, environmentId?: string): AiotEvent | null {
  if (!isRecord(value) || value.schema_version !== 3 || !isDeviceId(value.device_id) || value.device_id !== deviceId ||
    !isUuid(value.event_id) || !isUuid(value.device_record_id) || !isUuid(value.environment_id) ||
    (environmentId !== undefined && value.environment_id !== environmentId) || !isUuid(value.correlation_id) ||
    !isUtcTime(value.occurred_at) || !isUtcTime(value.received_at) || !isRecord(value.data)) return null
  const envelope: Envelope = {
    schema_version: 3, event_id: value.event_id, device_id: value.device_id, device_record_id: value.device_record_id,
    environment_id: value.environment_id, correlation_id: value.correlation_id, occurred_at: value.occurred_at, received_at: value.received_at,
  }
  const data = value.data
  if (value.type === 'telemetry') {
    const { equipment, measurements: m, actuators } = data
    if (!isRecord(equipment) || !isUuid(equipment.equipment_id) || typeof equipment.running !== 'boolean' ||
      !isRecord(m) || !isRecord(actuators) || !isActuator(actuators.led) || !isActuator(actuators.buzzer) ||
      actuators.led.actuator_id === actuators.buzzer.actuator_id ||
      !isMeasurement(m.ambient_temperature, 'degC', -40, 80) || !isMeasurement(m.humidity, 'percent', 0, 100) ||
      !isMeasurement(m.light, 'percent', 0, 100) || !isMeasurement(m.vibration, 'mm/s', 0, 100) ||
      !isMeasurement(m.motor_current, 'A', 0, 100) || !isMeasurement(m.motor_temperature, 'degC', -40, 200)) return null
    const sensor_ids = { ambient_temperature: m.ambient_temperature.sensor_id, humidity: m.humidity.sensor_id, light: m.light.sensor_id,
      vibration: m.vibration.sensor_id, motor_current: m.motor_current.sensor_id, motor_temperature: m.motor_temperature.sensor_id }
    if (new Set(Object.values(sensor_ids)).size !== 6) return null
    return { ...envelope, type: 'telemetry', data: {
      reading: { temperature_c: m.ambient_temperature.value, humidity_percent: m.humidity.value, light_percent: m.light.value,
        vibration_rms_mm_s: m.vibration.value, motor_current_a: m.motor_current.value, motor_temperature_c: m.motor_temperature.value,
        received_at: value.received_at, occurred_at: value.occurred_at, event_id: value.event_id, sensor_ids,
        device_record_id: value.device_record_id, environment_id: value.environment_id, equipment_id: equipment.equipment_id },
      equipment: { equipment_id: equipment.equipment_id, running: equipment.running, led: actuators.led, buzzer: actuators.buzzer },
    } }
  }
  if (value.type === 'prediction') {
    if (!isUuid(data.equipment_id) || !isUuid(data.source_event_id) || value.correlation_id !== data.source_event_id ||
      !isUtcTime(data.input_received_at) || typeof data.features_version !== 'string' ||
      !/^[A-Za-z0-9._+-]{1,64}$/.test(data.features_version)) return null
    const age = Date.parse(value.occurred_at) - Date.parse(data.input_received_at)
    if (age < 0 || Date.parse(value.received_at) < Date.parse(data.input_received_at)) return null
    const hasModel = isUuid(data.model_id) && typeof data.model_version === 'string' && /^[A-Za-z0-9._-]{1,64}$/.test(data.model_version)
    const available = data.status === 'available' && hasModel && data.reason === null &&
      inRange(data.health_score, 0, 100) && inRange(data.rul_hours, 0) && age <= 30_000
    const unavailable = data.status === 'unavailable' && data.health_score === null && data.rul_hours === null &&
      predictionUnavailableReasons.includes(data.reason as PredictionUnavailableReason) &&
      (data.reason === 'no_model' ? data.model_id === null && data.model_version === null : hasModel) &&
      (data.reason !== 'stale_input' || age > 30_000)
    if (!available && !unavailable) return null
    return { ...envelope, type: 'prediction', data: data as PredictionData }
  }
  if (value.type === 'command_status') {
    if (!isUuid(data.command_id) || !isUuid(data.actuator_id) || value.correlation_id !== data.command_id ||
      (data.actuator !== 'led' && data.actuator !== 'buzzer') || typeof data.desired_state !== 'boolean' ||
      !((data.status === 'confirmed' && data.confirmed_state === data.desired_state) ||
        ((data.status === 'pending' || data.status === 'unconfirmed' || data.status === 'rejected') && data.confirmed_state === null))) return null
    return { ...envelope, type: 'command_status', data: {
      schema_version: 3, command_id: data.command_id, actuator_id: data.actuator_id, device_id: deviceId,
      actuator: data.actuator, desired_state: data.desired_state, confirmed_state: data.confirmed_state, status: data.status,
      event_id: value.event_id, occurred_at: value.occurred_at, received_at: value.received_at,
    } }
  }
  if (value.type === 'freshness') {
    const freshness = parseFreshness(data)
    return freshness ? { ...envelope, type: 'freshness', data: freshness } : null
  }
  if (value.type === 'alert' && isUuid(data.alert_id) && isUuid(data.equipment_id) && isUuid(data.source_event_id) &&
    (data.kind === 'temperature_low' || data.kind === 'temperature_high') && (data.state === 'opened' || data.state === 'closed')) {
    return { ...envelope, type: 'alert', data: { alert_id: data.alert_id, equipment_id: data.equipment_id, source_event_id: data.source_event_id, kind: data.kind, state: data.state } }
  }
  return null
}

export function parseAiotCommand(value: unknown, deviceId?: string, environmentId?: string): ActuatorCommand | null {
  if (!isRecord(value) || !isDeviceId(value.device_id)) return null
  const event = parseAiotEvent(value, deviceId ?? value.device_id, environmentId)
  return event?.type === 'command_status' ? event.data : null
}

export function predictionMatchesReading(prediction: Prediction, reading: NonNullable<MonitoringSummary['reading']>): boolean {
  return prediction.data.source_event_id === reading.event_id &&
    prediction.correlation_id === reading.event_id && prediction.device_record_id === reading.device_record_id &&
    prediction.environment_id === reading.environment_id && prediction.data.equipment_id === reading.equipment_id &&
    Date.parse(prediction.data.input_received_at) === Date.parse(reading.received_at)
}

export function parseAiotSnapshot(value: unknown, deviceId?: string): MonitoringSummary | null {
  if (!isRecord(value) || !isRecord(value.environment) || !isUuid(value.environment.id) ||
    typeof value.environment.name !== 'string' || value.environment.name.trim() === '' ||
    !isRecord(value.device) || !isDeviceId(value.device.id) || (deviceId !== undefined && value.device.id !== deviceId) ||
    !isThresholds(value.thresholds)) return null
  const freshness = parseFreshness(value.freshness)
  if (!freshness || !isRecord(value.commands)) return null
  for (const actuator of ['led', 'buzzer'] as const) {
    const command = value.commands[actuator]
    if (command !== null && parseAiotCommand(command, value.device.id, value.environment.id)?.actuator !== actuator) return null
  }
  if (value.prediction_unavailable_reason != null && !predictionUnavailableReasons.includes(value.prediction_unavailable_reason as PredictionUnavailableReason)) return null
  const common = { environment: { id: value.environment.id, name: value.environment.name }, device: { id: value.device.id }, thresholds: value.thresholds }
  if (value.telemetry === null) {
    return freshness.state === 'no_data' && value.persistence === null ? { ...common, reading: null, freshness: null, status: 'no_data', persistence: null, prediction: null, prediction_unavailable_reason: null } : null
  }
  const event = parseAiotEvent(value.telemetry, value.device.id, value.environment.id)
  if (event?.type !== 'telemetry' || freshness.state === 'no_data' || freshness.last_event_id !== event.event_id ||
    Date.parse(freshness.last_received_at!) !== Date.parse(event.received_at) ||
    (value.persistence !== 'pending' && value.persistence !== 'persisted')) return null
  const candidate = parseAiotEvent(value.prediction, value.device.id, value.environment.id)
  const linked = candidate?.type === 'prediction' && predictionMatchesReading(candidate, event.data.reading) ? candidate : null
  const expired = linked?.data.status === 'available' && freshness.state === 'stale'
  const prediction = expired ? null : linked
  const reason = expired ? 'stale_input' : prediction?.data.reason ?? value.prediction_unavailable_reason ?? null
  return { ...common, ...event.data, persistence: value.persistence, prediction, prediction_unavailable_reason: reason as PredictionUnavailableReason | null,
    status: freshness.state === 'stale' ? 'stale' : calculateReadingStatus(event.data.reading.temperature_c, value.thresholds),
    freshness: { is_stale: freshness.state === 'stale', age_seconds: freshness.age_seconds! },
  }
}
