// @vitest-environment happy-dom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionToken } from '../account/session'
import LlmStatus from './LlmStatus.vue'

const request = vi.fn<typeof fetch>()
const response = (state: string) => new Response(JSON.stringify({ success: true,
  data: { state, model: 'llama3.2:1b-instruct-q4_K_M' }, meta: { schema_version: 3 } }))
let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.useFakeTimers(); request.mockReset(); vi.stubGlobal('fetch', request)
  sessionToken.value = 'session-one'; request.mockResolvedValue(response('ready'))
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers(); vi.unstubAllGlobals() })

describe('estado do modelo local', () => {
  it.each([
    ['loading', 'Preparando o modelo local'], ['ready', 'Modelo local carregado'],
    ['paused', 'pausado durante geração ou treinamento'], ['unavailable', 'Modelo local indisponível'],
    ['model_missing', 'Modelo local ainda não preparado'],
  ])('explica %s sem oferecer conversa já implementada', async (state, message) => {
    request.mockResolvedValue(response(state)); wrapper = mount(LlmStatus); await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain(message)
    expect(wrapper.find('input').exists()).toBe(false)
    expect(request).toHaveBeenCalledWith(expect.stringContaining('/api/v3/llm/status'), expect.objectContaining({
      headers: { authorization: 'Bearer session-one' }, signal: expect.any(AbortSignal),
    }))
    if (state === 'paused') expect(wrapper.text()).toContain('recarregado automaticamente')
  })

  it('oculta o aviso sem overlay e consulta novamente para detectar ativação', async () => {
    request.mockResolvedValueOnce(response('disabled')); wrapper = mount(LlmStatus); await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    request.mockResolvedValue(response('ready')); await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local carregado')
  })

  it('recupera após erro e recusa envelope ou estado desconhecido', async () => {
    request.mockRejectedValueOnce(new TypeError('offline')); wrapper = mount(LlmStatus); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local indisponível')
    request.mockResolvedValueOnce(response('invented')); await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local indisponível')
    request.mockResolvedValueOnce(new Response(JSON.stringify({ data: { state: 'ready' } })))
    await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local indisponível')
    request.mockResolvedValue(response('ready')); await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local carregado')
  })

  it('não consulta sem sessão e interrompe após 401', async () => {
    sessionToken.value = null; wrapper = mount(LlmStatus); await flushPromises()
    expect(request).not.toHaveBeenCalled()
    request.mockResolvedValue(new Response(null, { status: 401 })); sessionToken.value = 'expired'
    await flushPromises(); expect(sessionToken.value).toBeNull()
    await vi.advanceTimersByTimeAsync(20000)
    expect(request).toHaveBeenCalledOnce(); expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('interrompe após 403 sem apagar uma sessão válida', async () => {
    request.mockResolvedValue(new Response(null, { status: 403 })); wrapper = mount(LlmStatus); await flushPromises()
    await vi.advanceTimersByTimeAsync(20000)
    expect(request).toHaveBeenCalledOnce(); expect(sessionToken.value).toBe('session-one')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('cancela consulta antiga na troca de sessão e descarta sua resposta atrasada', async () => {
    let finish!: (value: Response) => void
    request.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    wrapper = mount(LlmStatus); const firstSignal = request.mock.calls[0]![1]!.signal!
    sessionToken.value = 'session-two'; await flushPromises()
    expect(firstSignal.aborted).toBe(true); expect(wrapper.text()).toContain('Modelo local carregado')
    finish(response('paused')); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local carregado')
    expect(request.mock.calls[1]![1]!.headers).toEqual({ authorization: 'Bearer session-two' })
  })

  it('encerra polling e aborta a requisição ao desmontar', async () => {
    request.mockImplementationOnce(() => new Promise(() => {})); wrapper = mount(LlmStatus)
    const signal = request.mock.calls[0]![1]!.signal!
    wrapper.unmount(); wrapper = undefined
    expect(signal.aborted).toBe(true); await vi.advanceTimersByTimeAsync(20000)
    expect(request).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0)
  })

  it('limita espera, informa indisponibilidade e retoma após timeout', async () => {
    request.mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => {
      options!.signal!.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    }))
    wrapper = mount(LlmStatus); await vi.advanceTimersByTimeAsync(4000); await flushPromises()
    expect(request.mock.calls[0]![1]!.signal!.aborted).toBe(true)
    expect(wrapper.text()).toContain('Modelo local indisponível')
    request.mockResolvedValue(response('ready')); await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local carregado')
  })
})
