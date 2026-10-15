import type { ReadingStatus } from './monitoring-state'
import { calculateReadingStatus, isRecord, isThresholds, isUtcTime, parseAiotEvent } from './aiot-api'
import { aiotEnabled } from './monitoring-version'
import type { MonitoringSummary } from './monitoring-summary'

export const historyPeriods = ['15m', '1h', '6h', '24h'] as const

export type HistoryPeriod = (typeof historyPeriods)[number]

export type HistoricalReading = NonNullable<MonitoringSummary['reading']> & Readonly<{
  status: ReadingStatus
  persistence?: 'pending' | 'persisted'
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
  token?: string
  start?: string
  end?: string
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
  token,
  start,
  end,
}: FetchMonitoringHistoryOptions): Promise<MonitoringHistory> {
  const query = new URLSearchParams({
    device_id: deviceId,
    ...(start && end ? { start, end } : { period }),
    limit: '300',
  })
  const response = await fetcher(
    `${baseUrl.replace(/\/+$/, '')}/api/${aiotEnabled ? 'v3' : 'v1'}/readings?${query.toString()}`,
    { headers: { accept: 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) } },
  )

  if (!response.ok) {
    throw new Error('Não foi possível consultar o histórico de temperatura.')
  }

  const body: unknown = await response.json()
  const history = aiotEnabled ? parseAiotHistory(body, deviceId) : parseMonitoringHistory(body)
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
    (value.light_percent === undefined || value.light_percent === null || isFiniteNumber(value.light_percent)) &&
    isIsoDate(value.received_at) &&
    isReadingStatus(value.status)
  )
}

function parseAiotHistory(value: unknown, deviceId: string): MonitoringHistory | null {
  if (!isRecord(value) || value.success !== true || !Array.isArray(value.data) || !isRecord(value.meta)) return null
  const { meta, data } = value
  if (meta.device_id !== deviceId || !isUtcTime(meta.start) || !isUtcTime(meta.end) ||
    Date.parse(meta.start) > Date.parse(meta.end) || !isNonNegativeInteger(meta.count) || meta.count !== data.length ||
    !isPositiveInteger(meta.limit) || meta.limit > 1000 || data.length > meta.limit || !isThresholds(meta.thresholds)) return null
  const readings: HistoricalReading[] = []
  for (const row of data) {
    if (!isRecord(row) || (row.persistence !== 'pending' && row.persistence !== 'persisted')) return null
    const event = parseAiotEvent(row.telemetry, deviceId)
    if (event?.type !== 'telemetry' || Date.parse(event.received_at) < Date.parse(meta.start) || Date.parse(event.received_at) > Date.parse(meta.end)) return null
    readings.push({ ...event.data.reading, status: calculateReadingStatus(event.data.reading.temperature_c, meta.thresholds), persistence: row.persistence })
  }
  readings.sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at) || (a.event_id ?? '').localeCompare(b.event_id ?? ''))
  return { deviceId, readings, start: meta.start, end: meta.end, limit: meta.limit }
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
