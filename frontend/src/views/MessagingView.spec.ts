// @vitest-environment happy-dom
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { logout, refreshSessionIdentity, sessionRole, sessionToken } from '../features/account/session'
import { fetchMessaging, fetchMessageSamples, MessagingAccessError, type MessagingSnapshot, type MessageSamplesSnapshot } from '../features/messaging/messaging-api'
import MessagingView from './MessagingView.vue'

vi.mock('../features/account/session', async (importOriginal) => ({
  ...await importOriginal<typeof import('../features/account/session')>(), refreshSessionIdentity: vi.fn(), logout: vi.fn(),
}))
vi.mock('../features/messaging/messaging-api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../features/messaging/messaging-api')>(), fetchMessaging: vi.fn(), fetchMessageSamples: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
const snapshot: MessagingSnapshot = { sampled_at: '2026-10-15T12:00:00Z', queues: [
  { name: 'telemetry.api.q', messages: 3, messages_ready: 2, messages_unacknowledged: 1,
    consumers: 1, publish_rate: null, deliver_rate: 0 },
] }
const samples: MessageSamplesSnapshot = { sampled_at: snapshot.sampled_at, connected: true,
  last_observed_at: snapshot.sampled_at, stale: false, stale_after_seconds: 30, capacity_per_kind: 100,
  messages: [{ event_id: 'event-safe', type: 'telemetry', occurred_at: snapshot.sampled_at,
    observed_at: snapshot.sampled_at, device_record_id: 'device-record', device_id: 'cold-01',
    environment_id: 'environment-safe', correlation_id: 'correlation-safe', source_queue: null, reason: null, error_code: null }],
  dead_letters: [{ event_id: 'dead-safe', type: 'telemetry', occurred_at: snapshot.sampled_at,
    observed_at: snapshot.sampled_at, device_record_id: 'device-record', device_id: 'cold-01',
    environment_id: 'environment-safe', correlation_id: 'correlation-safe', source_queue: 'coldsafe.writer',
    reason: 'rejected', error_code: 'INVALID_SCHEMA' }],
}
const mount = () => shallowMount(MessagingView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(snapshot.sampled_at))
  vi.mocked(fetchMessaging).mockReset().mockResolvedValue(snapshot)
  vi.mocked(fetchMessageSamples).mockReset().mockResolvedValue(samples)
  vi.mocked(logout).mockImplementation(async () => { sessionToken.value = null; sessionRole.value = null })
  vi.mocked(refreshSessionIdentity).mockImplementation(async () => { sessionRole.value = 'viewer' })
  sessionToken.value = 'admin-token'
  sessionRole.value = 'admin'
})
afterEach(() => vi.useRealTimers())

describe('MessagingView', () => {
  it('mostra contagens, zero real e taxa desconhecida sem confundi-los', async () => {
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Mensageria')
    expect(wrapper.get('h1').attributes('tabindex')).toBe('-1')
    expect(wrapper.get('tbody').text()).toContain('telemetry.api.q')
    expect(wrapper.get('tbody').text()).toContain('Indisponível')
    expect(wrapper.get('tbody').text()).toContain('0 /s')
    expect(wrapper.text()).toContain('há 0 s')
    expect(wrapper.text()).toContain('infraestrutura compartilhada')
    wrapper.unmount()
  })
  it.each(['viewer', 'operator', null] as const)('não consulta nem exibe métricas com papel %s', async (role) => {
    sessionRole.value = role
    const wrapper = mount()
    await flushPromises()
    expect(fetchMessaging).not.toHaveBeenCalled()
    expect(fetchMessageSamples).not.toHaveBeenCalled()
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).toContain('administradores')
    wrapper.unmount()
  })
  it('atualiza a cada 5s, mantém a amostra com falha explícita e permite recuperação', async () => {
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchMessaging).mockRejectedValueOnce(new Error('broker credential must never be shown'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchMessaging).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role="alert"]').text()).toContain('Não foi possível atualizar')
    expect(wrapper.text()).not.toContain('credential')
    expect(wrapper.get('tbody').text()).toContain('telemetry.api.q')
    expect(wrapper.text()).toContain('há 5 s')
    expect(wrapper.text()).toContain('Última consulta bem-sucedida')
    vi.mocked(fetchMessaging).mockResolvedValue({ ...snapshot, sampled_at: new Date().toISOString() })
    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchMessaging).toHaveBeenCalledTimes(3)
  })
  it('a idade continua aumentando durante consulta pendente e sinaliza desatualização', async () => {
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchMessaging).mockImplementationOnce(() => new Promise(() => {}))
    await vi.advanceTimersByTimeAsync(17000)
    expect(fetchMessaging).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('há 17 s')
    expect(wrapper.text()).toContain('Informação desatualizada')
    wrapper.unmount()
  })
  it('não sobrepõe consultas e cancela pedido ao sair da página', async () => {
    vi.mocked(fetchMessaging).mockImplementationOnce(() => new Promise(() => {}))
    const wrapper = mount()
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchMessaging).toHaveBeenCalledOnce()
    const signal = vi.mocked(fetchMessaging).mock.calls[0]![1]!
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchMessaging).toHaveBeenCalledOnce()
  })
  it.each(['logout', 'role', 'new-token'] as const)('apaga dados privados e ignora resposta anterior após %s', async (change) => {
    let finish!: (value: MessagingSnapshot) => void
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchMessaging).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    await vi.advanceTimersByTimeAsync(5000)
    if (change === 'logout') sessionToken.value = null
    if (change === 'role') sessionRole.value = 'viewer'
    if (change === 'new-token') {
      vi.mocked(fetchMessaging).mockResolvedValue({ ...snapshot, queues: [] })
      sessionToken.value = 'new-session'
    }
    await flushPromises()
    expect(wrapper.text()).not.toContain('telemetry.api.q')
    finish(snapshot)
    await flushPromises()
    expect(wrapper.text()).not.toContain('telemetry.api.q')
    wrapper.unmount()
  })
  it('retira a amostra quando a API revoga o acesso mesmo com papel local antigo', async () => {
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchMessaging).mockRejectedValueOnce(new MessagingAccessError(403))
    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('apenas para administradores')
    expect(sessionRole.value).toBe('viewer')
    wrapper.unmount()
  })
  it('encerra sessão quando a API responde 401', async () => {
    vi.mocked(fetchMessaging).mockRejectedValueOnce(new MessagingAccessError(401))
    const wrapper = mount()
    await flushPromises()
    expect(sessionToken.value).toBeNull()
    expect(wrapper.find('table').exists()).toBe(false)
    wrapper.unmount()
  })
  it('uma revogação atrasada da sessão antiga não encerra a nova sessão', async () => {
    let reject!: (error: Error) => void
    vi.mocked(fetchMessaging).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    const wrapper = mount()
    vi.mocked(fetchMessaging).mockResolvedValue({ ...snapshot, queues: [] })
    sessionToken.value = 'new-session'
    await flushPromises()
    reject(new MessagingAccessError(401))
    await flushPromises()
    expect(sessionToken.value).toBe('new-session')
    expect(sessionRole.value).toBe('admin')
    expect(wrapper.text()).toContain('Nenhuma fila disponível')
    wrapper.unmount()
  })
  it('sair encerra a sessão e remove os dados administrativos', async () => {
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('button.sign-out').trigger('click')
    await flushPromises()
    expect(logout).toHaveBeenCalled()
    expect(sessionToken.value).toBeNull()
    expect(wrapper.find('table').exists()).toBe(false)
    wrapper.unmount()
  })
  it('sair com falha mantém a sessão e explica como repetir', async () => {
    vi.mocked(logout).mockRejectedValueOnce(new Error('private diagnostic'))
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('button.sign-out').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Não foi possível encerrar a sessão')
    expect(wrapper.text()).not.toContain('private diagnostic')
    expect(sessionToken.value).toBe('admin-token')
    wrapper.unmount()
  })
  it('uma consulta que excede 8s é cancelada e o polling consegue recuperar', async () => {
    vi.mocked(fetchMessaging).mockImplementationOnce((_token, signal) => new Promise((_, reject) => {
      signal!.addEventListener('abort', () => reject(new Error('timeout')))
    }))
    const wrapper = mount()
    await vi.advanceTimersByTimeAsync(8000)
    expect(fetchMessaging).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="alert"]').text()).toContain('Nenhuma amostra disponível')
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetchMessaging).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('tbody').text()).toContain('telemetry.api.q')
    wrapper.unmount()
  })
  it('se a revalidação de permissões falha, as métricas permanecem ocultas', async () => {
    vi.mocked(refreshSessionIdentity).mockImplementationOnce(async () => {
      sessionRole.value = null
      throw new Error('offline')
    })
    vi.mocked(fetchMessaging).mockRejectedValueOnce(new MessagingAccessError(403))
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.find('table').exists()).toBe(false)
    expect(sessionRole.value).toBeNull()
    wrapper.unmount()
  })
  it('mostra indisponibilidade inicial sem inventar filas vazias', async () => {
    vi.mocked(fetchMessaging).mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Não foi possível atualizar')
    expect(wrapper.find('table').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('amostras privadas de mensagens', () => {
  it('mostra últimas mensagens, origem e motivo da DLQ sem controle Docker', async () => {
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.get('[aria-labelledby="messages-title"]').text()).toContain('event-safe')
    expect(wrapper.get('[aria-labelledby="dead-letters-title"]').text()).toContain('coldsafe.writer')
    expect(wrapper.text()).toContain('INVALID_SCHEMA')
    expect(wrapper.text()).toContain('rejected')
    expect(wrapper.text()).toContain('seus ambientes')
    expect(wrapper.text()).toContain('terminal')
    expect(wrapper.get('[aria-labelledby="writer-title"]').text()).toContain('coldsafe.writer')
    expect(wrapper.findAll('button')).toHaveLength(1)
    wrapper.unmount()
  })
  it('distingue vazio de falha, desconexão e amostra desatualizada', async () => {
    vi.mocked(fetchMessageSamples).mockResolvedValueOnce({ ...samples, messages: [], dead_letters: [],
      last_observed_at: null, stale: true, connected: false })
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).toContain('Nenhuma mensagem observada')
    expect(wrapper.text()).toContain('Nenhuma mensagem morta observada')
    expect(wrapper.text()).toContain('Observador desconectado')
    expect(wrapper.text()).toContain('Observação desatualizada')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('falha das amostras conserva métricas e última amostra com aviso, e recupera', async () => {
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchMessageSamples).mockRejectedValueOnce(new Error('private diagnostic'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.text()).toContain('Não foi possível atualizar as mensagens')
    expect(wrapper.text()).toContain('event-safe')
    expect(wrapper.text()).toContain('telemetry.api.q')
    expect(wrapper.text()).not.toContain('private diagnostic')
    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('idade local sinaliza observação antiga mesmo quando a próxima consulta falha', async () => {
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchMessageSamples).mockRejectedValue(new Error('offline'))
    await vi.advanceTimersByTimeAsync(31000)
    expect(wrapper.text()).toContain('Observação desatualizada')
    wrapper.unmount()
  })
  it.each(['logout', 'role', 'new-token'] as const)('remove amostras e ignora resposta tardia após %s', async (change) => {
    let finish!: (value: MessageSamplesSnapshot) => void
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchMessageSamples).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    await vi.advanceTimersByTimeAsync(5000)
    if (change === 'logout') sessionToken.value = null
    if (change === 'role') sessionRole.value = 'viewer'
    if (change === 'new-token') {
      vi.mocked(fetchMessageSamples).mockResolvedValue({ ...samples, messages: [], dead_letters: [] })
      sessionToken.value = 'new-session'
    }
    await flushPromises()
    expect(wrapper.text()).not.toContain('event-safe')
    expect(wrapper.text()).not.toContain('dead-safe')
    finish(samples)
    await flushPromises()
    expect(wrapper.text()).not.toContain('event-safe')
    expect(wrapper.text()).not.toContain('dead-safe')
    wrapper.unmount()
  })
  it('revogação do endpoint de mensagens oculta também métricas', async () => {
    vi.mocked(fetchMessageSamples).mockRejectedValueOnce(new MessagingAccessError(403))
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).not.toContain('event-safe')
    expect(wrapper.text()).not.toContain('telemetry.api.q')
    expect(sessionRole.value).toBe('viewer')
    wrapper.unmount()
  })
})
