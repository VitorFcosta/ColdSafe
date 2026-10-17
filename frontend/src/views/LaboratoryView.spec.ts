// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { sessionToken, sessionRole, refreshSessionIdentity } from '../features/account/session'
import { createGeneration, defaultGeneration, fetchJob, fetchDataset, fetchSample, LaboratoryAccessError, LaboratoryRequestError, type GenerationJob, type Dataset } from '../features/laboratory/laboratory-api'
import LaboratoryView from './LaboratoryView.vue'

vi.mock('../features/account/session', async (original) => ({ ...await original<typeof import('../features/account/session')>(), refreshSessionIdentity: vi.fn() }))
vi.mock('../features/laboratory/laboratory-api', async (original) => ({ ...await original<typeof import('../features/laboratory/laboratory-api')>(), createGeneration: vi.fn(), fetchJob: vi.fn(), fetchDataset: vi.fn(), fetchSample: vi.fn() }))
const routing = vi.hoisted(() => ({ replace: vi.fn(), route: { query: {} as Record<string, string> } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: routing.replace }), useRoute: () => routing.route }))
const id = '0d4f2e34-f5c7-4125-8fb0-800b0ebdcf6c'
const owner = '0d4f2e34-f5c7-4125-8fb0-800b0ebdcf6d'
const job: GenerationJob = { id, owner_user_id: owner, job_type: 'generation', status: 'queued', completed_units: 0,
  total_units: 1000000, config: defaultGeneration(), result_id: null, dataset_id: null, error_code: null,
  environment_id: null, created_at: '2026-10-17T12:00:00Z', updated_at: '2026-10-17T12:00:00Z' }
const dataset: Dataset = { id, generation_job_id: id, owner_user_id: owner, created_at: job.created_at,
  row_count: 1000000, config: { ...defaultGeneration(), sensor_types: ['humidity_percent'] }, storage_version: 'offline-numpy-v1',
  units: { humidity_percent: '%' }, quality: { missing_by_sensor: { humidity_percent: 10000 },
    range_by_sensor: { humidity_percent: { min: 20, max: 95 } }, rul_observed_rows: 600000, rul_censored_rows: 400000 } }
const render = () => mount(LaboratoryView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
beforeEach(() => {
  vi.useFakeTimers(); routing.route = reactive({ query: {} }); routing.replace.mockReset().mockImplementation(async (location) => {
    if (typeof location === 'object') routing.route.query = location.query
  })
  sessionToken.value = 'admin-token'; sessionRole.value = 'admin'
  vi.mocked(createGeneration).mockReset().mockResolvedValue(job)
  vi.mocked(fetchJob).mockReset().mockResolvedValue(job)
  vi.mocked(fetchDataset).mockReset().mockResolvedValue(dataset)
  vi.mocked(fetchSample).mockReset().mockResolvedValue({ dataset_id: id, rows: [] })
  vi.mocked(refreshSessionIdentity).mockReset().mockImplementation(async () => { sessionRole.value = 'viewer' })
})
afterEach(() => vi.useRealTimers())

describe('Laboratório privado', () => {
  it('explica volume antes da execução e envia todos parâmetros', async () => {
    const wrapper = render()
    expect(wrapper.get('h1').text()).toBe('Laboratório de Dados')
    expect(wrapper.text()).toContain('1.000.000 linhas')
    expect(wrapper.text()).toContain('600 sensores')
    expect(wrapper.text()).toContain('85 MB')
    await wrapper.get('input[name="seed"]').setValue(123)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(createGeneration).toHaveBeenCalledWith('admin-token', { ...defaultGeneration(), seed: 123 }, expect.any(AbortSignal))
    expect(routing.route.query.job).toBe(id)
    expect(wrapper.text()).toContain('Na fila')
    wrapper.unmount()
  })
  it('recusa inválidos e teto excedido antes da API', async () => {
    const wrapper = render()
    await wrapper.get('input[name="total_units"]').setValue(2000001)
    await wrapper.get('form').trigger('submit')
    expect(createGeneration).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Revise os parâmetros')
    wrapper.unmount()
  })
  it('recarrega acompanhamento sem POST e só carrega amostra após clique', async () => {
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 1000000, result_id: id })
    const wrapper = render(); await flushPromises()
    expect(createGeneration).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Concluído')
    expect(wrapper.text()).toContain(owner)
    expect(wrapper.text()).toContain('600.000')
    expect(wrapper.text()).toContain('400.000')
    expect(wrapper.text()).toContain('Seed: 42')
    expect(fetchSample).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="sample-button"]').trigger('click'); await flushPromises()
    expect(fetchSample).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('não representativa')
    wrapper.unmount()
  })
  it('não permite gerar na recarga enquanto o estado do job é desconhecido', async () => {
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockImplementationOnce(() => new Promise(() => {}))
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(createGeneration).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('recusa 422 permite corrigir parâmetros sem tratar a recusa como envio incerto', async () => {
    vi.mocked(createGeneration).mockRejectedValueOnce(new LaboratoryRequestError(422))
    const wrapper = render()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('API recusou os parâmetros')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('100% de unidades em execução não exibe dataset concluído; falha parcial é explícita', async () => {
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockResolvedValueOnce({ ...job, status: 'running', completed_units: 1000000 })
    const wrapper = render(); await flushPromises()
    expect(wrapper.text()).toContain('Em execução')
    expect(fetchDataset).not.toHaveBeenCalled()
    vi.mocked(fetchJob).mockResolvedValueOnce({ ...job, status: 'failed', completed_units: 500000, error_code: 'GENERATION_FAILED' })
    await vi.advanceTimersByTimeAsync(1500)
    expect(wrapper.text()).toContain('Falhou')
    expect(wrapper.text()).toContain('GENERATION_FAILED')
    expect(wrapper.text()).toContain('parciais')
    expect(fetchDataset).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it.each(['viewer', 'operator', null] as const)('não executa nem consulta com papel %s', async (role) => {
    sessionRole.value = role; routing.route.query = { job: id }
    const wrapper = render(); await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(fetchJob).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('limpa dados e cancela consulta ao trocar sessão, ignora resposta tardia', async () => {
    routing.route.query = { job: id }
    let finish!: (value: GenerationJob) => void
    vi.mocked(fetchJob).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = render(); await flushPromises()
    const signal = vi.mocked(fetchJob).mock.calls[0]![2]!
    sessionRole.value = 'viewer'; await flushPromises()
    expect(signal.aborted).toBe(true)
    finish(job); await flushPromises()
    expect(wrapper.text()).not.toContain(owner)
    wrapper.unmount()
  })
  it('não sobrepõe consultas manuais, cancela em 8s e não repete após desmontar', async () => {
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockRejectedValueOnce(new Error('offline'))
    const wrapper = render(); await flushPromises()
    let finish!: (value: GenerationJob) => void
    vi.mocked(fetchJob).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const retry = wrapper.findAll('button').find((button) => button.text() === 'Atualizar acompanhamento')!
    await retry.trigger('click'); await retry.trigger('click')
    expect(fetchJob).toHaveBeenCalledTimes(2)
    wrapper.unmount(); finish(job); await flushPromises()
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchJob).toHaveBeenCalledTimes(2)
  })
  it.each([401, 403] as const)('oculta dados na revogação %s', async (status) => {
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockRejectedValueOnce(new LaboratoryAccessError(status))
    const wrapper = render(); await flushPromises()
    expect(wrapper.text()).not.toContain(owner)
    if (status === 401) expect(sessionToken.value).toBeNull()
    else expect(refreshSessionIdentity).toHaveBeenCalled()
    wrapper.unmount()
  })
  it('permite repetir GET com falha e nunca repete POST automaticamente', async () => {
    vi.mocked(createGeneration).mockRejectedValueOnce(new Error('private traceback'))
    const wrapper = render()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('não envie novamente')
    expect(wrapper.text()).not.toContain('traceback')
    await vi.advanceTimersByTimeAsync(10000)
    expect(createGeneration).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
})
