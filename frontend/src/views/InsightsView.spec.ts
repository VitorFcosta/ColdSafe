// @vitest-environment happy-dom
import examplePayloads from '../../../contracts/examples/aiot.valid.json'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { listDevices, listEnvironments } from '../features/account/catalog'
import { logout, refreshSessionIdentity, sessionRole, sessionToken } from '../features/account/session'
import { fetchInsights, InsightsAccessError, savePredictiveRules, type InsightsSnapshot } from '../features/insights/insights-api'
import InsightsView from './InsightsView.vue'

vi.mock('../features/account/catalog', () => ({ listDevices: vi.fn(), listEnvironments: vi.fn() }))
vi.mock('../features/account/session', async (original) => ({ ...await original<typeof import('../features/account/session')>(), logout: vi.fn(), refreshSessionIdentity: vi.fn() }))
vi.mock('../features/insights/insights-api', async (original) => ({ ...await original<typeof import('../features/insights/insights-api')>(), fetchInsights: vi.fn(), savePredictiveRules: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
const examples = examplePayloads as unknown as { name: string; payload: InsightsSnapshot['prediction'] }[]
const prediction = examples.find((item) => item.name === 'prediction_available_zero_rul')!.payload!
const rules = { health_critical: 30, health_recovery: 40, rul_critical_hours: 24, rul_recovery_hours: 48, open_count: 3, close_count: 10 }
const device = { id: prediction.device_record_id, environment_id: prediction.environment_id, mqtt_device_id: prediction.device_id, name: 'Motor autorizado', is_active: true }
const otherDevice = { ...device, id: '00000000-0000-4000-8000-000000000999', mqtt_device_id: 'other-device', name: 'Outro motor' }
const snapshot: InsightsSnapshot = { device_id: device.mqtt_device_id, equipment_id: prediction.data.equipment_id, rules, prediction, availability: 'available', age_seconds: 0, trend: 'declining', active_alerts: [] }
const alert = { alert_id: '00000000-0000-4000-8000-000000000999', kind: 'predictive_failure' as const, opened_at: prediction.received_at, source_event_id: prediction.data.source_event_id, prediction_event_id: prediction.event_id }
const mount = () => shallowMount(InsightsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(prediction.data.input_received_at))
  vi.mocked(listEnvironments).mockReset().mockResolvedValue([{ id: device.environment_id, name: 'Meu ambiente' }])
  vi.mocked(listDevices).mockReset().mockResolvedValue([device, otherDevice])
  vi.mocked(fetchInsights).mockReset().mockResolvedValue(structuredClone(snapshot))
  vi.mocked(savePredictiveRules).mockReset().mockResolvedValue({ ...rules })
  vi.mocked(logout).mockReset().mockImplementation(async () => { sessionToken.value = null })
  vi.mocked(refreshSessionIdentity).mockReset().mockImplementation(async () => { sessionRole.value = 'viewer' })
  sessionToken.value = 'token-A'
  sessionRole.value = 'operator'
})
afterEach(() => vi.useRealTimers())

describe('InsightsView', () => {
  it('exibe equipamento autorizado, zero real, tendência, versão e idade', async () => {
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Insights')
    expect(wrapper.get('h1').attributes('tabindex')).toBe('-1')
    expect(wrapper.get('[aria-label="Insights do equipamento"]').text()).toContain('0 h')
    expect(wrapper.text()).toContain('Em queda')
    expect(wrapper.text()).toContain('fan-model-1')
    expect(wrapper.text()).toContain('há 0 s')
    expect(wrapper.text()).toContain('não calibrados')
    expect(fetchInsights).toHaveBeenCalledWith('token-A', device, expect.any(AbortSignal))
    wrapper.unmount()
  })
  it.each(['viewer', null] as const)('papel %s lê regras mas não pode editá-las', async (role) => {
    sessionRole.value = role
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.text()).toContain('Somente operadores e administradores')
    expect(wrapper.text()).toContain('3 previsões críticas')
    wrapper.unmount()
  })
  it.each(['operator', 'admin'] as const)('papel %s salva regras completas e confirma resultado', async (role) => {
    sessionRole.value = role
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('input[name="open_count"]').setValue(4)
    vi.mocked(savePredictiveRules).mockResolvedValueOnce({ ...rules, open_count: 4 })
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(savePredictiveRules).toHaveBeenCalledWith('token-A', device, { ...rules, open_count: 4 }, expect.any(AbortSignal))
    expect(wrapper.text()).toContain('Regras salvas')
    wrapper.unmount()
  })
  it('não envia regras inválidas nem apaga edição durante polling', async () => {
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('input[name="health_critical"]').setValue(50)
    await vi.advanceTimersByTimeAsync(2000)
    expect((wrapper.get('input[name="health_critical"]').element as HTMLInputElement).value).toBe('50')
    await wrapper.get('form').trigger('submit')
    expect(savePredictiveRules).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Regras inválidas')
    wrapper.unmount()
  })
  it('erro de rede mantém alerta persistente, oculta métricas e não anuncia recuperação', async () => {
    vi.mocked(fetchInsights).mockResolvedValueOnce({ ...snapshot, active_alerts: [alert] })
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchInsights).mockRejectedValue(new Error('secret diagnostic'))
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.text()).toContain('Alerta preditivo persistente')
    expect(wrapper.text()).toContain('Não foi possível atualizar')
    expect(wrapper.text()).not.toContain('secret diagnostic')
    expect(wrapper.get('[aria-label="Insights do equipamento"]').text()).not.toContain('0 h')
    expect(wrapper.text()).not.toContain('Nenhum alerta preditivo ativo')
    wrapper.unmount()
  })
  it('ausência de previsão não é recuperação nem limpa alerta', async () => {
    vi.mocked(fetchInsights).mockResolvedValueOnce({ ...snapshot, prediction: null, availability: 'no_data', age_seconds: null, trend: 'unknown', active_alerts: [alert] })
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).toContain('Sem previsão')
    expect(wrapper.text()).toContain('não significa recuperação')
    expect(wrapper.text()).toContain('Alerta preditivo persistente')
    wrapper.unmount()
  })
  it('idade local vence previsão durante consulta pendente e cancela ao desmontar', async () => {
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchInsights).mockImplementationOnce(() => new Promise(() => {}))
    await vi.advanceTimersByTimeAsync(31000)
    expect(fetchInsights).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Previsão desatualizada')
    expect(wrapper.text()).toContain('há 31 s')
    expect(wrapper.get('[aria-label="Insights do equipamento"]').text()).not.toContain('0 h')
    const signal = vi.mocked(fetchInsights).mock.calls[1]![2]!
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
  })
  it.each(['account', 'device', 'logout'] as const)('descarta dados e resposta atrasada após trocar %s', async (change) => {
    let resolve!: (value: InsightsSnapshot) => void
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchInsights).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.mocked(fetchInsights).mockResolvedValue({ ...snapshot, prediction: null, availability: 'no_data', age_seconds: null, trend: 'unknown' })
    if (change === 'account') sessionToken.value = 'token-B'
    if (change === 'device') await wrapper.get('select[name="device"]').setValue(otherDevice.id)
    if (change === 'logout') sessionToken.value = null
    await flushPromises()
    resolve({ ...snapshot, active_alerts: [alert] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('fan-model-1')
    expect(wrapper.text()).not.toContain('Alerta preditivo persistente')
    wrapper.unmount()
  })
  it.each([401, 403, 404])('revogação HTTP %s remove valores e alertas privados', async (status) => {
    const wrapper = mount()
    await flushPromises()
    vi.mocked(fetchInsights).mockRejectedValueOnce(new InsightsAccessError(status))
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.text()).not.toContain('fan-model-1')
    expect(wrapper.text()).not.toContain('Nenhum alerta preditivo ativo')
    if (status === 401) expect(sessionToken.value).toBeNull()
    else expect(wrapper.text()).toContain('Acesso ao equipamento indisponível')
    wrapper.unmount()
  })
  it('resposta 401 atrasada não encerra outra sessão', async () => {
    let reject!: (error: Error) => void
    vi.mocked(fetchInsights).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    const wrapper = mount()
    await flushPromises()
    sessionToken.value = 'token-B'
    await flushPromises()
    reject(new InsightsAccessError(401))
    await flushPromises()
    expect(sessionToken.value).toBe('token-B')
    wrapper.unmount()
  })
  it('catálogo vazio ou falho tem estado explícito, sem consultar dispositivo inventado', async () => {
    vi.mocked(listEnvironments).mockResolvedValueOnce([])
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).toContain('Nenhum ambiente autorizado')
    expect(fetchInsights).not.toHaveBeenCalled()
    wrapper.unmount()
    vi.mocked(listEnvironments).mockRejectedValueOnce(new Error('secret'))
    const failed = mount()
    await flushPromises()
    expect(failed.text()).toContain('Não foi possível carregar o catálogo')
    failed.unmount()
  })
  it('não consulta sem sessão', async () => {
    sessionToken.value = null
    const wrapper = mount()
    await flushPromises()
    expect(listEnvironments).not.toHaveBeenCalled()
    expect(fetchInsights).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('previsão indisponível informa motivo e nunca mostra ausência de alertas como recuperação', async () => {
    const unavailable = examples.find((item) => item.name === 'prediction_unavailable_no_model')!.payload!
    vi.mocked(fetchInsights).mockResolvedValueOnce({ ...snapshot, prediction: unavailable, availability: 'unavailable', trend: 'unknown' })
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).toContain('Previsão indisponível')
    expect(wrapper.text()).toContain('Nenhum modelo ativo')
    expect(wrapper.text()).not.toContain('Nenhum alerta preditivo ativo')
    wrapper.unmount()
  })
  it.each(['no_data', 'stale'] as const)('mostra idade da entrada sem envelope de previsão: %s', async (availability) => {
    vi.mocked(fetchInsights).mockResolvedValueOnce({ ...snapshot, prediction: null, availability, age_seconds: availability === 'stale' ? 31 : 4, trend: 'unknown' })
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).toContain('Idade da entrada')
    expect(wrapper.text()).toContain(availability === 'stale' ? 'há 31 s' : 'há 4 s')
    expect(wrapper.text()).not.toContain('Nenhum alerta preditivo ativo')
    wrapper.unmount()
  })
  it('erro inicial não inventa previsão nem alertas vazios e polling recupera', async () => {
    vi.mocked(fetchInsights).mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).toContain('Não foi possível atualizar')
    expect(wrapper.text()).not.toContain('Nenhum alerta preditivo ativo')
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.text()).toContain('Previsão disponível')
    expect(wrapper.text()).toContain('Nenhum alerta preditivo ativo')
    wrapper.unmount()
  })
  it('timeout cancela consulta e polling retoma sem sobreposição', async () => {
    vi.mocked(fetchInsights).mockImplementationOnce((_token, _device, signal) => new Promise((_, reject) => {
      signal!.addEventListener('abort', () => reject(new Error('timeout')))
    }))
    const wrapper = mount()
    await vi.advanceTimersByTimeAsync(8000)
    expect(fetchInsights).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Não foi possível atualizar')
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetchInsights).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Previsão disponível')
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchInsights).toHaveBeenCalledTimes(2)
  })
  it('trocar ambiente remove os valores antigos e filtra dispositivos de outro ambiente/inativos', async () => {
    const envB = '00000000-0000-4000-8000-000000000998'
    vi.mocked(listEnvironments).mockResolvedValue([{ id: device.environment_id, name: 'A' }, { id: envB, name: 'B' }])
    const wrapper = mount()
    await flushPromises()
    vi.mocked(listDevices).mockResolvedValueOnce([device, { ...otherDevice, environment_id: envB, is_active: false }])
    await wrapper.get('select[name="environment"]').setValue(envB)
    await flushPromises()
    expect(wrapper.text()).not.toContain('fan-model-1')
    expect(wrapper.text()).toContain('Nenhum equipamento ativo')
    wrapper.unmount()
  })
  it('ignora catálogo antigo após mudar conta e após desmontar', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof listDevices>>) => void
    vi.mocked(listDevices).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const wrapper = mount()
    await flushPromises()
    vi.mocked(listEnvironments).mockResolvedValueOnce([])
    sessionToken.value = 'token-B'
    await flushPromises()
    resolve([device])
    await flushPromises()
    expect(fetchInsights).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('Motor autorizado')
    wrapper.unmount()
    let finish!: (value: Awaited<ReturnType<typeof listEnvironments>>) => void
    vi.mocked(listEnvironments).mockImplementationOnce(() => new Promise((done) => { finish = done }))
    const leaving = mount()
    leaving.unmount()
    finish([{ id: device.environment_id, name: 'Private' }])
    await flushPromises()
    expect(listDevices).toHaveBeenCalledOnce()
  })
  it('falha na lista de dispositivos fica explícita', async () => {
    vi.mocked(listDevices).mockRejectedValueOnce(new Error('private'))
    const wrapper = mount()
    await flushPromises()
    expect(wrapper.text()).toContain('Não foi possível carregar o catálogo')
    expect(fetchInsights).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it.each([new Error('private'), new InsightsAccessError(403)])('falha ao salvar mantém erro explícito sem revelar diagnóstico', async (error) => {
    vi.mocked(savePredictiveRules).mockRejectedValueOnce(error)
    vi.mocked(refreshSessionIdentity).mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).not.toContain('private')
    expect(wrapper.text()).toContain(error instanceof InsightsAccessError ? 'Acesso ao equipamento indisponível' : 'Não foi possível salvar')
    wrapper.unmount()
  })
  it('salvamento atrasado não altera conta nova nem encerra sessão após desmontar', async () => {
    let reject!: (error: Error) => void
    vi.mocked(savePredictiveRules).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    const signal = vi.mocked(savePredictiveRules).mock.calls[0]![3]!
    sessionToken.value = 'token-B'
    await flushPromises()
    expect(signal.aborted).toBe(true)
    reject(new InsightsAccessError(401))
    await flushPromises()
    expect(sessionToken.value).toBe('token-B')
    vi.mocked(savePredictiveRules).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    await wrapper.get('form').trigger('submit')
    wrapper.unmount()
    reject(new InsightsAccessError(401))
    await flushPromises()
    expect(sessionToken.value).toBe('token-B')
  })
  it('sucesso atrasado não confirma salvamento para equipamento diferente', async () => {
    let resolve!: (value: typeof rules) => void
    vi.mocked(savePredictiveRules).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await wrapper.get('select[name="device"]').setValue(otherDevice.id)
    await flushPromises()
    resolve({ ...rules, open_count: 5 })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Regras salvas')
    wrapper.unmount()
  })
  it('sair explica falha e pode ser repetido', async () => {
    vi.mocked(logout).mockRejectedValueOnce(new Error('private'))
    const wrapper = mount()
    await flushPromises()
    await wrapper.get('header button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Não foi possível encerrar a sessão')
    await wrapper.get('header button').trigger('click')
    await flushPromises()
    expect(sessionToken.value).toBeNull()
    expect(wrapper.text()).not.toContain('fan-model-1')
    wrapper.unmount()
  })
})
