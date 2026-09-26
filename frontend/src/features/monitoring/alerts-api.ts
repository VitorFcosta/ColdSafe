export type AlertRecord = Readonly<{
  alert_id: string
  device_id: string
  kind: 'temperature_low' | 'temperature_high'
  opened_at: string
  closed_at: string | null
  status: 'open' | 'closed'
}>

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export async function fetchAlerts(options: {
  baseUrl: string
  deviceId: string
  start: string
  end: string
  auth: string
  fetcher: Fetcher
}): Promise<readonly AlertRecord[]> {
  const { baseUrl, deviceId, start, end, auth, fetcher } = options
  const query = new URLSearchParams({ device_id: deviceId, start, end, limit: '300' })
  const response = await fetcher(`${baseUrl.replace(/\/+$/, '')}/api/v1/alerts?${query}`, {
    headers: { accept: 'application/json', authorization: `Bearer ${auth}` },
  })
  if (!response.ok) throw new Error('Não foi possível consultar os alertas.')

  const body: unknown = await response.json()
  if (!isRecord(body) || body.success !== true || !isRecord(body.data) ||
      !Array.isArray(body.data.alerts) || !body.data.alerts.every(isAlert) ||
      !isRecord(body.meta) || body.meta.device_id !== deviceId ||
      body.meta.count !== body.data.alerts.length ||
      body.data.alerts.some((alert: AlertRecord) => alert.device_id !== deviceId)) {
    throw new Error('A API retornou alertas inválidos.')
  }
  return body.data.alerts
}

function isAlert(value: unknown): value is AlertRecord {
  return isRecord(value) &&
    typeof value.alert_id === 'string' &&
    typeof value.device_id === 'string' &&
    (value.kind === 'temperature_low' || value.kind === 'temperature_high') &&
    isDate(value.opened_at) &&
    (value.closed_at === null || isDate(value.closed_at)) &&
    (value.status === 'open' || value.status === 'closed') &&
    (value.status === 'open' ? value.closed_at === null : value.closed_at !== null)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isDate(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value))
}
