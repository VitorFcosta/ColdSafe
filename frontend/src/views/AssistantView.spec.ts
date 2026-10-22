// @vitest-environment happy-dom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionToken } from '../features/account/session'
import { askAssistant, AssistantRequestError, fetchLlmStatus } from '../features/assistant/assistant-api'
import AssistantView from './AssistantView.vue'

const routing = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: routing.replace }) }))
vi.mock('../features/assistant/assistant-api', async (original) => ({
  ...await original<typeof import('../features/assistant/assistant-api')>(),
  askAssistant: vi.fn(), fetchLlmStatus: vi.fn(),
}))
let wrapper: VueWrapper | undefined
const render = () => mount(AssistantView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
beforeEach(() => {
  vi.useFakeTimers(); routing.replace.mockReset(); sessionToken.value = 'first-account'
  vi.mocked(fetchLlmStatus).mockReset().mockResolvedValue('ready')
  vi.mocked(askAssistant).mockReset().mockImplementation(async (_token, _question, onDelta) => {
    onDelta('Saúde 20 e RUL 10 h.'); return 'request-one'
  })
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })
const send = async (text = 'Qual a saúde?') => {
  await wrapper!.get('textarea').setValue(text)
  await wrapper!.get('form').trigger('submit')
  await flushPromises()
}

describe('Assistente privado', () => {
  it('explica o escopo da conta e prepara seis perguntas sem enviar automaticamente', async () => {
    wrapper = render(); await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Assistente')
    expect(wrapper.text()).toContain('sua conta')
    expect(wrapper.text()).toContain('Cada pergunta é independente')
    expect(wrapper.findAll('[data-testid="suggestion"]')).toHaveLength(6)
    await wrapper.findAll('[data-testid="suggestion"]')[0]!.trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('estado')
    expect(askAssistant).not.toHaveBeenCalled()
  })

  it.each([
    ['loading', 'Preparando o modelo local'], ['paused', 'pausado'],
    ['disabled', 'não está habilitado'], ['model_missing', 'ainda não foi preparado'],
    ['unavailable', 'indisponível'],
  ] as const)('explica %s e impede envio enquanto não estiver pronto', async (state, text) => {
    vi.mocked(fetchLlmStatus).mockResolvedValue(state)
    wrapper = render(); await flushPromises(); await send()
    expect(wrapper.text()).toContain(text)
    expect(askAssistant).not.toHaveBeenCalled()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  })

  it('mostra deltas como texto sem executar HTML ou criar imagens e só conclui no terminal', async () => {
    let complete!: (id: string) => void
    vi.mocked(askAssistant).mockImplementationOnce((_token, _question, delta) => {
      delta('<img src="https://remote.invalid/pixel" onerror="alert(1)"><script>bad()</script>')
      return new Promise((resolve) => { complete = resolve })
    })
    wrapper = render(); await flushPromises(); await send()
    expect(wrapper.text()).toContain('Resposta em andamento')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.get('[data-testid="answer"]').text()).toContain('<img')
    expect(wrapper.text()).not.toContain('Resposta concluída')
    const requests = vi.mocked(fetchLlmStatus).mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(fetchLlmStatus).toHaveBeenCalledTimes(requests)
    complete('request-html'); await flushPromises()
    expect(wrapper.text()).toContain('Resposta concluída')
    expect(wrapper.get('[data-testid="answer"]').attributes('aria-live')).toBeUndefined()
  })

  it('recusa vazio e limite em bytes UTF-8 e aceita o limite ASCII', async () => {
    wrapper = render(); await flushPromises()
    await send('   '); await send('🧊'.repeat(65))
    expect(askAssistant).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('256 bytes')
    await send('x'.repeat(256))
    expect(askAssistant).toHaveBeenCalledWith('first-account', 'x'.repeat(256), expect.any(Function), expect.any(AbortSignal))
  })

  it('marca interrupção como incompleta, preserva o parcial e não repete o POST', async () => {
    vi.mocked(askAssistant).mockImplementationOnce(async (_token, _question, delta) => {
      delta('Parte recebida.'); throw new AssistantRequestError('STREAM_INTERRUPTED')
    })
    wrapper = render(); await flushPromises(); await send()
    expect(wrapper.text()).toContain('Parte recebida.')
    expect(wrapper.text()).toContain('Resposta incompleta')
    expect(wrapper.text()).not.toContain('Resposta concluída')
    await vi.advanceTimersByTimeAsync(10000)
    expect(askAssistant).toHaveBeenCalledOnce()
  })

  it('cancela o pedido, mantém parcial identificado e ignora conclusão atrasada', async () => {
    let complete!: (id: string) => void
    let delta!: (text: string) => void
    vi.mocked(askAssistant).mockImplementationOnce((_token, _question, next) => {
      delta = next; next('Parte inicial.'); return new Promise((resolve) => { complete = resolve })
    })
    wrapper = render(); await flushPromises(); await send()
    const signal = vi.mocked(askAssistant).mock.calls[0]![3]!
    await wrapper.get('[data-testid="cancel"]').trigger('click')
    expect(signal.aborted).toBe(true)
    expect(wrapper.text()).toContain('Resposta incompleta')
    delta('Texto tardio'); complete('late'); await flushPromises()
    expect(wrapper.text()).not.toContain('Texto tardio')
    expect(wrapper.text()).not.toContain('Resposta concluída')
  })

  it('apaga conversa na troca de conta e não deixa erro 401 antigo apagar a nova sessão', async () => {
    let fail!: (reason: Error) => void
    let delta!: (text: string) => void
    vi.mocked(askAssistant).mockImplementationOnce((_token, _question, next) => {
      delta = next; next('Dado privado da primeira conta.'); return new Promise((_resolve, reject) => { fail = reject })
    })
    wrapper = render(); await flushPromises(); await send('Pergunta privada')
    sessionToken.value = 'second-account'; await flushPromises()
    delta('Vazamento tardio'); fail(new AssistantRequestError('UNAUTHORIZED', 401)); await flushPromises()
    expect(sessionToken.value).toBe('second-account')
    expect(wrapper.text()).not.toContain('Dado privado')
    expect(wrapper.text()).not.toContain('Pergunta privada')
    expect(wrapper.text()).not.toContain('Vazamento tardio')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
  })

  it('apaga o conteúdo e exige novo login após revogação atual', async () => {
    vi.mocked(askAssistant).mockRejectedValueOnce(new AssistantRequestError('UNAUTHORIZED', 401))
    wrapper = render(); await flushPromises(); await send('Não guardar esta pergunta')
    expect(sessionToken.value).toBeNull()
    expect(wrapper.text()).not.toContain('Não guardar esta pergunta')
    expect(routing.replace).toHaveBeenCalledWith('/login')
  })

  it('respeita Retry-After sem reenvio automático e permite novo envio ao terminar', async () => {
    vi.mocked(askAssistant).mockRejectedValueOnce(new AssistantRequestError('RATE_LIMITED', 429, 3))
    wrapper = render(); await flushPromises(); await send()
    expect(wrapper.text()).toContain('Limite de perguntas')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(3000); await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(askAssistant).toHaveBeenCalledOnce()
  })

  it('recusa 403 de geração até trocar a sessão e apaga o texto privado', async () => {
    vi.mocked(askAssistant).mockRejectedValueOnce(new AssistantRequestError('FORBIDDEN', 403))
    wrapper = render(); await flushPromises(); await send('Pergunta privada')
    expect(wrapper.text()).toContain('Seu acesso ao assistente não está autorizado')
    expect(wrapper.text()).not.toContain('Pergunta privada')
    const polls = vi.mocked(fetchLlmStatus).mock.calls.length
    await vi.advanceTimersByTimeAsync(10000); await send('Não enviar')
    expect(askAssistant).toHaveBeenCalledOnce()
    expect(fetchLlmStatus).toHaveBeenCalledTimes(polls)
    sessionToken.value = 'second-account'; await flushPromises(); await send('Nova conta')
    expect(askAssistant).toHaveBeenCalledTimes(2)
  })

  it('403 no status encerra polling e 401 limpa somente a sessão atual', async () => {
    vi.mocked(fetchLlmStatus).mockRejectedValueOnce(new AssistantRequestError('FORBIDDEN', 403))
    wrapper = render(); await flushPromises()
    expect(wrapper.text()).toContain('Seu acesso ao assistente não está autorizado')
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchLlmStatus).toHaveBeenCalledOnce()
    vi.mocked(fetchLlmStatus).mockRejectedValueOnce(new AssistantRequestError('UNAUTHORIZED', 401))
    sessionToken.value = 'revoked-account'; await flushPromises()
    expect(sessionToken.value).toBeNull()
    expect(routing.replace).toHaveBeenCalledWith('/login')
  })

  it('consulta antiga não cancela o timeout da nova consulta após cancelar geração', async () => {
    let oldFinish!: (state: 'ready') => void
    wrapper = render(); await flushPromises()
    vi.mocked(fetchLlmStatus).mockImplementationOnce(() => new Promise((resolve) => { oldFinish = resolve }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.mocked(askAssistant).mockImplementationOnce(() => new Promise(() => {}))
    await send()
    vi.mocked(fetchLlmStatus).mockImplementationOnce(() => new Promise(() => {}))
    await wrapper.get('[data-testid="cancel"]').trigger('click'); await flushPromises()
    const newSignal = vi.mocked(fetchLlmStatus).mock.calls.at(-1)![1]!
    oldFinish('ready'); await flushPromises()
    expect(newSignal.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(4000)
    expect(newSignal.aborted).toBe(true)
  })

  it('explica prazo de resposta excedido sem marcar o parcial como concluído', async () => {
    vi.mocked(askAssistant).mockRejectedValueOnce(new AssistantRequestError('LLM_TIMEOUT'))
    wrapper = render(); await flushPromises(); await send()
    expect(wrapper.text()).toContain('excedeu o tempo de resposta')
    expect(wrapper.text()).toContain('Resposta incompleta')
    expect(wrapper.text()).not.toContain('Resposta concluída')
  })

  it('recupera status após falha de consulta sem repetir perguntas', async () => {
    vi.mocked(fetchLlmStatus).mockRejectedValueOnce(new TypeError('offline'))
    wrapper = render(); await flushPromises()
    expect(wrapper.text()).toContain('indisponível')
    await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local pronto')
    expect(askAssistant).not.toHaveBeenCalled()
  })

  it('descarta status antigo e aborta timers e stream ao desmontar', async () => {
    let finish!: (state: 'paused') => void
    vi.mocked(fetchLlmStatus).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    wrapper = render()
    const oldSignal = vi.mocked(fetchLlmStatus).mock.calls[0]![1]!
    sessionToken.value = 'second-account'; await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    finish('paused'); await flushPromises()
    expect(wrapper.text()).toContain('Modelo local pronto')
    vi.mocked(askAssistant).mockImplementationOnce(() => new Promise(() => {}))
    await send()
    const signal = vi.mocked(askAssistant).mock.calls[0]![3]!
    wrapper.unmount(); wrapper = undefined
    expect(signal.aborted).toBe(true)
    const calls = vi.mocked(fetchLlmStatus).mock.calls.length
    await vi.advanceTimersByTimeAsync(20000)
    expect(fetchLlmStatus).toHaveBeenCalledTimes(calls)
  })
})
