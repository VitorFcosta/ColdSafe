<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearSession, forgetKnownJob, knownJobs, rememberKnownJob, sessionRole, sessionToken } from '../features/account/session'
import { useDraftProtection } from '../features/editing/draft-protection'
import { fetchDataset, LaboratoryAccessError, sensorChoices, type Dataset } from '../features/laboratory/laboratory-api'
import { isUuid } from '../features/monitoring/aiot-api'
import { createTraining, fetchDatasets, fetchTrainingJob, fetchTrainingResult, TrainingAccessError, TrainingRequestError, type DatasetChoice, type TrainingJob, type TrainingResult } from '../features/training/training-api'
import TrainingTarget from '../features/training/TrainingTarget.vue'
import LlmStatus from '../features/llm/LlmStatus.vue'
import JobResumeLinks from '../features/jobs/JobResumeLinks.vue'
const route = useRoute()
const router = useRouter()
const datasets = ref<DatasetChoice[]>([])
const selected = ref('')
const dataset = ref<Dataset | null>(null)
const job = ref<TrainingJob | null>(null)
const result = ref<TrainingResult | null>(null)
const error = ref('')
const loading = ref(false)
const loadingDataset = ref(false)
const refreshing = ref(false)
const submitting = ref(false)
const uncertain = ref(false)
const denied = ref(false)
const unavailableJob = ref(false)
const authorized = computed(() => Boolean(sessionToken.value) && sessionRole.value === 'admin' && !denied.value)
const activeJob = computed(() => job.value?.status === 'queued' || job.value?.status === 'running')
const unknownJob = computed(() => route.query.job !== undefined && !job.value)
const selectionBaseline = ref('')
const selectionDirty = computed(() => authorized.value && !submitting.value && !activeJob.value &&
  !loading.value && !unknownJob.value && !uncertain.value && selected.value !== selectionBaseline.value)
useDraftProtection({ dirty: selectionDirty, label: 'Dataset do treinamento', discard: () => { selected.value = selectionBaseline.value } })
const blocked = computed(() => submitting.value || loadingDataset.value || loading.value || activeJob.value || uncertain.value || Boolean(route.query.job && !job.value) || !dataset.value || dataset.value.config.equipment_count < 3)
const labels = { queued: 'Na fila', running: 'Em execução', completed: 'Concluído', failed: 'Falhou', cancelled: 'Cancelado' }
const number = (v: number) => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 }).format(v)
let revision = 0
let datasetRevision = 0
let timer: ReturnType<typeof setTimeout> | undefined
const requests = new Set<AbortController>()
let datasetController: AbortController | undefined
let datasetDeadline: ReturnType<typeof setTimeout> | undefined
function current(version: number) { return version === revision && authorized.value }
function resetPrivate() { datasets.value = []; dataset.value = null; job.value = null; result.value = null; selected.value = ''; selectionBaseline.value = '' }
function accessError(cause: unknown) {
  if (!(cause instanceof TrainingAccessError) && !(cause instanceof LaboratoryAccessError)) return false
  resetPrivate(); denied.value = true
  if (cause.status === 401) clearSession()
  else error.value = 'Acesso ao treinamento indisponível. Consulte outro trabalho conhecido ou entre novamente.'
  return true
}
async function bounded<T>(operation: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController(); requests.add(controller)
  const deadline = setTimeout(() => controller.abort(), 8000)
  try { return await operation(controller.signal) } finally { clearTimeout(deadline); requests.delete(controller) }
}
function validRouteReferences() {
  const { job: id, dataset: datasetId } = route.query
  if ((id !== undefined && (typeof id !== 'string' || !isUuid(id))) ||
    (datasetId !== undefined && (typeof datasetId !== 'string' || !isUuid(datasetId)))) {
    error.value = 'Identificador de job ou dataset inválido na URL.'
    return false
  }
  return true
}
async function loadDatasets() {
  const token = sessionToken.value; const version = revision
  if (!token || !authorized.value || !validRouteReferences()) return
  const wanted = selected.value || job.value?.dataset_id || (route.query.job ? '' : route.query.dataset)
  selected.value = ''; dataset.value = null; loading.value = true
  try {
    const choices = await bounded((signal) => fetchDatasets(token, signal))
    if (!current(version)) return
    datasets.value = choices
    if (!selected.value && typeof wanted === 'string') selected.value = wanted
  } catch (cause) {
    if (current(version) && !accessError(cause)) {
      if (!selected.value && typeof wanted === 'string') selected.value = wanted
      error.value = 'Não foi possível listar os datasets. Tente consultar novamente.'
    }
  }
  finally { if (current(version)) loading.value = false }
}
function rejectJobReference(token: string, id: string, mismatchedDataset?: string) {
  const saved = knownJobs.value.training
  if (!mismatchedDataset || (saved?.jobId === id && saved.datasetId === mismatchedDataset)) forgetKnownJob(token, 'training', id)
  job.value = null; result.value = null; dataset.value = null; selected.value = ''; selectionBaseline.value = ''
  unavailableJob.value = true
  error.value = 'Treinamento indisponível. Confira o endereço ou consulte outro trabalho conhecido.'
}
async function refresh(retryDataset = false) {
  const token = sessionToken.value; const id = route.query.job; const version = revision
  const requestedDataset = route.query.dataset
  if (!token || !authorized.value || refreshing.value || !validRouteReferences() || typeof id !== 'string' || !isUuid(id)) return
  refreshing.value = true; clearTimeout(timer)
  let confirmed = false
  try {
    const next = await bounded((signal) => fetchTrainingJob(token, id, signal))
    if (!current(version)) return
    if (typeof requestedDataset === 'string' && requestedDataset !== next.dataset_id) {
      rejectJobReference(token, id, requestedDataset); return
    }
    const initial = job.value?.id !== next.id
    confirmed = true; unavailableJob.value = false
    job.value = next; error.value = ''
    if (initial) { selectionBaseline.value = next.dataset_id; selected.value = next.dataset_id }
    rememberKnownJob(token, 'training', { jobId: next.id, datasetId: next.dataset_id })
    if (!initial && retryDataset && !dataset.value && selected.value === next.dataset_id) await loadSelectedDataset(selected.value)
    if (!current(version)) return
    if (next.status === 'completed' && !result.value) {
      const report = await bounded((signal) => fetchTrainingResult(token, next.id, signal))
      if (!current(version)) return
      if (report.dataset_id !== next.dataset_id || report.model_id !== next.result_id) throw new Error('Resultado divergente')
      result.value = report
    }
  } catch (cause) {
    if (!current(version)) return
    if (!confirmed && ((cause instanceof TrainingAccessError && cause.status === 403) ||
      (cause instanceof TrainingRequestError && cause.status === 404))) { rejectJobReference(token, id); return }
    if (confirmed && cause instanceof TrainingAccessError && cause.status === 403) {
      result.value = null
      error.value = 'O treinamento foi concluído, mas o resultado está indisponível. Consulte novamente; não é necessário reenviar o treino.'
      return
    }
    if (!accessError(cause)) error.value = job.value?.status === 'completed'
      ? 'O treinamento foi concluído, mas o resultado está indisponível ou inválido. Consulte novamente; não é necessário reenviar o treino.'
      : 'Não foi possível confirmar a situação atual do treinamento. Você pode repetir a consulta.'
  } finally {
    if (current(version)) { refreshing.value = false; if (!unavailableJob.value && (!job.value || activeJob.value)) timer = setTimeout(() => { void refresh() }, 1500) }
  }
}
watch([sessionToken, sessionRole, () => route.query.job, () => route.query.dataset], ([token, role, id, datasetId], _old, onCleanup) => {
  revision += 1; datasetRevision += 1; resetPrivate(); error.value = ''; submitting.value = false; refreshing.value = false; loading.value = false; loadingDataset.value = false; uncertain.value = false; denied.value = false; unavailableJob.value = false
  onCleanup(() => { revision += 1; datasetRevision += 1; clearTimeout(timer); for (const request of requests) request.abort(); requests.clear() })
  if (!token) { void router.replace('/login'); return }
  if (role !== 'admin') return
  if (!validRouteReferences()) return
  selectionBaseline.value = typeof datasetId === 'string' ? datasetId : ''
  void loadDatasets(); if (id) void refresh()
}, { immediate: true, flush: 'sync' })
function cancelDatasetRequest() {
  datasetController?.abort(); clearTimeout(datasetDeadline)
  if (datasetController) requests.delete(datasetController)
  datasetController = undefined
  loadingDataset.value = false
}
async function loadSelectedDataset(id: string) {
  cancelDatasetRequest()
  const token = sessionToken.value; const version = revision; const selectionVersion = ++datasetRevision
  dataset.value = null
  if (!token || !authorized.value || !validRouteReferences() || !isUuid(id) || (route.query.job !== undefined && !job.value)) return
  loadingDataset.value = true; error.value = ''
  const controller = new AbortController(); requests.add(controller); datasetController = controller
  const deadline = setTimeout(() => controller.abort(), 8000); datasetDeadline = deadline
  try {
    const summary = await fetchDataset(token, id, controller.signal)
    if (current(version) && selectionVersion === datasetRevision) dataset.value = summary
  } catch (cause) {
    if (!current(version) || selectionVersion !== datasetRevision) return
    if (job.value?.dataset_id === id && cause instanceof LaboratoryAccessError && cause.status === 403) {
      error.value = 'O dataset está indisponível. Consulte novamente; não é necessário reenviar o treinamento.'
      return
    }
    if (!accessError(cause)) error.value = 'Não foi possível consultar o dataset selecionado.'
  } finally {
    clearTimeout(deadline); requests.delete(controller)
    if (datasetController === controller) datasetController = undefined
    if (current(version) && selectionVersion === datasetRevision) loadingDataset.value = false
  }
}
watch(selected, (id, _old, onCleanup) => {
  onCleanup(() => { datasetRevision += 1; cancelDatasetRequest() })
  void loadSelectedDataset(id)
})
async function train() {
  const token = sessionToken.value; const id = selected.value; const version = revision
  if (!token || !authorized.value || blocked.value) return
  submitting.value = true; error.value = ''; result.value = null
  let posting = false
  try {
    const summary = await bounded((signal) => fetchDataset(token, id, signal))
    if (!current(version)) return
    dataset.value = summary
    if (summary.config.equipment_count < 3) { error.value = 'O treinamento exige ao menos três equipamentos para separar treino, validação e teste.'; return }
    posting = true
    const created = await bounded((signal) => createTraining(token, id, signal))
    if (!current(version)) return
    selectionBaseline.value = id
    rememberKnownJob(token, 'training', { jobId: created.id, datasetId: created.dataset_id })
    job.value = created
    await router.replace({ query: { dataset: id, job: created.id } })
  } catch (cause) {
    if (!current(version) || accessError(cause)) return
    if (!posting) { error.value = 'Não foi possível confirmar o dataset. Nenhum treinamento foi enviado.'; return }
    if (cause instanceof TrainingRequestError && [404, 409, 422].includes(cause.status)) { error.value = 'A API recusou o treinamento. Confira o dataset e os requisitos antes de tentar novamente.'; return }
    uncertain.value = true; error.value = 'Não foi possível confirmar o envio. O job pode ter sido criado; não envie novamente sem conferir os jobs da conta. O envio não será repetido automaticamente. Sem um ID confirmado, este envio não tem retomada garantida; os links de retomada apontam somente para trabalhos confirmados anteriormente.'
  } finally { if (current(version)) submitting.value = false }
}
</script>

<template>
  <main class="training cs-controls">
    <div class="shell">
      <section class="heading" aria-labelledby="training-title">
        <h1 id="training-title" tabindex="-1">Treinamento</h1>
        <p>Compare saúde e vida útil restante com uma baseline e inspecione os erros. Treinar um pacote não o ativa no monitoramento.</p>
      </section>
      <p v-if="!authorized" role="status">O treinamento está disponível apenas para administradores. Visualizadores e operadores não podem iniciar treinamentos nem consultar estes resultados.</p>
      <template v-else>
        <section class="panel" aria-labelledby="training-config-title">
          <div class="setup-heading">
            <h2 id="training-config-title">Selecionar dataset concluído</h2>
            <div class="model-state"><LlmStatus /></div>
          </div>
          <p id="dataset-help" class="hint">Lista dos 50 datasets próprios concluídos mais recentes. A URL também pode indicar outro dataset autorizado. <RouterLink to="/laboratory">Gerar dados no laboratório</RouterLink>.</p>
          <p v-if="loading" role="status">Consultando datasets…</p>
          <p v-else-if="!datasets.length" class="hint">Nenhum dataset concluído disponível na lista.</p>
          <form class="setup" :aria-busy="submitting || loadingDataset" @submit.prevent="train">
            <div class="dataset-field">
              <label for="training-dataset">Dataset</label>
              <select id="training-dataset" v-model="selected" aria-describedby="dataset-help training-protocol" :disabled="loading || submitting || activeJob || unknownJob || uncertain">
                <option value="">Selecione um dataset</option>
                <option v-if="selected && !datasets.some((d) => d.id === selected)" :value="selected">Dataset indicado na URL · {{ selected }}</option>
                <option v-for="choice in datasets" :key="choice.id" :value="choice.id">{{ choice.name }} · {{ number(choice.row_count) }} linhas</option>
              </select>
              <p v-if="loadingDataset" role="status">Conferindo configuração do dataset…</p>
              <template v-if="dataset">
                <p>Dataset: {{ dataset.id }} · {{ number(dataset.row_count) }} linhas · Seed da geração: {{ dataset.config.seed }} · {{ dataset.config.equipment_count }} equipamentos · {{ dataset.config.days }} dias.</p>
                <p>Sensores: {{ sensorChoices.filter(([key]) => dataset!.config.sensor_types.includes(key)).map(([, label]) => label).join('; ') }}.</p>
                <p>RUL observado: {{ number(dataset.quality.rul_observed_rows) }} linhas; censurado: {{ number(dataset.quality.rul_censored_rows) }}. Censurado significa falha não observada, sem duração restante conhecida; essas linhas ficam fora do treino de RUL.</p>
                <details><summary>Configuração do dataset</summary><pre>{{ JSON.stringify(dataset.config, null, 2) }}</pre></details>
                <p v-if="dataset.config.equipment_count < 3" class="feedback error" role="alert">O treinamento exige ao menos três equipamentos para separar treino, validação e teste.</p>
              </template>
            </div>
            <div class="protocol">
              <h3>Configuração fixa do treino</h3>
              <p id="training-protocol">Seed do treino: 42. Split por equipamento: aproximadamente 70% treino, 15% validação e restante teste, com seed 42. A seleção usa a validação; os gráficos usam até 500 linhas reservadas do teste.</p>
              <button class="primary" type="submit" :disabled="blocked">{{ submitting ? 'Enviando…' : 'Iniciar treinamento' }}</button>
              <div class="resume"><JobResumeLinks /></div>
            </div>
          </form>
        </section>
        <div v-if="error" class="recovery">
          <p class="feedback error" role="alert">{{ error }}</p>
          <button type="button" :disabled="refreshing || loading" @click="route.query.job ? refresh(true) : loadDatasets()">{{ route.query.job ? 'Atualizar acompanhamento' : 'Consultar datasets novamente' }}</button>
        </div>
        <section v-if="job" class="panel" aria-labelledby="training-job-title" :aria-busy="refreshing">
          <h2 id="training-job-title">Acompanhamento do treinamento</h2>
          <p class="verdict" role="status">{{ labels[job.status] }} · {{ number(job.completed_units) }} / {{ number(job.total_units) }} etapas</p>
          <progress :value="job.completed_units" :max="job.total_units" aria-label="Etapas do treinamento"></progress>
          <p>Job: {{ job.id }} · Dataset: {{ job.dataset_id }}</p>
          <p class="hint">Atualizado em <time :datetime="job.updated_at">{{ new Date(job.updated_at).toLocaleString('pt-BR') }}</time>.</p>
          <p v-if="activeJob">Consulta a cada 1,5 segundo. Recarregar esta URL retoma o acompanhamento sem reenviar o pedido. 100% das etapas ainda pode anteceder a conclusão.</p>
          <p v-if="job.status === 'failed' || job.status === 'cancelled'" class="feedback error">{{ job.status === 'failed' ? 'O treinamento falhou.' : 'O treinamento foi cancelado.' }} Código: {{ job.error_code ?? 'Não informado' }}. Resultados parciais não são um pacote concluído.</p>
        </section>
        <template v-if="result">
          <section class="panel" aria-labelledby="training-result-title">
            <h2 id="training-result-title">Resultado do pacote</h2>
            <p class="verdict" :class="result.eligible ? 'eligible' : 'rejected'">{{ result.eligible ? 'Pacote apto pela validação' : 'Pacote rejeitado: ao menos um alvo não superou os critérios da validação' }}</p>
            <p>Job concluído confirma o fim do processamento. A aptidão de cada modelo é avaliada separadamente; nenhum resultado desta página ativa modelos.</p>
            <dl class="package-details">
              <div><dt>Versão do pacote</dt><dd>{{ result.model_version }} · {{ result.model_id }}</dd></div>
              <div><dt>Features</dt><dd>{{ result.features_version }}</dd></div>
              <div><dt>Seed / seed do split</dt><dd>{{ result.seed }} / {{ result.split_seed }}</dd></div>
              <div><dt>Equipamentos por partição</dt><dd>Treino {{ result.equipment_counts.train }}, validação {{ result.equipment_counts.validation }}, teste {{ result.equipment_counts.test }}. Equipamentos separados evitam compartilhar a mesma máquina entre treino e avaliação.</dd></div>
            </dl>
            <details><summary>Versões das ferramentas</summary><dl><div v-for="(version, key) in result.versions" :key="key"><dt>{{ key }}</dt><dd>{{ version }}</dd></div></dl></details>
            <h3>Limitações</h3><ul><li v-for="limitation in result.limitations" :key="limitation">{{ limitation }}</li></ul>
          </section>
          <div class="results-grid"><TrainingTarget :result="result.health" /><TrainingTarget :result="result.rul" /></div>
        </template>
      </template>
    </div>
  </main>
</template>

<style scoped>
.training { padding: var(--cs-space-48); }
.shell { max-width: 1200px; margin-inline: auto; display: grid; gap: var(--cs-space-24); min-width: 0; }
.heading h1 { font-size: var(--cs-type-32); margin-block: var(--cs-space-8); }
.heading p { color: var(--cs-color-ink-muted); max-width: 70ch; }
.panel { padding: var(--cs-space-24); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); min-width: 0; }
h2 { font-size: var(--cs-type-20); } h3 { font-size: var(--cs-type-16); font-weight: 600; margin-top: var(--cs-space-24); }
p { line-height: 1.6; margin-top: var(--cs-space-12); }
a { color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
.setup-heading { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--cs-space-16); align-items: start; }
.model-state { max-width: 420px; min-width: 0; }.model-state :deep(.llm-status) { margin: 0; padding: var(--cs-space-12); border: 0; background: var(--cs-color-surface-muted); font-size: var(--cs-type-14); }
.setup { display: grid; grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr); gap: var(--cs-space-32); margin-top: var(--cs-space-24); }
.dataset-field { display: grid; gap: var(--cs-space-8); align-content: start; min-width: 0; }.dataset-field p { margin-top: var(--cs-space-4); }
select { width: 100%; min-width: 0; min-height: var(--cs-control-min-height); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); padding: var(--cs-space-8) var(--cs-space-12); background: var(--cs-color-surface); color: var(--cs-color-ink); font: inherit; font-size: var(--cs-type-16); }
select:disabled { background: var(--cs-color-surface-muted); color: var(--cs-color-ink-muted); cursor: not-allowed; }
.protocol { min-width: 0; }.protocol h3 { margin-top: 0; }.protocol .primary { margin-top: var(--cs-space-24); }
.resume :deep(.resume-links) { margin: var(--cs-space-24) 0 0; padding: var(--cs-space-16) 0 0; border: 0; border-top: 1px solid var(--cs-color-line); border-radius: 0; }
progress { display: block; margin-top: var(--cs-space-16); width: 100%; height: var(--cs-space-8); appearance: none; border: 0; border-radius: var(--cs-radius-4); background: var(--cs-color-surface-muted); overflow: hidden; }
progress::-webkit-progress-bar { background: var(--cs-color-surface-muted); } progress::-webkit-progress-value { background: var(--cs-color-accent); } progress::-moz-progress-bar { background: var(--cs-color-accent); }
.verdict { font-weight: 650; }.verdict.eligible, .verdict.rejected { display: inline-block; padding: var(--cs-space-8) var(--cs-space-12); border-radius: var(--cs-radius-4); }.eligible { color: var(--cs-color-status-normal); background: var(--cs-color-normal-surface); }.rejected { color: var(--cs-color-status-attention); background: var(--cs-color-attention-surface); }
.package-details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16) var(--cs-space-32); margin-block: var(--cs-space-24); }
dl div { margin-top: var(--cs-space-8); } dt { font-weight: 600; } dd { overflow-wrap: anywhere; }
summary { min-height: var(--cs-control-min-height); display: list-item; align-content: center; cursor: pointer; color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: var(--cs-space-16); background: var(--cs-color-canvas); font-size: var(--cs-type-14); }
ul { margin-top: var(--cs-space-8); padding-left: var(--cs-space-24); list-style: disc; }
.results-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); align-items: start; }
.recovery .feedback { margin-top: 0; }
@media (max-width: 1100px) {
  .training { padding: var(--cs-space-16); }.heading h1 { font-size: var(--cs-type-24); line-height: 1.3333; }
  .panel { padding: var(--cs-space-16); }.setup, .results-grid, .package-details { grid-template-columns: minmax(0, 1fr); }
  .setup { gap: var(--cs-space-24); }.protocol .primary { width: 100%; }
}
</style>
