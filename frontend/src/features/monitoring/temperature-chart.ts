import type { HistoricalReading, HistoryPeriod } from './monitoring-history'
import { STALE_AFTER_SECONDS } from './monitoring-state'
import { sensorMetricByKey, type SensorMetricKey } from './sensor-metrics'

export type TemperatureChartData = Readonly<{
  points: readonly Readonly<{ x: number; y: number | null }>[]
  gaps: number
}>

export function buildTemperatureChart(
  readings: readonly HistoricalReading[],
  metric: SensorMetricKey = 'temperature_c',
): TemperatureChartData {
  const sorted = [...readings].sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at))
  const points: { x: number; y: number | null }[] = []
  let gaps = 0
  for (const reading of sorted) {
    const x = Date.parse(reading.received_at)
    const previous = points.at(-1)
    if (previous && x - previous.x > STALE_AFTER_SECONDS * 1000) {
      points.push({ x: previous.x + (x - previous.x) / 2, y: null })
      gaps++
    }
    points.push({ x, y: reading[metric] ?? null })
  }
  return { points, gaps }
}

export function describeTemperatureRange(
  readings: readonly HistoricalReading[],
  period: HistoryPeriod,
  metric: SensorMetricKey = 'temperature_c',
): string {
  const label = periodLabel(period)
  const sensor = sensorMetricByKey[metric]
  const metricLabel = metric === 'temperature_c' ? 'Temperatura' : sensor.label
  if (readings.length === 0) {
    return `Não há leituras de ${metricLabel.charAt(0).toLowerCase() + metricLabel.slice(1)} nas últimas ${label}.`
  }

  const values = readings.map((reading) => reading[metric]).filter((value): value is number => value != null)
  if (values.length === 0) {
    return `${metricLabel} indisponível nas ${readings.length} leituras retornadas no período de ${label}. Sensores novos podem estar ausentes no histórico legado.`
  }
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const count = readings.length
  const readingLabel = count === 1 ? 'leitura' : 'leituras'
  const missing = readings.length - values.length

  return `No período de ${label}, foram retornadas ${count} ${readingLabel}: ${metric === 'temperature_c' ? '' : `${metricLabel}: `}mínima de ${formatMetricValue(minimum, metric)} ${sensor.unit} e máxima de ${formatMetricValue(maximum, metric)} ${sensor.unit}.` +
    (missing ? ` ${missing} ${missing === 1 ? 'registro sem essa medição' : 'registros sem essa medição'}; a linha é interrompida nesses pontos.` : '')
}

export function formatHistoryTick(timestamp: number, timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  const date = new Date(timestamp)
  const day = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', timeZone }).format(date)
  const time = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone }).format(date)
  return `${day} ${time}`
}

export function formatReadingTime(value: string, timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short', timeZone,
  }).format(new Date(value))
}

export function describeHistoryCoverage(
  readings: readonly HistoricalReading[],
  limit: number,
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone,
): string {
  if (!readings.length) return 'Nenhuma leitura retornada no intervalo solicitado.'
  const times = readings.map((reading) => Date.parse(reading.received_at))
  const first = formatReadingTime(new Date(Math.min(...times)).toISOString(), timeZone)
  const last = formatReadingTime(new Date(Math.max(...times)).toISOString(), timeZone)
  const count = readings.length
  return `${count} ${count === 1 ? 'leitura retornada' : 'leituras retornadas'}; primeira em ${first}, última em ${last}. ` +
    (count >= limit
      ? `Limite de ${limit} atingido: podem existir leituras anteriores no período.`
      : 'A contagem não comprova coleta contínua entre esses horários.')
}

export function formatMetricValue(value: number, metric: SensorMetricKey): string {
  return value.toLocaleString('pt-BR', { maximumFractionDigits: metric === 'motor_current_a' || metric === 'vibration_rms_mm_s' ? 3 : 1 })
}

function periodLabel(period: HistoryPeriod): string {
  const labels: Readonly<Record<HistoryPeriod, string>> = {
    '15m': '15 minutos',
    '1h': '1 hora',
    '6h': '6 horas',
    '24h': '24 horas',
  }

  return labels[period]
}
