import { isDeviceId, isRecord, isUtcTime, isUuid } from '../monitoring/aiot-api'

export type QueueMetrics = Readonly<{
  name: string
  messages: number
  messages_ready: number
  messages_unacknowledged: number
  consumers: number
  publish_rate: number | null
  deliver_rate: number | null
}>
export type MessagingSnapshot = Readonly<{ sampled_at: string; queues: readonly QueueMetrics[] }>
export class MessagingAccessError extends Error {
  constructor(readonly status: 401 | 403) { super('Não foi possível consultar a mensageria.') }
}
const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const counter = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
const rate = (value: unknown): value is number | null => value === null ||
  (typeof value === 'number' && Number.isFinite(value) && value >= 0)
function isQueue(value: unknown): value is QueueMetrics {
  return isRecord(value) && typeof value.name === 'string' && value.name.length > 0 && value.name.length <= 255 &&
    counter(value.messages) && counter(value.messages_ready) && counter(value.messages_unacknowledged) &&
    counter(value.consumers) && rate(value.publish_rate) && rate(value.deliver_rate)
}

export async function fetchMessaging(token: string, signal?: AbortSignal): Promise<MessagingSnapshot> {
  const response = await fetch(`${baseUrl}/api/v3/messaging`, {
    signal, headers: { accept: 'application/json', authorization: `Bearer ${token}` },
  })
  if (response.status === 401 || response.status === 403) throw new MessagingAccessError(response.status)
  if (!response.ok) throw new Error('Não foi possível consultar a mensageria.')
  const body: unknown = await response.json()
  if (!isRecord(body) || body.success !== true || !isRecord(body.data) ||
    !isUtcTime(body.data.sampled_at) || !Array.isArray(body.data.queues) || !body.data.queues.every(isQueue) ||
    new Set(body.data.queues.map((queue) => queue.name)).size !== body.data.queues.length) {
    throw new Error('Resposta inválida da API de mensageria.')
  }
  return { sampled_at: body.data.sampled_at, queues: body.data.queues }
}

export type MessageSample = Readonly<{
  event_id: string
  type: string
  occurred_at: string
  observed_at: string
  device_record_id: string
  device_id: string
  environment_id: string
  correlation_id: string
  source_queue: string | null
  reason: string | null
  error_code: string | null
}>
export type MessageSamplesSnapshot = Readonly<{
  sampled_at: string
  connected: boolean
  last_observed_at: string | null
  stale: boolean
  stale_after_seconds: 30
  capacity_per_kind: 100
  messages: readonly MessageSample[]
  dead_letters: readonly MessageSample[]
}>
const metadata = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 255
const optionalMetadata = (value: unknown): value is string | null => value === null || metadata(value)
function isMessageSample(value: unknown): value is MessageSample {
  return isRecord(value) && isUuid(value.event_id) && metadata(value.type) && isUtcTime(value.occurred_at) &&
    isUtcTime(value.observed_at) && isUuid(value.device_record_id) && isDeviceId(value.device_id) &&
    isUuid(value.environment_id) && isUuid(value.correlation_id) && optionalMetadata(value.source_queue) &&
    optionalMetadata(value.reason) && optionalMetadata(value.error_code)
}
function isSampleList(value: unknown): value is MessageSample[] {
  return Array.isArray(value) && value.length <= 100 && value.every(isMessageSample) &&
    new Set(value.map((sample) => `${sample.event_id}:${sample.source_queue}`)).size === value.length
}
export async function fetchMessageSamples(token: string, signal?: AbortSignal): Promise<MessageSamplesSnapshot> {
  const response = await fetch(`${baseUrl}/api/v3/messaging/messages`, {
    signal, headers: { accept: 'application/json', authorization: `Bearer ${token}` },
  })
  if (response.status === 401 || response.status === 403) throw new MessagingAccessError(response.status)
  if (!response.ok) throw new Error('Não foi possível consultar as mensagens.')
  const body: unknown = await response.json()
  if (!isRecord(body) || body.success !== true || !isRecord(body.data) ||
    !isUtcTime(body.data.sampled_at) || typeof body.data.connected !== 'boolean' || typeof body.data.stale !== 'boolean' ||
    !(body.data.last_observed_at === null || isUtcTime(body.data.last_observed_at)) ||
    body.data.stale_after_seconds !== 30 || body.data.capacity_per_kind !== 100 ||
    !isSampleList(body.data.messages) || !isSampleList(body.data.dead_letters)) {
    throw new Error('Resposta inválida da API de mensagens.')
  }
  return { sampled_at: body.data.sampled_at, connected: body.data.connected, last_observed_at: body.data.last_observed_at,
    stale: body.data.stale, stale_after_seconds: body.data.stale_after_seconds, capacity_per_kind: body.data.capacity_per_kind,
    messages: body.data.messages, dead_letters: body.data.dead_letters }
}
