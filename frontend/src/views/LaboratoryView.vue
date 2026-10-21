<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearSession, logout, refreshSessionIdentity, sessionRole, sessionToken } from '../features/account/session'
import { isUuid } from '../features/monitoring/aiot-api'
import LlmStatus from '../features/llm/LlmStatus.vue'
import { createGeneration, defaultGeneration, failureChoices, fetchDataset, fetchJob, fetchSample,
  isGenerationInput, LaboratoryAccessError, LaboratoryRequestError, operatingChoices, sensorChoices,
  type Dataset, type DatasetSample, type GenerationJob } from '../features/laboratory/laboratory-api'

const route = useRoute()
const router = useRouter()
const config = reactive(defaultGeneration())
const environment = ref('')
const job = ref<GenerationJob | null>(null)
const dataset = ref<Dataset | null>(null)
const sample = ref<DatasetSample | null>(null)
const error = ref('')
const sampleError = ref('')
const logoutError = ref('')
const submitting = ref(false)
const uncertainSubmission = ref(false)
const sampling = ref(false)
const refreshing = ref(false)
const denied = ref(false)
const authorized = computed(() => Boolean(sessionToken.value) && sessionRole.value === 'admin' && !denied.value)
const unknownJob = computed(() => route.query.job !== undefined && !job.value)
const activeJob = computed(() => job.value?.status === 'queued' || job.value?.status === 'running')
const requestConfig = computed(() => ({ ...config, environment_id: environment.value.trim() || null }))
const number = (value: number) => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 }).format(value)
const labels = { queued: 'Na fila', running: 'Em execução', completed: 'Concluído', failed: 'Falhou', cancelled: 'Cancelado' }
const progress = computed(() => job.value ? Math.floor(job.value.completed_units / job.value.total_units * 100) : 0)
const numericFields = [
  { key: 'total_units', label: 'Linhas', min: 1000000, max: 2000000, step: '1', help: 'De 1.000.000 a 2.000.000; total de linhas do dataset.' },
  { key: 'seed', label: 'Seed', min: 0, max: 4294967295, step: '1', help: 'Inteiro que permite reproduzir a geração.' },
  { key: 'equipment_count', label: 'Equipamentos', min: 1, max: 10000, step: '1', help: 'Quantidade de equipamentos simulados.' },
  { key: 'days', label: 'Dias simulados', min: 0.000001, max: 3650, step: 'any', help: 'Duração maior que zero, até 3.650 dias.' },
  { key: 'failure_fraction', label: 'Fração com falha', min: 0, max: 1, step: 'any', help: 'Probabilidade por equipamento; 0,6 equivale a 60% de chance de falha observada.' },
  { key: 'noise_scale', label: 'Escala de ruído', min: 0, max: 10, step: 'any', help: 'Entre 0 e 10; zero desativa o ruído.' },
  { key: 'missing_rate', label: 'Taxa de faltantes', min: 0, max: 1, step: 'any', help: 'Entre 0 e 1; 0,01 corresponde a 1% configurado.' },
  { key: 'outlier_rate', label: 'Taxa de outliers', min: 0, max: 1, step: 'any', help: 'Entre 0 e 1; taxa configurada, não contagem detectada.' },
] as const
let revision = 0
let timer: ReturnType<typeof setTimeout> | undefined
const requests = new Set<AbortController>()
function resetPrivate() { job.value = null; dataset.value = null; sample.value = null }
function accessError(cause: unknown) {
  if (!(cause instanceof LaboratoryAccessError)) return false
  resetPrivate(); denied.value = true
  if (cause.status === 401) clearSession()
  else void refreshSessionIdentity().catch(() => { /* Permissions remain unknown and private data hidden. */ })
  return true
}
async function bounded<T>(operation: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController()
  requests.add(controller)
  const deadline = setTimeout(() => controller.abort(), 8000)
  try { return await operation(controller.signal) }
  finally { clearTimeout(deadline); requests.delete(controller) }
}
function current(version: number) { return version === revision && authorized.value }
async function refresh() {
  const token = sessionToken.value
  const id = route.query.job
  const version = revision
  if (!authorized.value || !token || refreshing.value || typeof id !== 'string' || !isUuid(id)) return
  refreshing.value = true
  clearTimeout(timer)
  try {
    const next = await bounded((signal) => fetchJob(token, id, signal))
    if (!current(version)) return
    job.value = next; error.value = ''
    if (next.status === 'completed' && next.result_id && !dataset.value) {
      const summary = await bounded((signal) => fetchDataset(token, next.result_id!, signal))
      if (!current(version)) return
      if (summary.generation_job_id !== next.id || summary.owner_user_id !== next.owner_user_id) throw new Error('Dataset divergente')
      dataset.value = summary
    }
  } catch (cause) {
    if (!current(version) || accessError(cause)) return
    error.value = 'Não foi possível atualizar o acompanhamento. A situação atual não está confirmada. Você pode repetir a consulta.'
  } finally {
    if (current(version)) refreshing.value = false
    if (current(version) && (!job.value || activeJob.value)) timer = setTimeout(() => { void refresh() }, 1500)
  }
}
watch([sessionToken, sessionRole, () => route.query.job], ([token, role, id], _previous, onCleanup) => {
  revision += 1
  resetPrivate(); error.value = ''; sampleError.value = ''; submitting.value = false; sampling.value = false; refreshing.value = false
  uncertainSubmission.value = false; denied.value = false
  Object.assign(config, defaultGeneration()); environment.value = ''
  onCleanup(() => { revision += 1; clearTimeout(timer); for (const request of requests) request.abort(); requests.clear() })
  if (!token) { void router.replace('/login'); return }
  if (role !== 'admin') return
  if (id !== undefined && (typeof id !== 'string' || !isUuid(id))) {
    error.value = 'Identificador de job inválido na URL.'; return
  }
  if (id) void refresh()
}, { immediate: true, flush: 'sync' })
async function generate() {
  const token = sessionToken.value
  if (!token || !authorized.value || submitting.value || activeJob.value || unknownJob.value || uncertainSubmission.value) return
  if (!isGenerationInput(requestConfig.value)) { error.value = 'Revise os parâmetros: limites, seed inteira, UUID do ambiente e ao menos uma opção em cada lista.'; return }
  const version = revision
  submitting.value = true; error.value = ''; sampleError.value = ''; resetPrivate()
  try {
    const created = await bounded((signal) => createGeneration(token, requestConfig.value, signal))
    if (!current(version)) return
    job.value = created
    await router.replace({ query: { ...route.query, job: created.id } })
  } catch (cause) {
    if (!current(version) || accessError(cause)) return
    if (cause instanceof LaboratoryRequestError && cause.status === 422) {
      error.value = 'A API recusou os parâmetros. Revise os valores e tente novamente.'
      return
    }
    uncertainSubmission.value = true
    error.value = 'Não foi possível confirmar o envio. O job pode ter sido criado; não envie novamente sem conferir os jobs da conta. O envio não será repetido automaticamente.'
  } finally { if (current(version)) submitting.value = false }
}
async function loadSample() {
  const token = sessionToken.value
  const summary = dataset.value
  if (!token || !authorized.value || !summary || sampling.value) return
  const version = revision
  sampling.value = true; sampleError.value = ''
  try {
    const next = await bounded((signal) => fetchSample(token, summary.id, signal))
    if (!current(version)) return
    if (next.rows.some((row) => Object.keys(row.measurements).length !== summary.config.sensor_types.length ||
      summary.config.sensor_types.some((key) => !Object.hasOwn(row.measurements, key)))) throw new Error('Sensores divergentes')
    sample.value = next
  } catch (cause) {
    if (current(version) && !accessError(cause)) sampleError.value = 'Não foi possível consultar a amostra. Tente novamente.'
  } finally { if (current(version)) sampling.value = false }
}
async function signOut() {
  logoutError.value = ''
  try { await logout() } catch { logoutError.value = 'Não foi possível encerrar a sessão. Tente novamente.' }
}
</script>

<template>
  <main class="laboratory">
    <a class="skip-link" href="#laboratory-title">Ir para o conteúdo</a>
    <div class="shell">
      <header class="nav">
        <RouterLink to="/" class="brand">◉ ColdSafe</RouterLink>
        <nav aria-label="Navegação principal">
          <RouterLink to="/dashboard">Monitoramento</RouterLink>
          <RouterLink to="/insights">Insights</RouterLink><RouterLink to="/digital-twin">Gêmeo digital</RouterLink>
          <RouterLink to="/manage">Ambientes e dispositivos</RouterLink>
          <RouterLink to="/messaging">Mensageria</RouterLink>
          <RouterLink to="/laboratory" aria-current="page">Laboratório</RouterLink>
          <RouterLink to="/training">Treinamento</RouterLink>
        </nav>
        <button type="button" class="sign-out" @click="signOut">Sair</button>
      </header>
      <p v-if="logoutError" role="alert">{{ logoutError }}</p>
      <section class="heading" aria-labelledby="laboratory-title">
        <p class="eyebrow">Simulação offline</p>
        <h1 id="laboratory-title" tabindex="-1">Laboratório de Dados</h1>
        <p>Gere dados sintéticos privados e acompanhe sua configuração e qualidade. Os dados deste laboratório ficam separados da telemetria ao vivo.</p>
      </section>
      <p v-if="!authorized" role="status">O laboratório está disponível apenas para administradores. Consulte o monitoramento para ver seus ambientes.</p>
      <template v-else>
        <LlmStatus />
        <section class="panel" aria-labelledby="generation-title">
          <h2 id="generation-title">Gerar dataset</h2>
          <form novalidate @submit.prevent="generate">
            <fieldset :disabled="submitting || activeJob || unknownJob || uncertainSubmission">
              <legend>Parâmetros de geração</legend>
              <div class="fields">
                <div v-for="field in numericFields" :key="field.key" class="field">
                  <label :for="field.key">{{ field.label }}</label>
                  <input :id="field.key" v-model.number="config[field.key]" :name="field.key" type="number" :min="field.min" :max="field.max" :step="field.step" required :aria-describedby="`${field.key}-help`">
                  <small :id="`${field.key}-help`">{{ field.help }}</small>
                </div>
                <div class="field"><label for="environment">Ambiente (UUID opcional)</label><input id="environment" v-model="environment" name="environment_id" type="text" spellcheck="false" aria-describedby="environment-help"><small id="environment-help">Vazio gera um dataset privado sem vínculo com um ambiente.</small></div>
              </div>
              <fieldset>
                <legend>Tipos de sensores (selecione ao menos um)</legend>
                <div class="choices"><label v-for="[key, label] in sensorChoices" :key="key"><input v-model="config.sensor_types" type="checkbox" name="sensor_types" :value="key">{{ label }}</label></div>
              </fieldset>
              <fieldset>
                <legend>Modos de falha (selecione ao menos um)</legend>
                <div class="choices"><label v-for="[key, label] in failureChoices" :key="key"><input v-model="config.failure_modes" type="checkbox" name="failure_modes" :value="key">{{ label }}</label></div>
              </fieldset>
              <fieldset>
                <legend>Modos de operação (selecione ao menos um)</legend>
                <div class="choices"><label v-for="[key, label] in operatingChoices" :key="key"><input v-model="config.operating_modes" type="checkbox" name="operating_modes" :value="key">{{ label }}</label></div>
              </fieldset>
            </fieldset>
            <p class="estimate" aria-live="polite">Estimativa: {{ number(config.total_units) }} linhas · {{ number(config.equipment_count * config.sensor_types.length) }} sensores (equipamentos × tipos) · aproximadamente {{ number(config.total_units / 1000000 * 85) }} MB em NPY. O formato fixo reserva colunas para os seis tipos, mesmo com menos tipos selecionados; metadados acrescentam espaço.</p>
            <button type="submit" :disabled="submitting || activeJob || unknownJob || uncertainSubmission">{{ submitting ? 'Enviando…' : 'Gerar dataset' }}</button>
          </form>
        </section>
        <p v-if="error" role="alert" class="feedback">{{ error }}</p>
        <button v-if="error && route.query.job" type="button" :disabled="refreshing" @click="refresh">Atualizar acompanhamento</button>
        <section v-if="job" class="panel" aria-labelledby="job-title" aria-live="polite">
          <h2 id="job-title">Acompanhamento da geração</h2>
          <p class="job-status">{{ labels[job.status] }} · {{ progress }}% das unidades</p>
          <progress :value="job.completed_units" :max="job.total_units" aria-label="Linhas processadas"></progress>
          <p>{{ number(job.completed_units) }} / {{ number(job.total_units) }} linhas processadas. Somente o estado Concluído confirma o dataset; 100% das unidades pode anteceder a finalização.</p>
          <dl>
            <div><dt>Job</dt><dd>{{ job.id }}</dd></div>
            <div><dt>Autor (UUID)</dt><dd>{{ job.owner_user_id }}</dd></div>
            <div><dt>Seed: {{ job.config.seed }}</dt><dd>Configuração enviada abaixo, preservada no job.</dd></div>
            <div><dt>Atualizado em</dt><dd><time :datetime="job.updated_at">{{ new Date(job.updated_at).toLocaleString('pt-BR') }}</time></dd></div>
          </dl>
          <details><summary>Configuração enviada ao gerador</summary><pre>{{ JSON.stringify(job.config, null, 2) }}</pre></details>
          <p v-if="job.status === 'failed' || job.status === 'cancelled'" class="feedback">{{ job.status === 'failed' ? 'A geração falhou.' : 'A geração foi cancelada.' }} Resultados parciais não são um dataset concluído. Código: {{ job.error_code ?? 'Não informado' }}.</p>
          <p v-if="activeJob">Consulta autenticada a cada 1,5 segundo. Recarregar esta URL retoma o acompanhamento sem reenviar o pedido.</p>
        </section>
        <section v-if="dataset" class="panel" aria-labelledby="dataset-title">
          <h2 id="dataset-title">Dataset concluído</h2>
          <RouterLink :to="{ path: '/training', query: { dataset: dataset.id } }">Treinar modelos com este dataset</RouterLink>
          <p>{{ number(dataset.row_count) }} linhas · Seed: {{ dataset.config.seed }} · {{ dataset.storage_version }}</p>
          <dl>
            <div><dt>Dataset</dt><dd>{{ dataset.id }}</dd></div>
            <div><dt>Autor (UUID)</dt><dd>{{ dataset.owner_user_id }}</dd></div>
          </dl>
          <div class="table-scroll" tabindex="0" role="region" aria-label="Qualidade dos sensores; role horizontalmente para ver todas as colunas">
            <table>
              <caption>Qualidade medida no dataset completo</caption>
              <thead>
                <tr>
                  <th scope="col">Sensor</th><th scope="col">Faltantes</th>
                  <th scope="col">Mínimo</th><th scope="col">Máximo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sensor in dataset.config.sensor_types" :key="sensor">
                  <th scope="row">{{ sensorChoices.find(([key]) => key === sensor)?.[1] }}</th>
                  <td>{{ number(dataset.quality.missing_by_sensor[sensor]!) }}</td>
                  <td>{{ dataset.quality.range_by_sensor[sensor]!.min ?? 'Sem valor' }} {{ dataset.units[sensor] }}</td>
                  <td>{{ dataset.quality.range_by_sensor[sensor]!.max ?? 'Sem valor' }} {{ dataset.units[sensor] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p>RUL observada: {{ number(dataset.quality.rul_observed_rows) }} linhas. RUL censurada: {{ number(dataset.quality.rul_censored_rows) }} linhas; excluída da avaliação de RUL.</p>
          <p>Taxa de outliers configurada: {{ number(dataset.config.outlier_rate * 100) }}%. Este valor não é uma contagem de outliers detectados.</p>
          <button data-testid="sample-button" type="button" :disabled="sampling" @click="loadSample">{{ sampling ? 'Consultando amostra…' : 'Ver amostra' }}</button>
          <p v-if="sampleError" role="alert">{{ sampleError }}</p>
          <section v-if="sample" aria-labelledby="sample-title">
            <h3 id="sample-title">Amostra sintética separada</h3>
            <p>Até 10 linhas, seleção determinística e não representativa da distribuição completa. Valores nulos indicam faltantes.</p>
            <p v-if="!sample.rows.length">Nenhuma linha na amostra recebida.</p>
            <div v-else class="table-scroll" tabindex="0" role="region" aria-label="Amostra do dataset sintético">
              <table>
                <caption>Linhas sintéticas e rótulos de referência</caption>
                <thead>
                  <tr>
                    <th scope="col">Equipamento</th><th scope="col">Instante</th>
                    <th v-for="sensor in dataset.config.sensor_types" :key="sensor" scope="col">{{ sensor }} ({{ dataset.units[sensor] }})</th>
                    <th scope="col">Degradação (0–1)</th><th scope="col">Saúde (0–100)</th>
                    <th scope="col">RUL (h)</th><th scope="col">RUL observada</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in sample.rows" :key="index">
                    <th scope="row">{{ row.equipment_id }}</th><td>{{ row.observed_at }}</td>
                    <td v-for="sensor in dataset.config.sensor_types" :key="sensor">{{ row.measurements[sensor] ?? 'Faltante' }}</td>
                    <td>{{ row.degradation_true }}</td><td>{{ row.health_score_true }}</td>
                    <td>{{ row.rul_hours_true ?? 'Não observada' }}</td>
                    <td>{{ row.rul_observed ? 'Sim' : 'Não (censurada)' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </section>
        <section class="panel" aria-labelledby="limits-title">
          <h2 id="limits-title">Limitações da simulação</h2>
          <p>Dados sintéticos, sem calibração industrial. Ruído, faltantes, outliers, degradação e RUL são produzidos pelo modelo de simulação; não comprovam desempenho em equipamento real. RUL censurada não representa uma falha observada e deve ser excluída da avaliação. Este laboratório não consulta nem grava telemetria ao vivo.</p>
        </section>
      </template>
    </div>
  </main>
</template>

<style scoped>
.laboratory { min-height: 100vh; background: var(--cs-color-canvas); color: var(--cs-color-ink); padding: var(--cs-space-48); }
.shell { max-width: 1280px; margin: 0 auto; min-width: 0; }
.nav { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.brand { font-size: var(--cs-type-20); font-weight: 700; }
.nav nav { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); font-size: var(--cs-type-14); }
.nav a, button, summary { min-height: 44px; display: inline-flex; align-items: center; }
.nav a:hover, button:hover { text-decoration: underline; }
.heading { padding-block: var(--cs-space-32); }
.eyebrow { color: var(--cs-color-ink-muted); text-transform: uppercase; font-size: var(--cs-type-12); letter-spacing: .08em; }
h1 { font-size: var(--cs-type-32); font-weight: 700; margin-block: var(--cs-space-8); }
h2 { font-size: var(--cs-type-20); font-weight: 600; margin-bottom: var(--cs-space-16); }
h3 { margin-top: var(--cs-space-24); font-weight: 600; }
.panel { border: 1px solid var(--cs-color-line); background: var(--cs-color-surface); padding: var(--cs-space-24); border-radius: var(--cs-radius-panel); min-width: 0; margin-bottom: var(--cs-space-24); }
p { line-height: 1.6; margin-block: var(--cs-space-8); }
.fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cs-space-24); }
.field { display: grid; gap: var(--cs-space-8); align-content: start; min-width: 0; }
label, legend { font-weight: 600; }
input[type="number"], input[type="text"] { width: 100%; min-width: 0; min-height: 44px; border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-4); padding: var(--cs-space-8); background: var(--cs-color-canvas); }
small { color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); }
fieldset { min-width: 0; margin-bottom: var(--cs-space-24); }
legend { padding-bottom: var(--cs-space-16); }
.choices { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); }
.choices label { display: inline-flex; gap: var(--cs-space-8); align-items: center; min-height: 44px; font-weight: 400; }
input[type="checkbox"] { accent-color: var(--cs-color-accent); width: 18px; height: 18px; }
button { border: 1px solid var(--cs-color-line); padding: var(--cs-space-8) var(--cs-space-16); border-radius: var(--cs-radius-4); cursor: pointer; color: var(--cs-color-accent); font-weight: 600; }
button:disabled, fieldset:disabled { opacity: .65; cursor: default; }
.estimate { padding-block: var(--cs-space-16); }
.feedback { color: var(--cs-color-status-critical); margin-block: var(--cs-space-16); }
.job-status { font-weight: 600; }
progress { display: block; width: 100%; accent-color: var(--cs-color-accent); }
dl { margin-block: var(--cs-space-16); }
dl div { display: flex; flex-wrap: wrap; gap: var(--cs-space-8); } dt { font-weight: 600; } dd { overflow-wrap: anywhere; min-width: 0; }
summary { cursor: pointer; text-decoration: underline; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: var(--cs-type-14); padding: var(--cs-space-16); background: var(--cs-color-canvas); }
.table-scroll { overflow-x: auto; max-width: 100%; margin-block: var(--cs-space-16); }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: var(--cs-type-14); }
caption { text-align: left; padding-bottom: var(--cs-space-8); }
th, td { padding: var(--cs-space-16); border-bottom: 1px solid var(--cs-color-line); white-space: nowrap; } th { font-weight: 600; }
@media (max-width: 800px) { .laboratory { padding: var(--cs-space-24); } .fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } .nav { gap: var(--cs-space-8); } .nav nav { order: 3; width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } .nav nav a { overflow-wrap: anywhere; min-width: 0; } .panel { padding: var(--cs-space-16); } h1 { font-size: var(--cs-type-24); } }
@media (max-width: 480px) { .fields { grid-template-columns: minmax(0, 1fr); } }
</style>
