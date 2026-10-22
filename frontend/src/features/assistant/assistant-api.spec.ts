import { afterEach, describe, expect, it, vi } from 'vitest'
import { askAssistant, AssistantRequestError, fetchLlmStatus } from './assistant-api'

const id = '9b2157af-cb36-4cb5-810d-d534dbf82988'
const event = (kind: string, data: object) => `event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`
const bytes = new TextEncoder()
const response = (body: string, status = 200, headers: Record<string, string> = {}) => new Response(body, {
  status, headers: { 'content-type': 'text/event-stream', ...headers },
})
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('cliente do Assistente', () => {
  it('entrega partes antes do terminal e envia somente a pergunta com Bearer', async () => {
    let write!: ReadableStreamDefaultController<Uint8Array>
    const cancel = vi.fn()
    const body = new ReadableStream<Uint8Array>({ start(controller) { write = controller }, cancel })
    const request = vi.fn().mockResolvedValue(new Response(body, { headers: { 'content-type': 'text/event-stream' } }))
    vi.stubGlobal('fetch', request)
    const delta = vi.fn()
    const result = askAssistant('private', 'Como está?', delta, new AbortController().signal)
    write.enqueue(bytes.encode(event('delta', { text: 'Saúde 20' })))
    await vi.waitFor(() => expect(delta).toHaveBeenCalledWith('Saúde 20'))
    expect(request).toHaveBeenCalledWith(expect.stringContaining('/api/v3/llm/ask'), expect.objectContaining({
      method: 'POST', cache: 'no-store', body: JSON.stringify({ question: 'Como está?' }),
      headers: { authorization: 'Bearer private', 'content-type': 'application/json', accept: 'text/event-stream' },
    }))
    write.enqueue(bytes.encode(event('done', { request_id: id })))
    expect(await result).toBe(id)
    expect(cancel).toHaveBeenCalledOnce()
  })

  it('preserva UTF-8 e CRLF fragmentados e trata HTML/Markdown como dados', async () => {
    const text = '<img src="https://remote.invalid/x" onerror="alert(1)"> **Saúde**: ação 🧊'
    const wire = bytes.encode((event('delta', { text }) + event('done', { request_id: id })).replaceAll('\n', '\r\n'))
    const body = new ReadableStream<Uint8Array>({ start(controller) {
      for (const byte of wire) controller.enqueue(Uint8Array.of(byte))
      controller.close()
    } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { headers: { 'content-type': 'text/event-stream' } })))
    const delta = vi.fn()
    await askAssistant('token', 'estado', delta)
    expect(delta).toHaveBeenCalledExactlyOnceWith(text)
  })

  it.each([
    '', event('delta', { text: 'parcial' }), 'event: delta\ndata: {bad}\n\n',
    event('done', { request_id: id }), event('delta', { text: '' }) + event('done', { request_id: id }),
    event('delta', { text: 3 }), event('tool', { text: 'run' }), event('done', { request_id: 'bad' }),
    event('delta', { text: 'x'.repeat(16385) }), 'x'.repeat(20000),
  ])('recusa stream inválido/interrompido sem inventar sucesso', async (wire) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(wire)))
    await expect(askAssistant('t', 'estado', vi.fn())).rejects.toBeInstanceOf(AssistantRequestError)
  })

  it.each(['LLM_TIMEOUT', 'LLM_UNAVAILABLE', 'UNAUTHORIZED'])('preserva falha SSE %s após texto parcial', async (code) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(event('delta', { text: 'parcial' }) + event('error', { code }))))
    const delta = vi.fn()
    await expect(askAssistant('t', 'estado', delta)).rejects.toMatchObject({ code })
    expect(delta).toHaveBeenCalledWith('parcial')
  })

  it.each([401, 403, 429, 503])('classifica erro HTTP %s sem confiar em mensagem remota', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(JSON.stringify({ error: {
      code: status === 429 ? 'RATE_LIMITED' : 'LLM_BUSY', message: '<script>private</script>',
    } }), status, { 'retry-after': '60' })))
    const failure = await askAssistant('t', 'estado', vi.fn()).catch((e: AssistantRequestError) => e)
    expect(failure).toBeInstanceOf(AssistantRequestError)
    expect((failure as AssistantRequestError).status).toBe(status)
    expect((failure as Error).message).not.toContain('private')
    if (status === 429) expect((failure as AssistantRequestError).retryAfterSeconds).toBe(60)
  })

  it.each(['', ' ', 'x'.repeat(257), '🧊'.repeat(65)])('recusa pergunta inválida antes do HTTP', async (question) => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
    await expect(askAssistant('t', question, vi.fn())).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('cancela o reader quando o chamador aborta', async () => {
    const cancel = vi.fn()
    const stream = new ReadableStream<Uint8Array>({ cancel })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { headers: { 'content-type': 'text/event-stream' } })))
    const controller = new AbortController()
    const pending = askAssistant('t', 'estado', vi.fn(), controller.signal)
    await Promise.resolve(); await Promise.resolve()
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(cancel).toHaveBeenCalledOnce()
  })

  it('limita a espera total e fecha um stream sem novas partes', async () => {
    vi.useFakeTimers()
    const cancel = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({ cancel }), {
      headers: { 'content-type': 'text/event-stream' },
    })))
    const pending = askAssistant('t', 'estado', vi.fn()).catch((error: unknown) => error)
    await vi.advanceTimersByTimeAsync(100_000)
    expect(await pending).toMatchObject({ code: 'LLM_TIMEOUT' })
    expect(cancel).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('recusa resposta 200 sem SSE e limite total de bytes', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response('{}', 200, { 'content-type': 'application/json' }))
      .mockResolvedValueOnce(response(':' + 'x'.repeat(65536)))
    vi.stubGlobal('fetch', fetcher)
    await expect(askAssistant('t', 'estado', vi.fn())).rejects.toMatchObject({ code: 'STREAM_INVALID' })
    await expect(askAssistant('t', 'estado', vi.fn())).rejects.toMatchObject({ code: 'STREAM_INVALID' })
  })

  it('não envia pergunta que já foi cancelada', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
    const controller = new AbortController(); controller.abort()
    await expect(askAssistant('t', 'estado', vi.fn(), controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetcher).not.toHaveBeenCalled()
  })

  it.each(['loading', 'ready', 'paused', 'disabled', 'model_missing', 'unavailable'])('valida estado %s', async (state) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true,
      data: { state, model: 'local' }, meta: { schema_version: 3 } }))))
    expect(await fetchLlmStatus('t')).toBe(state)
  })

  it('recusa envelope de estado desconhecido', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true,
      data: { state: 'invented', model: 'local' }, meta: { schema_version: 3 } }))))
    await expect(fetchLlmStatus('t')).rejects.toBeInstanceOf(AssistantRequestError)
  })
})
