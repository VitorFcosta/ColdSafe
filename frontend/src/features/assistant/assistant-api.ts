import { isRecord, isUuid } from '../monitoring/aiot-api'

export type LlmState = 'disabled' | 'loading' | 'ready' | 'paused' | 'model_missing' | 'unavailable'
const states: LlmState[] = ['disabled', 'loading', 'ready', 'paused', 'model_missing', 'unavailable']
const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const messages: Record<string, string> = {
  UNAUTHORIZED: 'Sessão inválida. Entre novamente.',
  FORBIDDEN: 'Acesso ao assistente não autorizado.',
  RATE_LIMITED: 'Limite de perguntas atingido. Aguarde antes de enviar novamente.',
  LLM_DISABLED: 'O assistente local não está habilitado.',
  LLM_BUSY: 'O assistente está ocupado ou aguarda recuperação segura da memória.',
  LLM_NOT_READY: 'O modelo local ainda não está pronto. Aguarde o carregamento.',
  LLM_UNAVAILABLE: 'O assistente local está indisponível. Tente novamente quando o modelo estiver pronto.',
  LLM_TIMEOUT: 'O prazo da resposta terminou. A resposta parcial está incompleta.',
  VALIDATION_ERROR: 'Digite uma pergunta com até 256 bytes UTF-8.',
  STREAM_INVALID: 'A resposta foi interrompida ou recebida em formato inválido. O texto parcial está incompleto.',
}

export class AssistantRequestError extends Error {
  constructor(readonly code: string, readonly status?: number, readonly retryAfterSeconds?: number) {
    super(messages[code] ?? messages.LLM_UNAVAILABLE)
  }
}

async function checkResponse(response: Response): Promise<void> {
  if (response.ok) return
  const retry = Number(response.headers.get('retry-after'))
  let code = response.status === 401 ? 'UNAUTHORIZED' : response.status === 403 ? 'FORBIDDEN' :
    response.status === 429 ? 'RATE_LIMITED' : 'LLM_UNAVAILABLE'
  if (![401, 403, 429].includes(response.status)) {
    try {
      const body: unknown = await response.json()
      if (isRecord(body) && isRecord(body.error) && typeof body.error.code === 'string' &&
          Object.hasOwn(messages, body.error.code)) code = body.error.code
    } catch { /* Invalid error bodies retain the fixed local message. */ }
  }
  throw new AssistantRequestError(code, response.status,
    response.status === 429 ? (Number.isFinite(retry) && retry > 0 ? Math.min(3600, Math.ceil(retry)) : 60) : undefined)
}

export async function fetchLlmStatus(token: string, signal?: AbortSignal): Promise<LlmState> {
  const response = await fetch(`${baseUrl}/api/v3/llm/status`, {
    headers: { authorization: `Bearer ${token}` }, signal, cache: 'no-store',
  })
  await checkResponse(response)
  const body: unknown = await response.json()
  if (!isRecord(body) || body.success !== true || !isRecord(body.meta) || body.meta.schema_version !== 3 ||
      !isRecord(body.data) || typeof body.data.model !== 'string' || !states.includes(body.data.state as LlmState)) {
    throw new AssistantRequestError('LLM_UNAVAILABLE')
  }
  return body.data.state as LlmState
}

export async function askAssistant(token: string, question: string, onDelta: (text: string) => void,
  signal?: AbortSignal): Promise<string> {
  if (!question.trim() || new TextEncoder().encode(question).length > 256) throw new AssistantRequestError('VALIDATION_ERROR')
  const controller = new AbortController()
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  let cancelled = false
  let timedOut = false
  const cancelReader = () => {
    if (!reader || cancelled) return
    cancelled = true
    // Cancellation is cleanup; the abort/protocol error remains the caller's failure.
    void reader.cancel().catch(() => {})
  }
  const abort = () => { controller.abort(); cancelReader() }
  signal?.addEventListener('abort', abort, { once: true })
  const deadline = setTimeout(() => { timedOut = true; abort() }, 100_000)
  try {
    if (signal?.aborted) abort()
    if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError')
    const response = await fetch(`${baseUrl}/api/v3/llm/ask`, {
      method: 'POST', cache: 'no-store', signal: controller.signal,
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', accept: 'text/event-stream' },
      body: JSON.stringify({ question }),
    })
    await checkResponse(response)
    if (!response.body || response.headers.get('content-type')?.split(';')[0]?.trim() !== 'text/event-stream') {
      throw new AssistantRequestError('STREAM_INVALID')
    }
    reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8', { fatal: true })
    let pending = ''
    let received = 0
    let textBytes = 0
    while (true) {
      const { value, done } = await reader.read()
      if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError')
      if (done) { decoder.decode(); throw new AssistantRequestError('STREAM_INVALID') }
      received += value.byteLength
      if (received > 65_536) throw new AssistantRequestError('STREAM_INVALID')
      pending += decoder.decode(value, { stream: true })
      let boundary: RegExpExecArray | null
      while ((boundary = /\r?\n\r?\n/.exec(pending))) {
        const frame = pending.slice(0, boundary.index)
        pending = pending.slice(boundary.index + boundary[0].length)
        if (!frame.trim() || frame.startsWith(':')) continue
        const lines = frame.split(/\r?\n/)
        if (frame.length > 20_000 || lines.length !== 2 || !lines[0]?.startsWith('event: ') || !lines[1]?.startsWith('data: ')) {
          throw new AssistantRequestError('STREAM_INVALID')
        }
        const kind = lines[0].slice(7)
        const data: unknown = JSON.parse(lines[1].slice(6))
        if (!isRecord(data)) throw new AssistantRequestError('STREAM_INVALID')
        if (kind === 'done' && isUuid(data.request_id) && textBytes > 0) return data.request_id
        if (kind === 'error' && ['LLM_TIMEOUT', 'LLM_UNAVAILABLE', 'UNAUTHORIZED'].includes(String(data.code))) {
          throw new AssistantRequestError(String(data.code), data.code === 'UNAUTHORIZED' ? 401 : undefined)
        }
        if (kind !== 'delta' || typeof data.text !== 'string') throw new AssistantRequestError('STREAM_INVALID')
        textBytes += new TextEncoder().encode(data.text).length
        if (textBytes > 16_384) throw new AssistantRequestError('STREAM_INVALID')
        onDelta(data.text)
      }
      if (pending.length > 20_000) throw new AssistantRequestError('STREAM_INVALID')
    }
  } catch (error) {
    if (timedOut) throw new AssistantRequestError('LLM_TIMEOUT')
    if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError')
    if (error instanceof AssistantRequestError) throw error
    throw new AssistantRequestError('STREAM_INVALID')
  } finally {
    clearTimeout(deadline)
    signal?.removeEventListener('abort', abort)
    cancelReader()
    reader?.releaseLock()
  }
}
