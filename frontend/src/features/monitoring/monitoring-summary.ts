import type { ReadingStatus } from './monitoring-state'

export type MonitoringSummary = Readonly<{
  environment: Readonly<{ id: string; name: string }>
  device: Readonly<{ id: string }>
  reading: Readonly<{
    temperature_c: number
    humidity_percent: number
    received_at: string
  }> | null
  status: ReadingStatus
  freshness: Readonly<{ is_stale: boolean; age_seconds: number }> | null
  thresholds: Readonly<{
    min_c: number
    max_c: number
    attention_margin_c: number
  }>
}>

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

type FetchMonitoringSummaryOptions = Readonly<{
  baseUrl: string
  fetcher: Fetcher
}>

const monitoringStatuses: readonly ReadingStatus[] = [
  'normal',
  'attention',
  'critical',
  'no_data',
  'stale',
]

export async function fetchMonitoringSummary({
  baseUrl,
  fetcher,
}: FetchMonitoringSummaryOptions): Promise<MonitoringSummary> {
  const response = await fetcher(
    `${baseUrl.replace(/\/+$/, '')}/api/v1/monitoring/summary`,
    { headers: { accept: 'application/json' } },
  )

  if (!response.ok) {
    throw new Error('Não foi possível consultar o diagnóstico atual.')
  }

  const body: unknown = await response.json()
  const summary = parseMonitoringSummary(body)
  if (summary === null) {
    throw new Error('A API retornou um diagnóstico inválido.')
  }

  return summary
}

function parseMonitoringSummary(value: unknown): MonitoringSummary | null {
  if (!isRecord(value) || value.success !== true || !isRecord(value.data)) {
    return null
  }

  const { data } = value
  if (
    !isEnvironment(data.environment) ||
    !isDevice(data.device) ||
    !isReading(data.reading) ||
    !isFreshness(data.freshness) ||
    !isThresholds(data.thresholds) ||
    !isReadingStatus(data.status)
  ) {
    return null
  }

  return {
    environment: data.environment,
    device: data.device,
    reading: data.reading,
    status: data.status,
    freshness: data.freshness,
    thresholds: data.thresholds,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isEnvironment(
  value: unknown,
): value is MonitoringSummary['environment'] {
  return isRecord(value) && isString(value.id) && isString(value.name)
}

function isDevice(value: unknown): value is MonitoringSummary['device'] {
  return isRecord(value) && isString(value.id)
}

function isReading(value: unknown): value is MonitoringSummary['reading'] {
  return (
    value === null ||
    (isRecord(value) &&
      isFiniteNumber(value.temperature_c) &&
      isFiniteNumber(value.humidity_percent) &&
      isString(value.received_at))
  )
}

function isFreshness(value: unknown): value is MonitoringSummary['freshness'] {
  return (
    value === null ||
    (isRecord(value) &&
      typeof value.is_stale === 'boolean' &&
      isFiniteNumber(value.age_seconds))
  )
}

function isThresholds(value: unknown): value is MonitoringSummary['thresholds'] {
  return (
    isRecord(value) &&
    isFiniteNumber(value.min_c) &&
    isFiniteNumber(value.max_c) &&
    isFiniteNumber(value.attention_margin_c)
  )
}

function isReadingStatus(value: unknown): value is ReadingStatus {
  return typeof value === 'string' && monitoringStatuses.includes(value as ReadingStatus)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}
