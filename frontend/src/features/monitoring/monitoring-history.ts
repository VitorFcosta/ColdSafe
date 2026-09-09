import type { ReadingStatus } from './monitoring-state'

export const historyPeriods = ['15m', '1h', '6h', '24h'] as const

export type HistoryPeriod = (typeof historyPeriods)[number]

export type HistoricalReading = Readonly<{
  temperature_c: number
  humidity_percent: number
  received_at: string
  status: ReadingStatus
}>

export type MonitoringHistory = Readonly<{
  deviceId: string
  readings: readonly HistoricalReading[]
  start: string
  end: string
  limit: number
}>

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

type FetchMonitoringHistoryOptions = Readonly<{
  baseUrl: string
  deviceId: string
  period: HistoryPeriod
  fetcher: Fetcher
}>

const readingStatuses: readonly ReadingStatus[] = [
  'normal',
  'attention',
  'critical',
  'no_data',
  'stale',
]

export async function fetchMonitoringHistory({
  baseUrl,
  deviceId,
  period,
  fetcher,
}: FetchMonitoringHistoryOptions): Promise<MonitoringHistory> {
  const query = new URLSearchParams({
    device_id: deviceId,
    period,
    limit: '300',
  })
  const response = await fetcher(
    `${baseUrl.replace(/\/+$/, '')}/api/v1/readings?${query.toString()}`,
    { headers: { accept: 'application/json' } },
  )

  if (!response.ok) {
    throw new Error('Não foi possível consultar o histórico de temperatura.')
  }

  const history = parseMonitoringHistory(await response.json())
  if (history === null) {
    throw new Error('A API retornou um histórico inválido.')
  }

  return history
}

function parseMonitoringHistory(value: unknown): MonitoringHistory | null {
  if (!isRecord(value) || value.success !== true || !isRecord(value.data) || !isRecord(value.meta)) {
    return null
  }

  const { data, meta } = value
  if (
    !Array.isArray(data.readings) ||
    !data.readings.every(isHistoricalReading) ||
    !isString(meta.device_id) ||
    !isIsoDate(meta.start) ||
    !isIsoDate(meta.end) ||
    !isNonNegativeInteger(meta.count) ||
    !isPositiveInteger(meta.limit) ||
    meta.count !== data.readings.length
  ) {
    return null
  }

  return {
    deviceId: meta.device_id,
    readings: data.readings,
    start: meta.start,
    end: meta.end,
    limit: meta.limit,
  }
}

function isHistoricalReading(value: unknown): value is HistoricalReading {
  return (
    isRecord(value) &&
    isFiniteNumber(value.temperature_c) &&
    isFiniteNumber(value.humidity_percent) &&
    isIsoDate(value.received_at) &&
    isReadingStatus(value.status)
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isReadingStatus(value: unknown): value is ReadingStatus {
  return typeof value === 'string' && readingStatuses.includes(value as ReadingStatus)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isIsoDate(value: unknown): value is string {
  return isString(value) && !Number.isNaN(Date.parse(value))
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0
}
