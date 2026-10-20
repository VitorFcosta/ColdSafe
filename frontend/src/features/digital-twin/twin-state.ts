import type { InsightsSnapshot } from '../insights/insights-api'
import { calculateReadingStatus, sensorRoles } from '../monitoring/aiot-api'
import type { MonitoringSummary } from '../monitoring/monitoring-summary'
import { sensorMetrics } from '../monitoring/sensor-metrics'

export type TwinStatus = 'normal' | 'attention' | 'critical' | 'no_data'
export type TwinVisualState = Readonly<{
  running: boolean
  vibration: number | null
  temperature: number
  light: number | null
  led: boolean
  buzzer: boolean
}>

export function buildTwinVisualState(summary: MonitoringSummary | null, fresh: boolean): TwinVisualState | null {
  if (!fresh || !summary?.reading || !summary.equipment) return null
  return {
    running: summary.equipment.running, vibration: summary.reading.vibration_rms_mm_s ?? null,
    temperature: summary.reading.temperature_c, light: summary.reading.light_percent ?? null,
    led: summary.equipment.led.actual_state, buzzer: summary.equipment.buzzer.actual_state,
  }
}

export type TwinItem = Readonly<{
  id: string | null
  key: string
  label: string
  kind: 'sensor' | 'actuator' | 'equipment'
  value: string
  status: TwinStatus
  position: readonly [number, number, number]
}>
export const twinStatusLabels: Record<TwinStatus, string> = { normal: 'Normal', attention: 'Atenção', critical: 'Crítico', no_data: 'Sem dados' }
export const twinColors: Record<TwinStatus, number> = { normal: 0x197854, attention: 0xa96409, critical: 0xc3353c, no_data: 0x667681 }
const positions: readonly (readonly [number, number, number])[] = [
  [-3, 1.6, 0], [-3, 0.4, 0], [-3, -0.8, 0], [3, 1.6, 0], [3, 0.4, 0], [3, -0.8, 0],
]
const noData = 'Sem dados atuais'

function fanStatus(summary: MonitoringSummary, insights: InsightsSnapshot | null): TwinStatus {
  if (!insights || insights.device_id !== summary.device.id || insights.equipment_id !== summary.equipment?.equipment_id) return 'no_data'
  if (insights.active_alerts.length) return 'critical'
  const prediction = summary.prediction
  if (insights.availability !== 'available' || prediction?.data.status !== 'available') return 'no_data'
  return prediction.data.health_score < insights.rules.health_recovery || prediction.data.rul_hours < insights.rules.rul_recovery_hours ? 'attention' : 'normal'
}

export function buildTwinItems(summary: MonitoringSummary | null, fresh: boolean, insights: InsightsSnapshot | null): TwinItem[] {
  const reading = fresh ? summary?.reading : null
  const equipment = fresh ? summary?.equipment : null
  const sensors: TwinItem[] = sensorMetrics.map((metric, index) => {
    const role = sensorRoles[index]!
    const value = reading?.[metric.key]
    return { key: metric.key, id: summary?.inventory?.sensors[role] ?? summary?.reading?.sensor_ids?.[role] ?? null,
      label: metric.label, kind: 'sensor', position: positions[index]!,
      value: value == null ? noData : `${value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} ${metric.unit}`,
      status: value == null ? 'no_data' : metric.key === 'temperature_c' ? calculateReadingStatus(value, summary!.thresholds) : 'normal' }
  })
  const actuators: TwinItem[] = (['led', 'buzzer'] as const).map((key, index) => ({
    key, id: summary?.inventory?.actuators[key] ?? summary?.equipment?.[key].actuator_id ?? null,
    label: key === 'led' ? 'LED' : 'Buzzer', kind: 'actuator', position: [index ? 1 : -1, -2, 0],
    value: equipment ? equipment[key].actual_state ? 'Ligado' : 'Desligado' : noData,
    status: !equipment ? 'no_data' : key === 'buzzer' && equipment.buzzer.actual_state ? 'critical' : 'normal',
  }))
  return [...sensors, ...actuators, { key: 'fan', id: summary?.inventory?.equipment_id ?? summary?.equipment?.equipment_id ?? null,
    label: 'Ventilador', kind: 'equipment', position: [0, 0.4, 0],
    value: equipment ? equipment.running ? 'Em operação' : 'Parado' : noData,
    status: equipment && summary ? fanStatus(summary, insights) : 'no_data' }]
}
