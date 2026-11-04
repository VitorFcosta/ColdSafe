// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { sessionToken, sessionRole, refreshSessionIdentity, setSession, knownJobs, rememberKnownJob } from '../features/account/session'
import { draftPrompt, requestDraftTransition, resolveDraftPrompt } from '../features/editing/draft-protection'
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
const render = () => mount(LaboratoryView, { attachTo: document.body, global: { stubs: { LlmStatus: true, RouterLink: { template: '<a><slot /></a>' } } } })
// Vue mantém refs de script setup internamente; não expor API de produção só para testes.
const generationIsDirty = (wrapper: ReturnType<typeof render>) =>
  (wrapper.vm.$ as unknown as { setupState: { generationDirty: boolean } }).setupState.generationDirty
beforeEach(() => {
  vi.useFakeTimers(); routing.route = reactive({ query: {} }); routing.replace.mockReset().mockImplementation(async (location) => {
    if (typeof location === 'object') routing.route.query = location.query
  })
  setSession('admin-token', '2099-01-01T00:00:00Z'); sessionRole.value = 'admin'
  vi.mocked(createGeneration).mockReset().mockResolvedValue(job)
  vi.mocked(fetchJob).mockReset().mockResolvedValue(job)
  vi.mocked(fetchDataset).mockReset().mockResolvedValue(dataset)
  vi.mocked(fetchSample).mockReset().mockResolvedValue({ dataset_id: id, rows: [] })
  vi.mocked(refreshSessionIdentity).mockReset().mockImplementation(async () => { sessionRole.value = 'viewer' })
})
afterEach(() => vi.useRealTimers())

describe('Laboratório privado', () => {
  it('registra referência mínima em POST confirmado antes de trocar a URL', async () => {
    const wrapper = render()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(knownJobs.value.generation).toEqual({ jobId: id })
    wrapper.unmount()
  })
  it('consulta e registra o job autorizado sem POST ao recarregar', async () => {
    routing.route.query = { job: id }
    const wrapper = render(); await flushPromises()
    expect(knownJobs.value.generation).toEqual({ jobId: id })
    expect(createGeneration).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('par job/dataset divergente não consulta ou apresenta dataset associado', async () => {
    routing.route.query = { job: id, dataset: owner }
    vi.mocked(fetchJob).mockResolvedValueOnce({ ...job, status: 'completed', result_id: id, completed_units: job.total_units })
    const wrapper = render(); await flushPromises()
    expect(fetchDataset).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-labelledby="job-title"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('indisponível')
    wrapper.unmount()
  })
  it('UUID inválido em qualquer parâmetro bloqueia consultas e permite recuperação', async () => {
    routing.route.query = { job: id, dataset: 'invalid' }
    const wrapper = render(); await flushPromises()
    expect(fetchJob).not.toHaveBeenCalled(); expect(fetchDataset).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('inválido')
    await wrapper.findAll('button').find((button) => button.text() === 'Atualizar acompanhamento')!.trigger('click')
    await flushPromises()
    expect(fetchJob).not.toHaveBeenCalled(); expect(fetchDataset).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it.each([403, 404])('%s definitivo remove só job consultado e não entra em polling', async (status) => {
    rememberKnownJob('admin-token', 'generation', { jobId: id })
    rememberKnownJob('admin-token', 'training', { jobId: owner, datasetId: owner })
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockRejectedValueOnce(status === 403 ? new LaboratoryAccessError(403) : new LaboratoryRequestError(404))
    const wrapper = render(); await flushPromises()
    expect(knownJobs.value.generation).toBeUndefined()
    expect(knownJobs.value.training?.jobId).toBe(owner)
    await vi.advanceTimersByTimeAsync(6000)
    expect(fetchJob).toHaveBeenCalledOnce(); expect(createGeneration).not.toHaveBeenCalled()
    expect(refreshSessionIdentity).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('falha temporária preserva referência e retry só repete GET', async () => {
    rememberKnownJob('admin-token', 'generation', { jobId: id })
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockRejectedValueOnce(new Error('offline'))
    const wrapper = render(); await flushPromises()
    expect(knownJobs.value.generation?.jobId).toBe(id)
    await wrapper.findAll('button').find((button) => button.text() === 'Atualizar acompanhamento')!.trigger('click')
    await flushPromises()
    expect(fetchJob).toHaveBeenCalledTimes(2); expect(createGeneration).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('403 do resultado conserva job conhecido e permite consultar novamente sem POST', async () => {
    routing.route.query = { job: id }
    vi.mocked(fetchJob).mockResolvedValue({ ...job, status: 'completed', result_id: id, completed_units: job.total_units })
    vi.mocked(fetchDataset).mockRejectedValueOnce(new LaboratoryAccessError(403))
    const wrapper = render(); await flushPromises()
    expect(wrapper.find('[aria-labelledby="job-title"]').exists()).toBe(true)
    expect(knownJobs.value.generation?.jobId).toBe(id)
    await wrapper.findAll('button').find((button) => button.text() === 'Atualizar acompanhamento')!.trigger('click')
    await flushPromises()
    expect(fetchDataset).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Dataset concluído')
    expect(createGeneration).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('proteção real permite permanecer ou descartar antes de executar uma transição', async () => {
    const wrapper = render()
    await wrapper.get('input[name="seed"]').setValue(123)
    const move = vi.fn()
    const staying = requestDraftTransition(move)
    await flushPromises()
    expect(draftPrompt.value?.labels).toEqual(['Parâmetros de geração'])
    resolveDraftPrompt(false)
    expect(await staying).toBe(false)
    expect(move).not.toHaveBeenCalled()
    expect((wrapper.get('input[name="seed"]').element as HTMLInputElement).value).toBe('123')
    const leaving = requestDraftTransition(move)
    await flushPromises(); resolveDraftPrompt(true)
    expect(await leaving).toBe(true)
    expect(move).toHaveBeenCalledOnce()
    expect((wrapper.get('input[name="seed"]').element as HTMLInputElement).value).toBe('42')
    expect(generationIsDirty(wrapper)).toBe(false)
    wrapper.unmount()
  })
  it('rascunho compara valores reais e volta a limpo ao restaurar campos e escolhas', async () => {
    const wrapper = render()
    expect(generationIsDirty(wrapper)).toBe(false)
    const seed = wrapper.get('input[name="seed"]')
    await seed.setValue(123)
    expect(generationIsDirty(wrapper)).toBe(true)
    await seed.setValue(42)
    expect(generationIsDirty(wrapper)).toBe(false)
    const sensor = wrapper.findAll('input[name="sensor_types"]')[0]!
    await sensor.setValue(false)
    expect(generationIsDirty(wrapper)).toBe(true)
    await sensor.setValue(true)
    expect(generationIsDirty(wrapper)).toBe(false)
    await wrapper.get('input[name="environment_id"]').setValue(owner)
    expect(generationIsDirty(wrapper)).toBe(true)
    wrapper.unmount()
  })
  it('erro conserva rascunho e envio confirmado deixa de ser edição perdida', async () => {
    vi.mocked(createGeneration).mockRejectedValueOnce(new LaboratoryRequestError(422))
    const wrapper = render()
    await wrapper.get('input[name="seed"]').setValue(123)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(generationIsDirty(wrapper)).toBe(true)
    expect((wrapper.get('input[name="seed"]').element as HTMLInputElement).value).toBe('123')
    routing.replace.mockImplementation(async (location) => {
      expect(generationIsDirty(wrapper)).toBe(false)
      if (typeof location === 'object') routing.route.query = location.query
    })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(generationIsDirty(wrapper)).toBe(false)
    expect(routing.route.query.job).toBe(id)
    wrapper.unmount()
  })
  it('envio incerto conserva parâmetros bloqueados sem tratar o possível job como rascunho', async () => {
    vi.mocked(createGeneration).mockRejectedValueOnce(new Error('offline'))
    const wrapper = render()
    await wrapper.get('input[name="seed"]').setValue(123)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(generationIsDirty(wrapper)).toBe(false)
    expect((wrapper.get('input[name="seed"]').element as HTMLInputElement).value).toBe('123')
    const move = vi.fn()
    expect(await requestDraftTransition(move)).toBe(true)
    expect(draftPrompt.value).toBeNull()
    expect(move).toHaveBeenCalledOnce()
    expect(createGeneration).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
  it('retorno de envio antigo não limpa edição em outra sessão', async () => {
    let finish!: (value: GenerationJob) => void
    vi.mocked(createGeneration).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = render()
    await wrapper.get('input[name="seed"]').setValue(123)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(generationIsDirty(wrapper)).toBe(false)
    sessionToken.value = 'new-account'; await flushPromises()
    await wrapper.get('input[name="seed"]').setValue(456)
    finish(job); await flushPromises()
    expect(generationIsDirty(wrapper)).toBe(true)
    expect((wrapper.get('input[name="seed"]').element as HTMLInputElement).value).toBe('456')
    expect(routing.replace).not.toHaveBeenCalled()
    wrapper.unmount()
  })
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
  it('identifica o campo inválido, associa o erro e orienta o foco sem POST', async () => {
    const wrapper = render()
    try {
      const lines = wrapper.get('input[name="total_units"]')
      await lines.setValue(2000001)
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(createGeneration).not.toHaveBeenCalled()
      expect(lines.attributes('aria-invalid')).toBe('true')
      expect(lines.attributes('aria-describedby')).toContain('total_units-error')
      expect(wrapper.get('#total_units-error').text()).toContain('1.000.000 a 2.000.000')
      expect(document.activeElement).toBe(lines.element)
      await lines.setValue(1000000)
      expect(wrapper.find('#total_units-error').exists()).toBe(false)
      expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    } finally { wrapper.unmount() }
  })
  it.each(['sensor_types', 'failure_modes', 'operating_modes'])('identifica conjunto vazio %s e foca sua primeira opção', async (name) => {
    const wrapper = render()
    try {
      const choices = wrapper.findAll(`input[name="${name}"]`)
      for (const choice of choices) await choice.setValue(false)
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(createGeneration).not.toHaveBeenCalled()
      expect(wrapper.get(`#${name}-error`).text()).toContain('Selecione ao menos')
      expect(choices[0]!.attributes('aria-describedby')).toContain(`${name}-error`)
      expect(document.activeElement).toBe(choices[0]!.element)
    } finally { wrapper.unmount() }
  })
  it.each([
    ['total_units', 999999], ['total_units', 1000000.5], ['seed', -1], ['seed', 4294967296],
    ['seed', 1.5], ['equipment_count', 0], ['equipment_count', 10001], ['equipment_count', 1.5],
    ['days', 0], ['days', 3651], ['failure_fraction', 1.1], ['noise_scale', 11],
    ['missing_rate', -0.1], ['outlier_rate', 1.1], ['total_units', ''],
  ])('associa limites ou obrigatoriedade de %s=%s sem POST', async (name, value) => {
    const wrapper = render()
    try {
      const field = wrapper.get(`input[name="${name}"]`)
      await field.setValue(value)
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(field.attributes('aria-invalid')).toBe('true')
      expect(document.activeElement).toBe(field.element)
      expect(createGeneration).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
  it('associa UUID opcional inválido e aceita remover o vínculo', async () => {
    const wrapper = render()
    try {
      const field = wrapper.get('input[name="environment_id"]')
      await field.setValue('invalid')
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(field.attributes('aria-invalid')).toBe('true')
      expect(wrapper.get('#environment-error').text()).toContain('UUID válido')
      expect(document.activeElement).toBe(field.element)
      expect(createGeneration).not.toHaveBeenCalled()
      await field.setValue('')
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(createGeneration).toHaveBeenCalledOnce()
    } finally { wrapper.unmount() }
  })
  it('aceita dias positivos menores que um milionésimo sem criar novo limite', async () => {
    const wrapper = render()
    try {
      await wrapper.get('input[name="days"]').setValue(0.0000001)
      expect(wrapper.get('.estimate').text()).toContain('0,0000001')
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(createGeneration).toHaveBeenCalledWith('admin-token', expect.objectContaining({ days: 0.0000001 }), expect.any(AbortSignal))
    } finally { wrapper.unmount() }
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
    else expect(refreshSessionIdentity).not.toHaveBeenCalled()
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
