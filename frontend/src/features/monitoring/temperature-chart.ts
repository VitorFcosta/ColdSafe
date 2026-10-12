import type { HistoricalReading, HistoryPeriod } from './monitoring-history'
import { STALE_AFTER_SECONDS } from './monitoring-state'

export type TemperatureChartData = Readonly<{
  points: readonly Readonly<{ x: number; y: number | null }>[]
  gaps: number
}>

export function buildTemperatureChart(readings: readonly HistoricalReading[]): TemperatureChartData {
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
    points.push({ x, y: reading.temperature_c })
  }
  return { points, gaps }
}

export function describeTemperatureRange(
  readings: readonly HistoricalReading[],
  period: HistoryPeriod,
): string {
  const label = periodLabel(period)
  if (readings.length === 0) {
    return `Não há leituras de temperatura nas últimas ${label}.`
  }

  const temperatures = readings.map((reading) => reading.temperature_c)
  const minimum = Math.min(...temperatures)
  const maximum = Math.max(...temperatures)
  const count = readings.length
  const readingLabel = count === 1 ? 'leitura' : 'leituras'

  return `No período de ${label}, foram retornadas ${count} ${readingLabel}: mínima de ${formatTemperature(minimum)} °C e máxima de ${formatTemperature(maximum)} °C.`
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

function formatTemperature(value: number): string {
  return value.toLocaleString('pt-BR', { maximumFractionDigits: 1 })
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
