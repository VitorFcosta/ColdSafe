<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearSession, logout, refreshSessionIdentity, sessionRole, sessionToken } from '../features/account/session'
import { fetchDataset, LaboratoryAccessError, sensorChoices, type Dataset } from '../features/laboratory/laboratory-api'
import { isUuid } from '../features/monitoring/aiot-api'
import { createTraining, fetchDatasets, fetchTrainingJob, fetchTrainingResult, TrainingAccessError, TrainingRequestError, type DatasetChoice, type TrainingJob, type TrainingResult } from '../features/training/training-api'
import TrainingTarget from '../features/training/TrainingTarget.vue'
const route = useRoute()
const router = useRouter()
const datasets = ref<DatasetChoice[]>([])
const selected = ref('')
const dataset = ref<Dataset | null>(null)
const job = ref<TrainingJob | null>(null)
const result = ref<TrainingResult | null>(null)
const error = ref('')
const logoutError = ref('')
const loading = ref(false)
const loadingDataset = ref(false)
const refreshing = ref(false)
const submitting = ref(false)
const uncertain = ref(false)
const denied = ref(false)
const authorized = computed(() => Boolean(sessionToken.value) && sessionRole.value === 'admin' && !denied.value)
const activeJob = computed(() => job.value?.status === 'queued' || job.value?.status === 'running')
const blocked = computed(() => submitting.value || loadingDataset.value || loading.value || activeJob.value || uncertain.value || Boolean(route.query.job && !job.value) || !dataset.value || dataset.value.config.equipment_count < 3)
const labels = { queued: 'Na fila', running: 'Em execução', completed: 'Concluído', failed: 'Falhou', cancelled: 'Cancelado' }
const number = (v: number) => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 }).format(v)
let revision = 0
let datasetRevision = 0
let timer: ReturnType<typeof setTimeout> | undefined
const requests = new Set<AbortController>()
function current(version: number) { return version === revision && authorized.value }
function resetPrivate() { datasets.value = []; dataset.value = null; job.value = null; result.value = null; selected.value = '' }
function accessError(cause: unknown) {
  if (!(cause instanceof TrainingAccessError) && !(cause instanceof LaboratoryAccessError)) return false
  resetPrivate(); denied.value = true
  if (cause.status === 401) clearSession()
  else void refreshSessionIdentity().catch(() => { /* Unknown permissions keep private data hidden. */ })
  return true
}
async function bounded<T>(operation: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController(); requests.add(controller)
  const deadline = setTimeout(() => controller.abort(), 8000)
  try { return await operation(controller.signal) } finally { clearTimeout(deadline); requests.delete(controller) }
}
async function loadDatasets() {
  const token = sessionToken.value; const version = revision
  if (!token || !authorized.value) return
  const wanted = selected.value || route.query.dataset
  selected.value = ''; dataset.value = null; loading.value = true
  try {
    const choices = await bounded((signal) => fetchDatasets(token, signal))
    if (!current(version)) return
    datasets.value = choices
    if (typeof wanted === 'string') selected.value = wanted
  } catch (cause) { if (current(version) && !accessError(cause)) error.value = 'Não foi possível listar os datasets. Tente consultar novamente.' }
  finally { if (current(version)) loading.value = false }
}
async function refresh() {
  const token = sessionToken.value; const id = route.query.job; const version = revision
  if (!token || !authorized.value || refreshing.value || typeof id !== 'string' || !isUuid(id)) return
  refreshing.value = true; clearTimeout(timer)
  try {
    const next = await bounded((signal) => fetchTrainingJob(token, id, signal))
    if (!current(version)) return
    job.value = next; error.value = ''
    if (next.status === 'completed' && !result.value) {
      const report = await bounded((signal) => fetchTrainingResult(token, next.id, signal))
      if (!current(version)) return
      if (report.dataset_id !== next.dataset_id || report.model_id !== next.result_id) throw new Error('Resultado divergente')
      result.value = report
    }
  } catch (cause) {
    if (current(version) && !accessError(cause)) error.value = job.value?.status === 'completed'
      ? 'O treinamento foi concluído, mas o resultado está indisponível ou inválido. Consulte novamente; não é necessário reenviar o treino.'
      : 'Não foi possível confirmar a situação atual do treinamento. Você pode repetir a consulta.'
  } finally {
    if (current(version)) { refreshing.value = false; if (!job.value || activeJob.value) timer = setTimeout(() => { void refresh() }, 1500) }
  }
}
watch([sessionToken, sessionRole, () => route.query.job, () => route.query.dataset], ([token, role, id, datasetId], _old, onCleanup) => {
  revision += 1; datasetRevision += 1; resetPrivate(); error.value = ''; submitting.value = false; refreshing.value = false; loading.value = false; loadingDataset.value = false; uncertain.value = false; denied.value = false
  onCleanup(() => { revision += 1; datasetRevision += 1; clearTimeout(timer); for (const request of requests) request.abort(); requests.clear() })
  if (!token) { void router.replace('/login'); return }
  if (role !== 'admin') return
  if ((id !== undefined && (typeof id !== 'string' || !isUuid(id))) || (datasetId !== undefined && (typeof datasetId !== 'string' || !isUuid(datasetId)))) { error.value = 'Identificador de job ou dataset inválido na URL.'; return }
  void loadDatasets(); if (id) void refresh()
}, { immediate: true, flush: 'sync' })
watch(selected, async (id, _old, onCleanup) => {
  const token = sessionToken.value; const version = revision; const selectionVersion = ++datasetRevision
  dataset.value = null
  if (!token || !authorized.value || !isUuid(id)) return
  loadingDataset.value = true; error.value = ''
  const controller = new AbortController(); requests.add(controller)
  const deadline = setTimeout(() => controller.abort(), 8000)
  onCleanup(() => { controller.abort(); clearTimeout(deadline); requests.delete(controller) })
  try {
    const summary = await fetchDataset(token, id, controller.signal)
    if (current(version) && selectionVersion === datasetRevision) dataset.value = summary
  } catch (cause) { if (current(version) && selectionVersion === datasetRevision && !accessError(cause)) error.value = 'Não foi possível consultar o dataset selecionado.' }
  finally { clearTimeout(deadline); requests.delete(controller); if (current(version) && selectionVersion === datasetRevision) loadingDataset.value = false }
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
    job.value = created
    await router.replace({ query: { dataset: id, job: created.id } })
  } catch (cause) {
    if (!current(version) || accessError(cause)) return
    if (!posting) { error.value = 'Não foi possível confirmar o dataset. Nenhum treinamento foi enviado.'; return }
    if (cause instanceof TrainingRequestError && [404, 409, 422].includes(cause.status)) { error.value = 'A API recusou o treinamento. Confira o dataset e os requisitos antes de tentar novamente.'; return }
    uncertain.value = true; error.value = 'Não foi possível confirmar o envio. O job pode ter sido criado; não envie novamente sem conferir os jobs da conta. O envio não será repetido automaticamente.'
  } finally { if (current(version)) submitting.value = false }
}
async function signOut() { logoutError.value = ''; try { await logout() } catch { logoutError.value = 'Não foi possível encerrar a sessão. Tente novamente.' } }
</script>

<template>
  <main class="training">
    <a class="skip-link" href="#training-title">Ir para o conteúdo</a>
    <div class="shell">
      <header class="nav"><RouterLink to="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</RouterLink><nav aria-label="Navegação principal"><RouterLink to="/dashboard">Monitoramento</RouterLink><RouterLink to="/manage">Ambientes e dispositivos</RouterLink><RouterLink to="/messaging">Mensageria</RouterLink><RouterLink to="/laboratory">Laboratório</RouterLink><RouterLink to="/training" aria-current="page">Treinamento</RouterLink></nav><button type="button" @click="signOut">Sair</button></header>
      <p v-if="logoutError" role="alert">{{ logoutError }}</p>
      <section class="heading"><p class="eyebrow">Regressão offline</p><h1 id="training-title" tabindex="-1">Treinamento</h1><p>Compare saúde e vida útil restante com uma baseline e inspecione os erros. Treinar um pacote não o ativa no monitoramento.</p></section>
      <p v-if="!authorized" role="status">O treinamento está disponível apenas para administradores. Visualizadores e operadores não podem iniciar treinamentos nem consultar estes resultados.</p>
      <template v-else>
        <section class="panel" aria-labelledby="training-config-title"><h2 id="training-config-title">Selecionar dataset concluído</h2>
          <p>Lista dos 50 datasets próprios concluídos mais recentes. <RouterLink to="/laboratory">Gerar dados no laboratório</RouterLink>.</p>
          <p v-if="loading" role="status">Consultando datasets…</p><p v-else-if="!datasets.length">Nenhum dataset concluído disponível na lista.</p>
          <form @submit.prevent="train"><label for="training-dataset">Dataset</label><select id="training-dataset" v-model="selected" :disabled="loading || submitting || activeJob || uncertain"><option value="">Selecione um dataset</option><option v-if="selected && !datasets.some((d) => d.id === selected)" :value="selected">Dataset indicado na URL · {{ selected }}</option><option v-for="choice in datasets" :key="choice.id" :value="choice.id">{{ choice.name }} · {{ number(choice.row_count) }} linhas</option></select>
            <p v-if="loadingDataset" role="status">Conferindo configuração do dataset…</p>
            <template v-if="dataset"><p>Dataset: {{ dataset.id }} · {{ number(dataset.row_count) }} linhas · Seed da geração: {{ dataset.config.seed }} · {{ dataset.config.equipment_count }} equipamentos · {{ dataset.config.days }} dias.</p><p>Sensores: {{ sensorChoices.filter(([key]) => dataset!.config.sensor_types.includes(key)).map(([, label]) => label).join('; ') }}.</p><p>RUL observado: {{ number(dataset.quality.rul_observed_rows) }} linhas; censurado: {{ number(dataset.quality.rul_censored_rows) }}. Censurado significa falha não observada, sem duração restante conhecida; essas linhas ficam fora do treino de RUL.</p><details><summary>Configuração do dataset</summary><pre>{{ JSON.stringify(dataset.config, null, 2) }}</pre></details><p v-if="dataset.config.equipment_count < 3" role="alert">O treinamento exige ao menos três equipamentos para separar treino, validação e teste.</p></template>
            <p>Seed do treino: 42. Split por equipamento: aproximadamente 70% treino, 15% validação e restante teste, com seed 42. A seleção usa a validação; os gráficos usam até 500 linhas reservadas do teste.</p><button type="submit" :disabled="blocked">{{ submitting ? 'Enviando…' : 'Iniciar treinamento' }}</button>
          </form>
        </section>
        <p v-if="error" class="feedback" role="alert">{{ error }}</p><button v-if="error" type="button" :disabled="refreshing || loading" @click="route.query.job ? refresh() : loadDatasets()">{{ route.query.job ? 'Atualizar acompanhamento' : 'Consultar datasets novamente' }}</button>
        <section v-if="job" class="panel" aria-labelledby="training-job-title" aria-live="polite"><h2 id="training-job-title">Acompanhamento do treinamento</h2><p class="verdict">{{ labels[job.status] }} · {{ number(job.completed_units) }} / {{ number(job.total_units) }} etapas</p><progress :value="job.completed_units" :max="job.total_units" aria-label="Etapas do treinamento"></progress><p>Job: {{ job.id }} · Dataset: {{ job.dataset_id }}</p><p>Atualizado em <time :datetime="job.updated_at">{{ new Date(job.updated_at).toLocaleString('pt-BR') }}</time>.</p><p v-if="activeJob">Consulta a cada 1,5 segundo. Recarregar esta URL retoma o acompanhamento sem reenviar o pedido. 100% das etapas ainda pode anteceder a conclusão.</p><p v-if="job.status === 'failed' || job.status === 'cancelled'" class="feedback">{{ job.status === 'failed' ? 'O treinamento falhou.' : 'O treinamento foi cancelado.' }} Código: {{ job.error_code ?? 'Não informado' }}. Resultados parciais não são um pacote concluído.</p></section>
        <template v-if="result"><section class="panel" aria-labelledby="training-result-title"><h2 id="training-result-title">Resultado do pacote</h2><p class="verdict">{{ result.eligible ? 'Pacote apto pela validação' : 'Pacote rejeitado: ao menos um alvo não superou os critérios da validação' }}</p><p>Job concluído confirma o fim do processamento. A aptidão de cada modelo é avaliada separadamente; nenhum resultado desta página ativa modelos.</p><dl><div><dt>Versão do pacote</dt><dd>{{ result.model_version }} · {{ result.model_id }}</dd></div><div><dt>Features</dt><dd>{{ result.features_version }}</dd></div><div><dt>Seed / seed do split</dt><dd>{{ result.seed }} / {{ result.split_seed }}</dd></div><div><dt>Equipamentos por partição</dt><dd>Treino {{ result.equipment_counts.train }}, validação {{ result.equipment_counts.validation }}, teste {{ result.equipment_counts.test }}. Equipamentos separados evitam compartilhar a mesma máquina entre treino e avaliação.</dd></div></dl><details><summary>Versões das ferramentas</summary><dl><div v-for="(version, key) in result.versions" :key="key"><dt>{{ key }}</dt><dd>{{ version }}</dd></div></dl></details><h3>Limitações</h3><ul><li v-for="limitation in result.limitations" :key="limitation">{{ limitation }}</li></ul></section><TrainingTarget :result="result.health" /><TrainingTarget :result="result.rul" /></template>
      </template>
    </div>
  </main>
</template>

<style scoped>
.training { min-height: 100vh; background: var(--cs-color-canvas); color: var(--cs-color-ink); padding: var(--cs-space-48); } .shell { max-width: 1280px; margin: auto; display: grid; gap: var(--cs-space-24); min-width: 0; }.nav { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }.brand { font-weight: 700; }.nav nav { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); font-size: var(--cs-type-14); } a, button, summary { color: var(--cs-color-accent); } .nav a, button, summary { display: inline-flex; align-items: center; min-height: 44px; } button, summary { cursor: pointer; } button:disabled { cursor: not-allowed; opacity: .6; } a:hover, button:hover { text-decoration: underline; }.heading h1 { font-size: var(--cs-type-32); font-weight: 600; margin-top: var(--cs-space-8); }.eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: var(--cs-type-12); color: var(--cs-color-ink-muted); }.panel { padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-lg); background: var(--cs-color-surface); min-width: 0; } h2 { font-size: var(--cs-type-20); font-weight: 600; } h3 { font-weight: 600; margin-top: var(--cs-space-16); } p { line-height: 1.7; margin-top: var(--cs-space-12); } form { display: grid; gap: var(--cs-space-12); margin-top: var(--cs-space-16); } label { font-weight: 600; } select { width: 100%; min-height: 44px; border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-sm); padding: var(--cs-space-8); background: var(--cs-color-canvas); } button[type=submit] { justify-self: start; padding: var(--cs-space-8) var(--cs-space-16); border: 1px solid var(--cs-color-accent); border-radius: var(--cs-radius-sm); } progress { width: 100%; accent-color: var(--cs-color-accent); } .verdict { font-weight: 600; } dl div { margin-top: var(--cs-space-12); } dt { font-weight: 600; } dd, p { overflow-wrap: anywhere; } pre { overflow: auto; padding: var(--cs-space-12); font-size: var(--cs-type-12); } ul { padding-left: var(--cs-space-24); list-style: disc; } .feedback { border-left: 3px solid var(--cs-color-status-attention); padding-left: var(--cs-space-12); }.skip-link { position: absolute; transform: translateY(-200%); }.skip-link:focus { transform: none; background: var(--cs-color-surface); padding: var(--cs-space-12); }
@media (max-width: 800px) { .training { padding: var(--cs-space-24); }.nav { gap: var(--cs-space-8); }.nav nav { order: 3; width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }.nav nav a { overflow-wrap: anywhere; min-width: 0; }.panel { padding: var(--cs-space-16); }.heading h1 { font-size: var(--cs-type-24); } }
</style>
