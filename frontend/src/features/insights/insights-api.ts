import type { Device } from '../account/catalog'
import { isRecord, isUtcTime, isUuid, parseAiotEvent, type Prediction } from '../monitoring/aiot-api'
import { STALE_AFTER_SECONDS } from '../monitoring/monitoring-state'

export type PredictiveRules = {
  health_critical: number
  health_recovery: number
  rul_critical_hours: number
  rul_recovery_hours: number
  open_count: number
  close_count: number
}
export type PredictiveAlert = Readonly<{
  alert_id: string
  kind: 'predictive_failure'
  opened_at: string
  source_event_id: string
  prediction_event_id: string
}>
export type InsightsSnapshot = Readonly<{
  device_id: string
  equipment_id: string
  rules: PredictiveRules
  prediction: Prediction | null
  availability: 'available' | 'unavailable' | 'stale' | 'no_data'
  age_seconds: number | null
  trend: 'improving' | 'declining' | 'stable' | 'unknown'
  active_alerts: PredictiveAlert[]
}>

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
export function parsePredictiveRules(value: unknown): PredictiveRules | null {
  if (!isRecord(value) || Object.keys(value).length !== 6 ||
    !finite(value.health_critical) || !finite(value.health_recovery) || value.health_critical < 0 || value.health_recovery > 100 || value.health_critical >= value.health_recovery ||
    !finite(value.rul_critical_hours) || !finite(value.rul_recovery_hours) || value.rul_critical_hours < 0 || value.rul_critical_hours >= value.rul_recovery_hours ||
    !finite(value.open_count) || !Number.isInteger(value.open_count) || value.open_count < 1 || value.open_count > 100 ||
    !finite(value.close_count) || !Number.isInteger(value.close_count) || value.close_count < 1 || value.close_count > 100) return null
  return { health_critical: value.health_critical, health_recovery: value.health_recovery,
    rul_critical_hours: value.rul_critical_hours, rul_recovery_hours: value.rul_recovery_hours,
    open_count: value.open_count, close_count: value.close_count }
}

export function parseInsights(value: unknown, device: Device): InsightsSnapshot | null {
  if (!isRecord(value) || value.device_id !== device.mqtt_device_id || !isUuid(value.equipment_id) ||
    !['available', 'unavailable', 'stale', 'no_data'].includes(String(value.availability)) ||
    !['improving', 'declining', 'stable', 'unknown'].includes(String(value.trend)) ||
    !Array.isArray(value.active_alerts)) return null
  const rules = parsePredictiveRules(value.rules)
  if (!rules) return null
  const candidate = value.prediction === null ? null : parseAiotEvent(value.prediction, device.mqtt_device_id, device.environment_id)
  if (value.prediction !== null && (candidate?.type !== 'prediction' || candidate.device_record_id !== device.id || candidate.data.equipment_id !== value.equipment_id)) return null
  const prediction = candidate?.type === 'prediction' ? candidate : null
  if (prediction === null) {
    const noData = value.availability === 'no_data' && (value.age_seconds === null || (finite(value.age_seconds) && value.age_seconds >= 0 && value.age_seconds <= STALE_AFTER_SECONDS))
    const stale = value.availability === 'stale' && finite(value.age_seconds) && value.age_seconds > STALE_AFTER_SECONDS
    if ((!noData && !stale) || value.trend !== 'unknown') return null
  } else {
    if (!finite(value.age_seconds) || value.age_seconds < 0 || value.availability === 'no_data' ||
      (value.availability === 'available' && (prediction.data.status !== 'available' || value.age_seconds > STALE_AFTER_SECONDS)) ||
      (value.availability === 'unavailable' && (prediction.data.status !== 'unavailable' || value.age_seconds > STALE_AFTER_SECONDS)) ||
      (value.availability === 'stale' && value.age_seconds <= STALE_AFTER_SECONDS)) return null
  }
  if (value.availability !== 'available' && value.trend !== 'unknown') return null
  const alerts: PredictiveAlert[] = []
  for (const alert of value.active_alerts) {
    if (!isRecord(alert) || !isUuid(alert.alert_id) || alert.kind !== 'predictive_failure' ||
      !isUtcTime(alert.opened_at) || !isUuid(alert.source_event_id) || !isUuid(alert.prediction_event_id) ||
      alerts.some((item) => item.alert_id === alert.alert_id)) return null
    alerts.push({ alert_id: alert.alert_id, kind: alert.kind, opened_at: alert.opened_at,
      source_event_id: alert.source_event_id, prediction_event_id: alert.prediction_event_id })
  }
  return { device_id: value.device_id, equipment_id: value.equipment_id, rules, prediction,
    availability: value.availability as InsightsSnapshot['availability'], age_seconds: value.age_seconds as number | null,
    trend: value.trend as InsightsSnapshot['trend'], active_alerts: alerts }
}

export class InsightsAccessError extends Error {
  constructor(readonly status: number) { super('Acesso aos Insights indisponível.') }
}

async function requestInsights(token: string, device: Device, signal?: AbortSignal, rules?: PredictiveRules): Promise<unknown> {
  const response = await fetch(`${baseUrl}/api/v3/insights${rules ? '/rules' : ''}?device_id=${encodeURIComponent(device.mqtt_device_id)}`, {
    method: rules ? 'PUT' : 'GET', signal, cache: 'no-store',
    headers: { accept: 'application/json', authorization: `Bearer ${token}`, ...(rules ? { 'content-type': 'application/json' } : {}) },
    ...(rules ? { body: JSON.stringify(rules) } : {}),
  })
  if ([401, 403, 404].includes(response.status)) throw new InsightsAccessError(response.status)
  if (!response.ok) throw new Error('Não foi possível consultar os Insights.')
  let payload: unknown
  try { payload = await response.json() } catch { throw new Error('Resposta de Insights inválida.') }
  if (!isRecord(payload) || payload.success !== true || !isRecord(payload.meta) || payload.meta.schema_version !== 3) throw new Error('Resposta de Insights inválida.')
  return payload.data
}

export async function fetchInsights(token: string, device: Device, signal?: AbortSignal): Promise<InsightsSnapshot> {
  const result = parseInsights(await requestInsights(token, device, signal), device)
  if (!result) throw new Error('Resposta de Insights inválida.')
  return result
}

export async function savePredictiveRules(token: string, device: Device, rules: PredictiveRules, signal?: AbortSignal): Promise<PredictiveRules> {
  if (!parsePredictiveRules(rules)) throw new Error('Regras inválidas. Confira os limites e as contagens.')
  const result = parsePredictiveRules(await requestInsights(token, device, signal, rules))
  if (!result) throw new Error('Resposta de regras inválida.')
  return result
}
