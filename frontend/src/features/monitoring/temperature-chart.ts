import type { HistoricalReading, HistoryPeriod } from './monitoring-history'

export type TemperatureChartData = Readonly<{
  labels: readonly string[]
  temperatures: readonly number[]
}>

export function buildTemperatureChart(
  readings: readonly HistoricalReading[],
  period?: HistoryPeriod,
): TemperatureChartData {
  return {
    labels: readings.map((reading) => formatReadingTime(reading.received_at, period)),
    temperatures: readings.map((reading) => reading.temperature_c),
  }
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

  return `No período de ${label}, foram recebidas ${count} ${readingLabel}: mínima de ${formatTemperature(minimum)} °C e máxima de ${formatTemperature(maximum)} °C.`
}

function formatReadingTime(timestamp: string, period?: HistoryPeriod): string {
  const options: Intl.DateTimeFormatOptions = {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  }

  if (period === '24h') {
    options.day = '2-digit'
    options.month = '2-digit'
  }

  return new Intl.DateTimeFormat('pt-BR', options).format(new Date(timestamp))
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
