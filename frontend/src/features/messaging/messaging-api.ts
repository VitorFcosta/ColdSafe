import { isRecord, isUtcTime } from '../monitoring/aiot-api'

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
