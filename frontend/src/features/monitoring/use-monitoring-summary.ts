import { computed, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'
import { clearSession, sessionToken } from '../account/session'

import { resolveMonitoringState, STALE_AFTER_SECONDS, type SummaryState } from './monitoring-state'
import { fetchMonitoringSummary, type MonitoringSummary } from './monitoring-summary'
import { parseAiotEvent, predictionMatchesReading, type AiotEvent } from './aiot-api'
import { aiotEnabled } from './monitoring-version'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function formatFreshness(ageSeconds: number | undefined) {
  if (ageSeconds === undefined) return 'Sem leitura recebida'
  if (ageSeconds < 5) return 'Agora mesmo'
  if (ageSeconds < 60) return `Há ${Math.floor(ageSeconds)} s`
  if (ageSeconds < 3600) return `Há ${Math.floor(ageSeconds / 60)} min`
  if (ageSeconds < 86400) return `Há ${Math.floor(ageSeconds / 3600)} h`
  const days = Math.floor(ageSeconds / 86400)
  return `Há ${days} ${days === 1 ? 'dia' : 'dias'}`
}

type LegacyMonitoringEvent = Readonly<{
  schema_version: 2
  type: 'reading' | 'command_status' | 'alert'
  device_id: string
  environment_id: string
  occurred_at: string
  data: unknown
}>
export type MonitoringEvent = LegacyMonitoringEvent | AiotEvent

function isMonitoringEvent(value: unknown, deviceId: string): value is LegacyMonitoringEvent {
  if (typeof value !== 'object' || value === null) return false
  const event = value as Record<string, unknown>
  return event.schema_version === 2 &&
    (event.type === 'reading' || event.type === 'command_status' || event.type === 'alert') &&
    event.device_id === deviceId && typeof event.environment_id === 'string' &&
    typeof event.occurred_at === 'string' && typeof event.data === 'object' && event.data !== null
}

export function useMonitoringSummary(
  token: Ref<string | null>,
  deviceId: Ref<string | null>,
  onEvent?: (event: MonitoringEvent) => void,
) {
  const summary = ref<MonitoringSummary | null>(null)
  const summaryState = ref<SummaryState>({ phase: 'loading' })
  const refreshRevision = ref(0)
  const connectionState = ref<'connecting' | 'connected' | 'offline' | 'unauthorized' | 'forbidden'>('offline')
  const clock = ref(Date.now())
  const summaryRequestedAt = ref(Date.now())
  let clockTimer: ReturnType<typeof setInterval> | null = null
  let socket: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let selectionRevision = 0
  let latestSummaryRequest = 0
  let disposed = false
  const recentEvents = new Set<string>()

  const ageSeconds = computed(() => !summary.value?.freshness
    ? null
    : summary.value.freshness.age_seconds + Math.max(0, clock.value - summaryRequestedAt.value) / 1000)

  const monitoringState = computed(() => resolveMonitoringState({
    summary: summaryState.value.phase === 'ready' && summary.value?.reading && ageSeconds.value !== null && ageSeconds.value > STALE_AFTER_SECONDS
      ? { phase: 'ready', status: 'stale' }
      : summaryState.value,
    history: { phase: 'idle' },
  }))

  async function loadSummary() {
    const currentToken = token.value
    const currentDevice = deviceId.value
    if (!currentToken || !currentDevice) return
    const requestedAt = Date.now()
    const requestId = ++latestSummaryRequest
    if (summary.value === null) summaryState.value = { phase: 'loading' }

    try {
      const result = await fetchMonitoringSummary({
        baseUrl: apiBaseUrl,
        fetcher: fetch,
        token: currentToken,
        deviceId: currentDevice,
      })
      if (requestId !== latestSummaryRequest || token.value !== currentToken || deviceId.value !== currentDevice) return
      if (result.device.id !== currentDevice) throw new Error('Dispositivo inesperado no resumo.')
      clock.value = Math.max(clock.value, Date.now())
      summaryRequestedAt.value = requestedAt
      summary.value = result
      summaryState.value = { phase: 'ready', status: result.status }
      refreshRevision.value += 1
    } catch {
      if (requestId !== latestSummaryRequest || token.value !== currentToken || deviceId.value !== currentDevice) return
      summary.value = null
      summaryState.value = { phase: 'error' }
    }
  }

  function disconnect() {
    if (reconnectTimer !== null) clearTimeout(reconnectTimer)
    reconnectTimer = null
    if (socket !== null) {
      const old = socket
      socket = null
      old.onopen = null
      old.onmessage = null
      old.onclose = null
      old.onerror = null
      old.close()
    }
  }

  async function connect(revision: number) {
    const currentToken = token.value
    const currentDevice = deviceId.value
    if (!currentToken || !currentDevice || disposed || revision !== selectionRevision) return
    connectionState.value = 'connecting'
    let ticket: string
    try {
      const response = await fetch(`${apiBaseUrl.replace(/\/+$/, '')}/api/v1/auth/ws-ticket`, {
        method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${currentToken}` },
        body: JSON.stringify({ device_id: currentDevice }),
      })
      if (disposed || revision !== selectionRevision || token.value !== currentToken || deviceId.value !== currentDevice) return
      if (response.status === 401) {
        connectionState.value = 'unauthorized'
        if (sessionToken.value === currentToken) clearSession()
        token.value = null
        return
      }
      if (response.status === 403) { connectionState.value = 'forbidden'; return }
      const payload = await response.json()
      if (!response.ok || payload?.success !== true || typeof payload.data?.ticket !== 'string' ||
        !payload.data.ticket || !(Date.parse(payload.data.expires_at) > Date.now())) {
        throw new Error('Ticket inválido.')
      }
      ticket = payload.data.ticket
    } catch {
      if (disposed || revision !== selectionRevision || token.value !== currentToken || deviceId.value !== currentDevice) return
      connectionState.value = 'offline'
      reconnectTimer = setTimeout(() => { void connect(revision) }, 2000)
      return
    }
    if (disposed || revision !== selectionRevision || token.value !== currentToken || deviceId.value !== currentDevice) return
    const url = new URL(`${apiBaseUrl.replace(/\/+$/, '')}/api/${aiotEnabled ? 'v3' : 'v1'}/events`, window.location.origin)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.searchParams.set('device_id', currentDevice)
    const nextSocket = new WebSocket(url)
    socket = nextSocket

    nextSocket.onopen = () => {
      if (disposed || revision !== selectionRevision || token.value !== currentToken || deviceId.value !== currentDevice) return
      nextSocket.send(JSON.stringify({ ticket }))
      connectionState.value = 'connected'
      void loadSummary()
    }
    nextSocket.onmessage = (message) => {
      if (revision !== selectionRevision) return
      try {
        const value: unknown = JSON.parse(String(message.data))
        if (aiotEnabled) {
          const event = parseAiotEvent(value, currentDevice, summary.value?.environment.id)
          if (event === null || recentEvents.has(event.event_id)) return
          if (event.type === 'prediction' && summary.value?.reading) {
            const reading = summary.value.reading
            if (event.device_record_id !== reading.device_record_id || event.data.equipment_id !== reading.equipment_id ||
              (!predictionMatchesReading(event, reading) && Date.parse(event.data.input_received_at) <= Date.parse(reading.received_at))) return
          }
          recentEvents.add(event.event_id)
          // shortcut: bounded live dedup; REST recovers authoritative state after reconnect.
          if (recentEvents.size > 256) recentEvents.delete(recentEvents.values().next().value!)
          onEvent?.(event)
        } else {
          if (!isMonitoringEvent(value, currentDevice)) return
          onEvent?.(value)
        }
        void loadSummary()
      } catch {
        // A malformed event cannot replace the last REST-verified state.
      }
    }
    nextSocket.onclose = (event) => {
      if (revision !== selectionRevision || disposed) return
      socket = null
      connectionState.value = event.code === 4401 ? 'unauthorized' : event.code === 4403 ? 'forbidden' : 'offline'
      if (event.code === 4401) {
        if (sessionToken.value === currentToken) clearSession()
        token.value = null
      } else if (event.code !== 4403) reconnectTimer = setTimeout(() => { void connect(revision) }, 2000)
    }
    nextSocket.onerror = () => nextSocket.close()
  }

  onMounted(() => {
    clockTimer = setInterval(() => { clock.value = Math.max(clock.value, Date.now()) }, 1000)
    watch([token, deviceId], () => {
      selectionRevision += 1
      latestSummaryRequest += 1
      recentEvents.clear()
      disconnect()
      summary.value = null
      summaryState.value = { phase: 'loading' }
      connectionState.value = 'offline'
      if (token.value && deviceId.value) {
        void loadSummary()
        void connect(selectionRevision)
      }
    }, { immediate: true })
  })

  onUnmounted(() => {
    disposed = true
    selectionRevision += 1
    if (clockTimer !== null) clearInterval(clockTimer)
    disconnect()
  })

  return { loadSummary, monitoringState, refreshRevision, summary, connectionState, ageSeconds }
}
