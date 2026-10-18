// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import TrainingView from './TrainingView.vue'
import { sessionRole, sessionToken } from '../features/account/session'
import { fetchDataset, defaultGeneration } from '../features/laboratory/laboratory-api'
import { createTraining, fetchDatasets, fetchTrainingJob, fetchTrainingResult, TrainingRequestError, TrainingAccessError, type TrainingJob, type TrainingResult } from '../features/training/training-api'
import fixture from '../features/training/training.fixture.json'
vi.mock('../features/laboratory/laboratory-api', async (original) => ({ ...await original<typeof import('../features/laboratory/laboratory-api')>(), fetchDataset: vi.fn() }))
vi.mock('../features/training/training-api', async (original) => ({ ...await original<typeof import('../features/training/training-api')>(), fetchDatasets: vi.fn(), createTraining: vi.fn(), fetchTrainingJob: vi.fn(), fetchTrainingResult: vi.fn() }))
const routing = vi.hoisted(() => ({ replace: vi.fn(), route: { query: {} as Record<string, string> } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: routing.replace }), useRoute: () => routing.route }))
const job: TrainingJob = { id: fixture.job_id, owner_user_id: fixture.job_id, job_type: 'training', status: 'queued', completed_units: 0, total_units: 2, result_id: null, dataset_id: fixture.dataset_id, environment_id: null, error_code: null, config: { job_type: 'training', dataset_id: fixture.dataset_id, environment_id: null }, created_at: '2026-10-17T12:00:00Z', updated_at: '2026-10-17T12:00:00Z' }
const summary = { id: fixture.dataset_id, generation_job_id: fixture.job_id, owner_user_id: fixture.job_id, row_count: 1000000, created_at: job.created_at, config: defaultGeneration(), storage_version: 'offline-numpy-v1' as const, units: {}, quality: { missing_by_sensor: {}, range_by_sensor: {}, rul_observed_rows: 600000, rul_censored_rows: 400000 } }
const render = () => mount(TrainingView, { global: { stubs: { TrainingTarget: { template: '<div>Resultados de regressão</div>' }, RouterLink: { template: '<a><slot /></a>' } } } })
beforeEach(() => {
  vi.useFakeTimers(); routing.route = reactive({ query: {} }); routing.replace.mockReset().mockImplementation(async (location) => { if (typeof location === 'object') routing.route.query = location.query })
  sessionToken.value = 'admin-token'; sessionRole.value = 'admin'
  vi.mocked(fetchDataset).mockReset().mockResolvedValue(summary)
  vi.mocked(fetchDatasets).mockReset().mockResolvedValue([{ id: fixture.dataset_id, name: 'Dataset 1', row_count: 1000000, created_at: job.created_at, generation_job_id: fixture.job_id }])
  vi.mocked(createTraining).mockReset().mockResolvedValue(job); vi.mocked(fetchTrainingJob).mockReset().mockResolvedValue(job)
  vi.mocked(fetchTrainingResult).mockReset().mockResolvedValue(fixture as TrainingResult)
})
afterEach(() => vi.useRealTimers())
describe('treinamento privado', () => {
  it('preseleciona dataset do laboratório, confirma resumo antes do POST e não duplica', async () => {
    routing.route.query = { dataset: fixture.dataset_id }
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('select').element.value).toBe(fixture.dataset_id)
    expect(wrapper.text()).toContain('400.000'); expect(wrapper.text()).toContain('Seed do treino: 42')
    await wrapper.get('form').trigger('submit'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(createTraining).toHaveBeenCalledOnce(); expect(fetchDataset).toHaveBeenCalledTimes(3)
    expect(routing.route.query.job).toBe(fixture.job_id); wrapper.unmount()
  })
  it('retoma job concluído sem POST e diferencia concluído de apto', async () => {
    routing.route.query = { job: fixture.job_id }; vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id })
    const wrapper = render(); await flushPromises()
    expect(createTraining).not.toHaveBeenCalled(); expect(fetchTrainingResult).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Concluído'); expect(wrapper.text()).toContain('Pacote rejeitado')
    expect(wrapper.text()).toContain('offline-42'); expect(wrapper.text()).toContain('Dados sintéticos')
    wrapper.unmount()
  })
  it.each(['viewer', 'operator', null] as const)('bloqueia papel %s sem consultar dados', async (role) => {
    sessionRole.value = role; const wrapper = render(); await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false); expect(fetchDatasets).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('administradores'); wrapper.unmount()
  })
  it('não repete POST incerto e mantém botão bloqueado', async () => {
    routing.route.query = { dataset: fixture.dataset_id }; vi.mocked(createTraining).mockRejectedValue(new Error('offline'))
    const wrapper = render(); await flushPromises(); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('não envie novamente'); await vi.advanceTimersByTimeAsync(10000)
    expect(createTraining).toHaveBeenCalledOnce(); expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined(); wrapper.unmount()
  })
  it('falha 422 permite corrigir e resultado indisponível preserva job', async () => {
    routing.route.query = { dataset: fixture.dataset_id }; vi.mocked(createTraining).mockRejectedValue(new TrainingRequestError(422))
    const wrapper = render(); await flushPromises(); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('recusou'); expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined(); wrapper.unmount()
  })
  it('cancela e ignora resposta tardia ao trocar sessão', async () => {
    let finish!: (value: TrainingJob) => void; routing.route.query = { job: fixture.job_id }
    vi.mocked(fetchTrainingJob).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = render(); await flushPromises(); const signal = vi.mocked(fetchTrainingJob).mock.calls[0]![2]!
    sessionToken.value = null; await flushPromises(); expect(signal.aborted).toBe(true); finish(job); await flushPromises()
    expect(wrapper.text()).not.toContain(fixture.job_id); expect(routing.replace).toHaveBeenCalledWith('/login'); wrapper.unmount()
  })
  it('aceita subset de sensores e bloqueia menos de três equipamentos', async () => {
    routing.route.query = { dataset: fixture.dataset_id }
    vi.mocked(fetchDataset).mockResolvedValue({ ...summary, config: { ...defaultGeneration(), sensor_types: ['humidity_percent'] } })
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    vi.mocked(fetchDataset).mockResolvedValue({ ...summary, config: { ...defaultGeneration(), equipment_count: 2 } })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(createTraining).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('ao menos três equipamentos')
    wrapper.unmount()
  })
  it('faz polling sequencial e permite repetir resultado indisponível sem novo POST', async () => {
    routing.route.query = { job: fixture.job_id }
    const wrapper = render(); await flushPromises()
    expect(wrapper.text()).toContain('Na fila')
    vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id })
    vi.mocked(fetchTrainingResult).mockRejectedValueOnce(new TrainingRequestError(503))
    await vi.advanceTimersByTimeAsync(1500); await flushPromises()
    expect(wrapper.text()).toContain('resultado está indisponível')
    await wrapper.findAll('button').find((b) => b.text() === 'Atualizar acompanhamento')!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Pacote rejeitado'); expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount(); const calls = vi.mocked(fetchTrainingJob).mock.calls.length
    await vi.advanceTimersByTimeAsync(10000); expect(fetchTrainingJob).toHaveBeenCalledTimes(calls)
  })
  it('oculta dados na revogação e rejeita URL inválida', async () => {
    routing.route.query = { job: 'bad' }; const invalid = render(); await flushPromises()
    expect(invalid.text()).toContain('inválido na URL'); expect(fetchTrainingJob).not.toHaveBeenCalled(); invalid.unmount()
    routing.route.query = { job: fixture.job_id }; vi.mocked(fetchTrainingJob).mockRejectedValueOnce(new TrainingAccessError(401))
    const wrapper = render(); await flushPromises(); expect(sessionToken.value).toBeNull(); expect(wrapper.text()).not.toContain(fixture.job_id); wrapper.unmount()
  })
  it('erro antes do POST não gera envio incerto', async () => {
    routing.route.query = { dataset: fixture.dataset_id }
    const wrapper = render(); await flushPromises()
    vi.mocked(fetchDataset).mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('Nenhum treinamento foi enviado'); expect(createTraining).not.toHaveBeenCalled()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined(); wrapper.unmount()
  })

  it('repete resumo do mesmo dataset quando a consulta inicial falha', async () => {
    routing.route.query = { dataset: fixture.dataset_id }
    vi.mocked(fetchDataset).mockRejectedValueOnce(new Error('offline'))
    const wrapper = render(); await flushPromises(); expect(wrapper.text()).toContain('consultar o dataset selecionado')
    await wrapper.findAll('button').find((b) => b.text() === 'Consultar datasets novamente')!.trigger('click'); await flushPromises()
    expect(fetchDataset).toHaveBeenCalledTimes(2)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined(); wrapper.unmount()
  })

})
