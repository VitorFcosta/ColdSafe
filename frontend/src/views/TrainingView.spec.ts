// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import TrainingView from './TrainingView.vue'
import { sessionRole, sessionToken } from '../features/account/session'
import { draftPrompt, requestDraftTransition, resolveDraftPrompt } from '../features/editing/draft-protection'
import { fetchDataset, defaultGeneration, LaboratoryAccessError } from '../features/laboratory/laboratory-api'
import { createTraining, fetchDatasets, fetchTrainingJob, fetchTrainingResult, TrainingRequestError, TrainingAccessError, type TrainingJob, type TrainingResult } from '../features/training/training-api'
import fixture from '../features/training/training.fixture.json'
vi.mock('../features/laboratory/laboratory-api', async (original) => ({ ...await original<typeof import('../features/laboratory/laboratory-api')>(), fetchDataset: vi.fn() }))
vi.mock('../features/training/training-api', async (original) => ({ ...await original<typeof import('../features/training/training-api')>(), fetchDatasets: vi.fn(), createTraining: vi.fn(), fetchTrainingJob: vi.fn(), fetchTrainingResult: vi.fn() }))
const known = vi.hoisted(() => ({ remember: vi.fn(), forget: vi.fn(), identity: vi.fn(), references: {} as { training?: { jobId: string; datasetId: string } } }))
vi.mock('../features/account/session', async (original) => ({ ...await original<typeof import('../features/account/session')>(), rememberKnownJob: known.remember, forgetKnownJob: known.forget, refreshSessionIdentity: known.identity, knownJobs: { get value() { return known.references } } }))
const routing = vi.hoisted(() => ({ replace: vi.fn(), route: { query: {} as Record<string, string> } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: routing.replace }), useRoute: () => routing.route }))
const job: TrainingJob = { id: fixture.job_id, owner_user_id: fixture.job_id, job_type: 'training', status: 'queued', completed_units: 0, total_units: 2, result_id: null, dataset_id: fixture.dataset_id, environment_id: null, error_code: null, config: { job_type: 'training', dataset_id: fixture.dataset_id, environment_id: null }, created_at: '2026-10-17T12:00:00Z', updated_at: '2026-10-17T12:00:00Z' }
const summary = { id: fixture.dataset_id, generation_job_id: fixture.job_id, owner_user_id: fixture.job_id, row_count: 1000000, created_at: job.created_at, config: defaultGeneration(), storage_version: 'offline-numpy-v1' as const, units: {}, quality: { missing_by_sensor: {}, range_by_sensor: {}, rul_observed_rows: 600000, rul_censored_rows: 400000 } }
const render = () => mount(TrainingView, { global: { stubs: { LlmStatus: true, JobResumeLinks: true, TrainingTarget: { template: '<div>Resultados de regressão</div>' }, RouterLink: { template: '<a><slot /></a>' } } } })
// Vue mantém refs de script setup internamente; não expor API de produção só para testes.
const selectionIsDirty = (wrapper: ReturnType<typeof render>) =>
  (wrapper.vm.$ as unknown as { setupState: { selectionDirty: boolean } }).setupState.selectionDirty
beforeEach(() => {
  known.references = {}; known.remember.mockReset(); known.forget.mockReset(); known.identity.mockReset().mockResolvedValue(undefined)
  vi.useFakeTimers(); routing.route = reactive({ query: {} }); routing.replace.mockReset().mockImplementation(async (location) => { if (typeof location === 'object') routing.route.query = location.query })
  sessionToken.value = 'admin-token'; sessionRole.value = 'admin'
  vi.mocked(fetchDataset).mockReset().mockResolvedValue(summary)
  vi.mocked(fetchDatasets).mockReset().mockResolvedValue([{ id: fixture.dataset_id, name: 'Dataset 1', row_count: 1000000, created_at: job.created_at, generation_job_id: fixture.job_id }])
  vi.mocked(createTraining).mockReset().mockResolvedValue(job); vi.mocked(fetchTrainingJob).mockReset().mockResolvedValue(job)
  vi.mocked(fetchTrainingResult).mockReset().mockResolvedValue(fixture as TrainingResult)
})
afterEach(() => vi.useRealTimers())
describe('treinamento privado', () => {
  it.each([false, true])('retry não contorna parâmetro dataset inválido, com job: %s', async (withJob) => {
    routing.route.query = withJob ? { job: job.id, dataset: 'invalid' } : { dataset: 'invalid' }
    const wrapper = render(); await flushPromises()
    const retry = wrapper.findAll('button').find((button) => button.text() === (withJob ? 'Atualizar acompanhamento' : 'Consultar datasets novamente'))!
    await retry.trigger('click'); await flushPromises()
    expect(fetchTrainingJob).not.toHaveBeenCalled()
    expect(fetchDatasets).not.toHaveBeenCalled()
    expect(fetchDataset).not.toHaveBeenCalled()
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('dataset 403 preserva job confirmado e retry recupera detalhes sem POST nem mudança de baseline', async () => {
    routing.route.query = { job: job.id, dataset: job.dataset_id }
    vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id })
    vi.mocked(fetchDataset).mockRejectedValueOnce(new LaboratoryAccessError(403))
    const wrapper = render(); await flushPromises()
    expect(wrapper.find('[aria-labelledby="training-job-title"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('dataset está indisponível')
    expect(known.forget).not.toHaveBeenCalled()
    expect(selectionIsDirty(wrapper)).toBe(false)
    const retry = wrapper.findAll('button').find((button) => button.text() === 'Atualizar acompanhamento')!
    await retry.trigger('click'); await flushPromises()
    expect(fetchDataset).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Seed da geração: 42')
    expect(selectionIsDirty(wrapper)).toBe(false)
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('retry do job não sobrescreve escolha manual diferente do dataset confirmado', async () => {
    const other = '00000000-0000-4000-8000-000000000123'
    routing.route.query = { job: job.id, dataset: job.dataset_id }
    vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id })
    vi.mocked(fetchDatasets).mockResolvedValue([
      { id: job.dataset_id, name: 'Inicial', row_count: 1000000, created_at: job.created_at, generation_job_id: fixture.job_id },
      { id: other, name: 'Outro', row_count: 1000000, created_at: job.created_at, generation_job_id: fixture.job_id },
    ])
    const wrapper = render(); await flushPromises()
    vi.mocked(fetchDataset).mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('select').setValue(other); await flushPromises()
    const retry = wrapper.findAll('button').find((button) => button.text() === 'Atualizar acompanhamento')!
    await retry.trigger('click'); await flushPromises()
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(other)
    expect(selectionIsDirty(wrapper)).toBe(true)
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('não associa dataset divergente antes da confirmação do job', async () => {
    const other = '00000000-0000-4000-8000-000000000123'
    routing.route.query = { job: job.id, dataset: other }
    const wrapper = render(); await flushPromises()
    expect(fetchDataset).not.toHaveBeenCalled()
    expect(fetchTrainingResult).not.toHaveBeenCalled()
    expect(known.remember).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-labelledby="training-job-title"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('indisponível')
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it.each([false, true])('relação divergente remove somente a referência coincidente com o par inválido: %s', async (tampered) => {
    const other = '00000000-0000-4000-8000-000000000123'
    known.references = { training: { jobId: job.id, datasetId: tampered ? other : job.dataset_id } }
    routing.route.query = { job: job.id, dataset: other }
    const wrapper = render(); await flushPromises()
    if (tampered) expect(known.forget).toHaveBeenCalledWith('admin-token', 'training', job.id)
    else expect(known.forget).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchTrainingJob).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
  it('listagem atrasada não desfaz dataset inferido pelo job confirmado', async () => {
    let finish!: (value: Awaited<ReturnType<typeof fetchDatasets>>) => void
    vi.mocked(fetchDatasets).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    routing.route.query = { job: job.id }
    const wrapper = render(); await flushPromises()
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(job.dataset_id)
    finish([]); await flushPromises()
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(job.dataset_id)
    expect(selectionIsDirty(wrapper)).toBe(false)
    wrapper.unmount()
  })
  it('resposta tardia de outro job não registra nem associa o par anterior', async () => {
    const nextId = '00000000-0000-4000-8000-000000000123'
    const nextDataset = '00000000-0000-4000-8000-000000000124'
    let finish!: (value: TrainingJob) => void
    vi.mocked(fetchTrainingJob).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    vi.mocked(fetchTrainingJob).mockResolvedValueOnce({ ...job, id: nextId, dataset_id: nextDataset, config: { ...job.config, dataset_id: nextDataset } })
    routing.route.query = { job: job.id }
    const wrapper = render(); await flushPromises()
    routing.route.query = { job: nextId }; await flushPromises()
    finish(job); await flushPromises()
    expect(known.remember).toHaveBeenCalledTimes(1)
    expect(known.remember).toHaveBeenCalledWith('admin-token', 'training', { jobId: nextId, datasetId: nextDataset })
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(nextDataset)
    wrapper.unmount()
  })
  it('resultado 403 preserva job confirmado, referência e recuperação GET na página autorizada', async () => {
    routing.route.query = { job: job.id, dataset: job.dataset_id }
    vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id })
    vi.mocked(fetchTrainingResult).mockRejectedValueOnce(new TrainingAccessError(403))
    const wrapper = render(); await flushPromises()
    expect(wrapper.find('[aria-labelledby="training-job-title"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('resultado está indisponível')
    expect(known.remember).toHaveBeenCalledWith('admin-token', 'training', { jobId: job.id, datasetId: job.dataset_id })
    expect(known.forget).not.toHaveBeenCalled(); expect(known.identity).not.toHaveBeenCalled()
    const retry = wrapper.findAll('button').find((button) => button.text() === 'Atualizar acompanhamento')!
    expect(retry).toBeDefined()
    await retry.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Pacote rejeitado')
    expect(fetchTrainingResult).toHaveBeenCalledTimes(2)
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('falha do resultado preserva referência do job confirmado para repetir somente GET', async () => {
    routing.route.query = { job: job.id, dataset: job.dataset_id }
    vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id })
    vi.mocked(fetchTrainingResult).mockRejectedValueOnce(new TrainingRequestError(404))
    const wrapper = render(); await flushPromises()
    expect(known.remember).toHaveBeenCalledWith('admin-token', 'training', { jobId: job.id, datasetId: job.dataset_id })
    expect(known.forget).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('resultado está indisponível')
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('job sozinho infere dataset pelo GET confirmado e registra referência sem alterar URL', async () => {
    routing.route.query = { job: job.id }
    const wrapper = render(); await flushPromises()
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(job.dataset_id)
    expect(fetchDataset).toHaveBeenCalledWith('admin-token', job.dataset_id, expect.any(AbortSignal))
    expect(known.remember).toHaveBeenCalledWith('admin-token', 'training', { jobId: job.id, datasetId: job.dataset_id })
    expect(routing.route.query).toEqual({ job: job.id })
    expect(routing.replace).not.toHaveBeenCalled()
    expect(selectionIsDirty(wrapper)).toBe(false)
    wrapper.unmount()
  })
  it.each([403, 404])('job definitivamente inacessível %s remove referência e cessa polling sem revalidar identidade em ciclo', async (status) => {
    routing.route.query = { job: job.id, dataset: job.dataset_id }
    vi.mocked(fetchTrainingJob).mockRejectedValueOnce(status === 403 ? new TrainingAccessError(403) : new TrainingRequestError(404))
    const wrapper = render(); await flushPromises()
    expect(known.forget).toHaveBeenCalledWith('admin-token', 'training', job.id)
    expect(known.identity).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('indisponível')
    expect(fetchDataset).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchTrainingJob).toHaveBeenCalledOnce()
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('erro temporário conserva referência e repete somente GET', async () => {
    routing.route.query = { job: job.id, dataset: job.dataset_id }
    vi.mocked(fetchTrainingJob).mockRejectedValueOnce(new TrainingRequestError(503))
    const wrapper = render(); await flushPromises()
    expect(known.forget).not.toHaveBeenCalled()
    expect(known.remember).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1500); await flushPromises()
    expect(known.remember).toHaveBeenCalledWith('admin-token', 'training', { jobId: job.id, datasetId: job.dataset_id })
    expect(createTraining).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('POST confirmado registra referência antes da atualização recuperável da URL', async () => {
    routing.route.query = { dataset: job.dataset_id }
    routing.replace.mockImplementation(async (location) => {
      expect(known.remember).toHaveBeenCalledWith('admin-token', 'training', { jobId: job.id, datasetId: job.dataset_id })
      if (typeof location === 'object') routing.route.query = location.query
    })
    const wrapper = render(); await flushPromises()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(routing.route.query).toEqual({ dataset: job.dataset_id, job: job.id })
    expect(createTraining).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
  it('dataset inválido com job válido bloqueia todas as consultas da retomada', async () => {
    routing.route.query = { job: job.id, dataset: 'invalid' }
    const wrapper = render(); await flushPromises()
    expect(fetchDatasets).not.toHaveBeenCalled(); expect(fetchDataset).not.toHaveBeenCalled()
    expect(fetchTrainingJob).not.toHaveBeenCalled(); expect(known.remember).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('falha de listagem inicial não transforma dataset da URL em edição', async () => {
    routing.route.query = { dataset: fixture.dataset_id }
    vi.mocked(fetchDatasets).mockRejectedValueOnce(new Error('offline'))
    const wrapper = render(); await flushPromises()
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(fixture.dataset_id)
    expect(selectionIsDirty(wrapper)).toBe(false)
    expect(draftPrompt.value).toBeNull()
    wrapper.unmount()
  })
  it('job ainda não confirmado bloqueia edição e não cria aviso de rascunho', async () => {
    routing.route.query = { job: fixture.job_id }
    vi.mocked(fetchTrainingJob).mockRejectedValueOnce(new Error('offline'))
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('select').attributes('disabled')).toBeDefined()
    expect(selectionIsDirty(wrapper)).toBe(false)
    const move = vi.fn()
    expect(await requestDraftTransition(move)).toBe(true)
    expect(move).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
  it('proteção real mantém ou descarta somente a escolha de dataset antes de transição', async () => {
    const wrapper = render(); await flushPromises()
    await wrapper.get('select').setValue(fixture.dataset_id); await flushPromises()
    const move = vi.fn()
    const staying = requestDraftTransition(move)
    await flushPromises()
    expect(draftPrompt.value?.labels).toEqual(['Dataset do treinamento'])
    resolveDraftPrompt(false)
    expect(await staying).toBe(false)
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(fixture.dataset_id)
    const leaving = requestDraftTransition(move)
    await flushPromises(); resolveDraftPrompt(true)
    expect(await leaving).toBe(true)
    expect(move).toHaveBeenCalledOnce()
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('')
    expect(selectionIsDirty(wrapper)).toBe(false)
    wrapper.unmount()
  })
  it('POST tardio de outra sessão não confirma baseline da escolha nova', async () => {
    let finish!: (value: TrainingJob) => void
    vi.mocked(createTraining).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = render(); await flushPromises()
    await wrapper.get('select').setValue(fixture.dataset_id); await flushPromises()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    sessionToken.value = 'other-admin'; await flushPromises()
    await wrapper.get('select').setValue(fixture.dataset_id); await flushPromises()
    finish(job); await flushPromises()
    expect(selectionIsDirty(wrapper)).toBe(true)
    expect(routing.replace).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-labelledby="training-job-title"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('envio incerto não pede descarte de possível job nem repete o POST ao sair', async () => {
    vi.mocked(createTraining).mockRejectedValueOnce(new Error('offline'))
    const wrapper = render(); await flushPromises()
    await wrapper.get('select').setValue(fixture.dataset_id); await flushPromises()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(selectionIsDirty(wrapper)).toBe(false)
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(fixture.dataset_id)
    const move = vi.fn()
    expect(await requestDraftTransition(move)).toBe(true)
    expect(draftPrompt.value).toBeNull()
    expect(createTraining).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
  it('somente escolha manual diferente do dataset inicial é rascunho, não seed e split fixos', async () => {
    const otherId = '00000000-0000-4000-8000-000000000123'
    routing.route.query = { dataset: fixture.dataset_id }
    vi.mocked(fetchDatasets).mockResolvedValue([
      { id: fixture.dataset_id, name: 'Inicial', row_count: 1000000, created_at: job.created_at, generation_job_id: fixture.job_id },
      { id: otherId, name: 'Outro', row_count: 1000000, created_at: job.created_at, generation_job_id: fixture.job_id },
    ])
    const wrapper = render(); await flushPromises()
    expect(selectionIsDirty(wrapper)).toBe(false)
    expect(wrapper.find('input[name="seed"]').exists()).toBe(false)
    await wrapper.get('select').setValue(otherId); await flushPromises()
    expect(selectionIsDirty(wrapper)).toBe(true)
    await wrapper.get('select').setValue(fixture.dataset_id); await flushPromises()
    expect(selectionIsDirty(wrapper)).toBe(false)
    wrapper.unmount()
  })
  it('erro conserva escolha não enviada e sucesso confirma baseline antes de trocar URL', async () => {
    vi.mocked(createTraining).mockRejectedValueOnce(new TrainingRequestError(422))
    const wrapper = render(); await flushPromises()
    await wrapper.get('select').setValue(fixture.dataset_id); await flushPromises()
    expect(selectionIsDirty(wrapper)).toBe(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(selectionIsDirty(wrapper)).toBe(true)
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(fixture.dataset_id)
    routing.replace.mockImplementation(async (location) => {
      expect(selectionIsDirty(wrapper)).toBe(false)
      if (typeof location === 'object') routing.route.query = location.query
    })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(routing.route.query.job).toBe(job.id)
    expect(selectionIsDirty(wrapper)).toBe(false)
    wrapper.unmount()
  })
  it('preseleciona dataset do laboratório, confirma resumo antes do POST e não duplica', async () => {
    routing.route.query = { dataset: fixture.dataset_id }
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('select').element.value).toBe(fixture.dataset_id)
    expect(wrapper.text()).toContain('400.000'); expect(wrapper.text()).toContain('Seed do treino: 42')
    await wrapper.get('form').trigger('submit'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(createTraining).toHaveBeenCalledOnce(); expect(fetchDataset).toHaveBeenCalledTimes(3)
    expect(routing.route.query.job).toBe(fixture.job_id); wrapper.unmount()
  })
  it('100% das etapas em execução não consulta resultado nem libera pacote antes de completed', async () => {
    routing.route.query = { job: job.id }
    vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'running', completed_units: 2 })
    const wrapper = render()
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('Em execução')
      expect(wrapper.find('[aria-labelledby="training-result-title"]').exists()).toBe(false)
      expect(fetchTrainingResult).not.toHaveBeenCalled()
      vi.mocked(fetchTrainingJob).mockResolvedValue({ ...job, status: 'completed', completed_units: 2, result_id: fixture.model_id })
      await vi.advanceTimersByTimeAsync(1500); await flushPromises()
      expect(fetchTrainingResult).toHaveBeenCalledOnce()
      expect(wrapper.text()).toContain('Pacote rejeitado')
      expect(createTraining).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
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
