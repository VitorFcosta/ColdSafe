<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearSession, forgetKnownJob, rememberKnownJob, sessionRole, sessionToken } from '../features/account/session'
import { useDraftProtection } from '../features/editing/draft-protection'
import { isUuid } from '../features/monitoring/aiot-api'
import JobResumeLinks from '../features/jobs/JobResumeLinks.vue'
import AreaNavigation from '../features/navigation/AreaNavigation.vue'
import { createGeneration, defaultGeneration, failureChoices, fetchDataset, fetchJob, fetchSample,
  isGenerationInput, LaboratoryAccessError, LaboratoryRequestError, operatingChoices, sensorChoices,
  type Dataset, type DatasetSample, type GenerationInput, type GenerationJob } from '../features/laboratory/laboratory-api'

const route = useRoute()
const router = useRouter()
const config = reactive(defaultGeneration())
const environment = ref('')
const pageTitle = ref<HTMLElement | null>(null)
const generationForm = ref<HTMLFormElement | null>(null)
const validationAttempted = ref(false)
const job = ref<GenerationJob | null>(null)
const dataset = ref<Dataset | null>(null)
const sample = ref<DatasetSample | null>(null)
const error = ref('')
const sampleError = ref('')
const submitting = ref(false)
const uncertainSubmission = ref(false)
const sampling = ref(false)
const refreshing = ref(false)
const denied = ref(false)
const unavailableJob = ref(false)
const authorized = computed(() => Boolean(sessionToken.value) && sessionRole.value === 'admin' && !denied.value)
const hasReference = computed(() => route.query.job !== undefined || route.query.dataset !== undefined)
const unknownJob = computed(() => hasReference.value && !job.value)
const activeJob = computed(() => job.value?.status === 'queued' || job.value?.status === 'running')
const requestConfig = computed(() => ({ ...config, environment_id: environment.value.trim() || null }))
const generationBaseline = ref<GenerationInput>(defaultGeneration())
function generationSignature(value: GenerationInput) {
  return JSON.stringify({ ...value, sensor_types: [...value.sensor_types].sort(),
    failure_modes: [...value.failure_modes].sort(), operating_modes: [...value.operating_modes].sort() })
}
const generationDirty = computed(() => authorized.value && !submitting.value && !activeJob.value &&
  !unknownJob.value && !uncertainSubmission.value && generationSignature(requestConfig.value) !== generationSignature(generationBaseline.value))
function resetGeneration() {
  Object.assign(config, defaultGeneration()); environment.value = ''
  generationBaseline.value = defaultGeneration()
  validationAttempted.value = false
}
useDraftProtection({ dirty: generationDirty, label: 'Parâmetros de geração', discard: resetGeneration })
const number = (value: number) => new Intl.NumberFormat('pt-BR', { maximumSignificantDigits: 15 }).format(value)
const labels = { queued: 'Na fila', running: 'Em execução', completed: 'Concluído', failed: 'Falhou', cancelled: 'Cancelado' }
const progress = computed(() => job.value ? Math.floor(job.value.completed_units / job.value.total_units * 100) : 0)
const essentialFields = [
  { key: 'total_units', label: 'Linhas', min: 1000000, max: 2000000, step: '1', help: 'De 1.000.000 a 2.000.000 linhas no conjunto.' },
  { key: 'equipment_count', label: 'Equipamentos', min: 1, max: 10000, step: '1', help: 'Quantidade de equipamentos simulados.' },
  { key: 'days', label: 'Dias simulados', min: 0, max: 3650, step: 'any', help: 'Duração maior que zero, até 3.650 dias.' },
] as const
const advancedFields = [
  { key: 'seed', label: 'Semente', min: 0, max: 4294967295, step: '1', help: 'Inteiro que permite reproduzir a geração.' },
  { key: 'failure_fraction', label: 'Probabilidade de falha', min: 0, max: 1, step: 'any', help: 'Probabilidade por equipamento; 0,6 equivale a 60% de chance de falha observada.' },
  { key: 'noise_scale', label: 'Escala de ruído', min: 0, max: 10, step: 'any', help: 'Entre 0 e 10; zero desativa o ruído.' },
  { key: 'missing_rate', label: 'Taxa de valores faltantes', min: 0, max: 1, step: 'any', help: 'Entre 0 e 1; 0,01 corresponde a 1% configurado.' },
  { key: 'outlier_rate', label: 'Taxa de valores fora do padrão', min: 0, max: 1, step: 'any', help: 'Entre 0 e 1. Por exemplo, 0,002 equivale a 0,2%.' },
] as const
const fieldErrors = computed(() => {
  const errors: Record<string, string> = {}
  if (!validationAttempted.value) return errors
  for (const field of [...essentialFields, ...advancedFields]) {
    const value = config[field.key]
    if (typeof value !== 'number' || !Number.isFinite(value) || value < field.min || value > field.max ||
      (field.key === 'days' && value === 0) || (field.step === '1' && !Number.isInteger(value))) {
      errors[field.key] = field.key === 'days' ? 'Informe uma duração maior que zero, até 3.650 dias.' :
        `Informe ${field.step === '1' ? 'um inteiro' : 'um valor'} de ${number(field.min)} a ${number(field.max)}.`
    }
  }
  if (environment.value.trim() && !isUuid(environment.value.trim())) errors.environment = 'Informe um UUID válido ou deixe o ambiente vazio.'
  for (const key of ['sensor_types', 'failure_modes', 'operating_modes'] as const) {
    if (!config[key].length) errors[key] = 'Selecione ao menos uma opção neste conjunto.'
  }
  return errors
})
let revision = 0
let timer: ReturnType<typeof setTimeout> | undefined
const requests = new Set<AbortController>()
function resetPrivate() { job.value = null; dataset.value = null; sample.value = null }
function accessError(cause: unknown) {
  if (!(cause instanceof LaboratoryAccessError)) return false
  resetPrivate(); resetGeneration(); denied.value = true
  if (cause.status === 401) clearSession()
  else error.value = 'Acesso ao laboratório indisponível. Consulte outro trabalho conhecido ou entre novamente.'
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
  if (!authorized.value || !token || refreshing.value || typeof id !== 'string' || !isUuid(id) ||
    (route.query.dataset !== undefined && !isUuid(route.query.dataset))) return
  refreshing.value = true
  clearTimeout(timer)
  let confirmed = false
  try {
    const next = await bounded((signal) => fetchJob(token, id, signal))
    if (!current(version)) return
    if (typeof route.query.dataset === 'string' && route.query.dataset !== next.result_id) {
      resetPrivate(); unavailableJob.value = true
      error.value = 'Geração ou dataset indisponível. Confira o endereço ou consulte outro trabalho conhecido.'
      return
    }
    confirmed = true; unavailableJob.value = false
    job.value = next; error.value = ''
    rememberKnownJob(token, 'generation', { jobId: next.id })
    if (next.status === 'completed' && next.result_id && !dataset.value) {
      const summary = await bounded((signal) => fetchDataset(token, next.result_id!, signal))
      if (!current(version)) return
      if (summary.generation_job_id !== next.id || summary.owner_user_id !== next.owner_user_id) throw new Error('Dataset divergente')
      dataset.value = summary
    }
  } catch (cause) {
    if (!current(version)) return
    if (!confirmed && ((cause instanceof LaboratoryAccessError && cause.status === 403) ||
      (cause instanceof LaboratoryRequestError && cause.status === 404))) {
      forgetKnownJob(token, 'generation', id)
      resetPrivate(); resetGeneration(); unavailableJob.value = true
      error.value = 'Geração indisponível. Confira o endereço ou consulte outro trabalho conhecido.'
      return
    }
    if (confirmed && cause instanceof LaboratoryAccessError && cause.status === 403) {
      dataset.value = null; sample.value = null
      error.value = 'O job foi consultado, mas o resultado está indisponível. Você pode repetir a consulta sem gerar novamente.'
      return
    }
    if (accessError(cause)) return
    error.value = 'Não foi possível atualizar o acompanhamento. A situação atual não está confirmada. Você pode repetir a consulta.'
  } finally {
    if (current(version)) refreshing.value = false
    if (current(version) && !unavailableJob.value && (!job.value || activeJob.value)) timer = setTimeout(() => { void refresh() }, 1500)
  }
}
watch([sessionToken, sessionRole, () => route.query.job, () => route.query.dataset], ([token, role, id, datasetId], _previous, onCleanup) => {
  revision += 1
  resetPrivate(); error.value = ''; sampleError.value = ''; submitting.value = false; sampling.value = false; refreshing.value = false
  uncertainSubmission.value = false; denied.value = false; unavailableJob.value = false
  resetGeneration()
  onCleanup(() => { revision += 1; clearTimeout(timer); for (const request of requests) request.abort(); requests.clear() })
  if (!token) { void router.replace('/login'); return }
  if (role !== 'admin') return
  if ((id !== undefined && (typeof id !== 'string' || !isUuid(id))) ||
    (datasetId !== undefined && (typeof datasetId !== 'string' || !isUuid(datasetId)))) {
    unavailableJob.value = true
    error.value = 'Identificador de job ou dataset inválido na URL.'; return
  }
  if (datasetId && !id) {
    unavailableJob.value = true
    error.value = 'Geração indisponível. Informe o job para conferir o dataset associado.'
    return
  }
  if (id) void refresh()
}, { immediate: true, flush: 'sync' })
watch([() => route.query.job, () => route.query.dataset], () => pageTitle.value?.focus(), { flush: 'post' })

async function generate() {
  const token = sessionToken.value
  if (!token || !authorized.value || submitting.value || activeJob.value || unknownJob.value || uncertainSubmission.value) return
  validationAttempted.value = true
  if (!isGenerationInput(requestConfig.value)) {
    error.value = ''
    await nextTick()
    const invalidField = generationForm.value?.querySelector<HTMLElement>('[aria-invalid="true"]')
    const advanced = invalidField?.closest('details')
    if (advanced) advanced.open = true
    invalidField?.focus()
    return
  }
  const version = revision
  const submitted = { ...requestConfig.value, sensor_types: [...config.sensor_types],
    failure_modes: [...config.failure_modes], operating_modes: [...config.operating_modes] }
  submitting.value = true; error.value = ''; sampleError.value = ''; resetPrivate()
  try {
    const created = await bounded((signal) => createGeneration(token, submitted, signal))
    if (!current(version)) return
    generationBaseline.value = submitted
    rememberKnownJob(token, 'generation', { jobId: created.id })
    job.value = created
    await router.replace({ query: { ...route.query, job: created.id } })
  } catch (cause) {
    if (!current(version) || accessError(cause)) return
    if (cause instanceof LaboratoryRequestError && cause.status === 422) {
      error.value = 'A API recusou os parâmetros. Revise os valores e tente novamente.'
      return
    }
    uncertainSubmission.value = true
    error.value = 'Não foi possível confirmar o envio. O job pode ter sido criado; não envie novamente sem conferir os jobs da conta. O envio não será repetido automaticamente. Sem um ID confirmado, este envio não tem retomada garantida; os links de retomada apontam somente para trabalhos confirmados anteriormente.'
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
</script>

<template>
  <main class="laboratory cs-controls">
    <div class="shell">
      <header class="area-heading heading">
        <h1 ref="pageTitle" id="laboratory-title" tabindex="-1">Dados sintéticos</h1>
        <AreaNavigation />
        <p>Gere dados de teste privados e confira sua configuração e qualidade. Eles ficam separados das leituras dos dispositivos.</p>
      </header>
      <p v-if="!authorized" role="status">O laboratório está disponível apenas para administradores. Consulte o monitoramento para ver seus ambientes.</p>
      <template v-else>
        <p v-if="hasReference && error" role="alert" class="feedback error">{{ error }}</p>
        <button v-if="error && route.query.job && !unavailableJob" type="button" class="retry" :disabled="refreshing" @click="refresh">Atualizar acompanhamento</button>
        <p v-if="unknownJob && !error" class="panel" role="status">Consultando a geração…</p>
        <section v-if="dataset" class="panel" aria-labelledby="dataset-title">
          <div class="result-heading">
            <div>
              <h2 id="dataset-title">Dataset concluído</h2>
              <p>{{ number(dataset.row_count) }} linhas sintéticas prontas para treino.</p>
            </div>
            <RouterLink class="training-link" :to="{ path: '/training', query: { dataset: dataset.id } }">Treinar com estes dados</RouterLink>
          </div>
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
          <p>Valores fora do padrão configurados: {{ number(dataset.config.outlier_rate * 100) }}%. Este percentual não é uma contagem medida no conjunto.</p>
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
                    <th v-for="sensor in dataset.config.sensor_types" :key="sensor" scope="col">{{ sensorChoices.find(([key]) => key === sensor)?.[1].replace(/ \([^()]+\)$/, '') }} ({{ dataset.units[sensor] }})</th>
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
          <details class="technical-details">
            <summary>Identificadores e versão do conjunto</summary>
            <dl>
              <div><dt>Dataset</dt><dd>{{ dataset.id }}</dd></div>
              <div><dt>Autor (UUID)</dt><dd>{{ dataset.owner_user_id }}</dd></div>
              <div><dt>Semente:</dt><dd>{{ dataset.config.seed }}</dd></div>
              <div><dt>Versão:</dt><dd>{{ dataset.storage_version }}</dd></div>
            </dl>
          </details>
        </section>
        <section v-if="job" class="panel" aria-labelledby="job-title" :aria-busy="refreshing">
          <h2 id="job-title">Acompanhamento da geração</h2>
          <p class="job-status" role="status">{{ labels[job.status] }} · {{ progress }}% das linhas</p>
          <progress :value="job.completed_units" :max="job.total_units" aria-label="Linhas processadas"></progress>
          <p>{{ number(job.completed_units) }} de {{ number(job.total_units) }} linhas processadas.</p>
          <p v-if="activeJob && progress === 100" role="status">Finalizando a geração. As linhas foram processadas e o conjunto ainda está sendo preparado.</p>
          <p v-else-if="job.status === 'completed' && !dataset && !error" role="status">Consultando o conjunto concluído…</p>
          <p v-if="job.status === 'failed' || job.status === 'cancelled'" class="feedback error">{{ job.status === 'failed' ? 'A geração falhou.' : 'A geração foi cancelada.' }} Resultados parciais não são um dataset concluído. Código: {{ job.error_code ?? 'Não informado' }}.</p>
          <dl>
            <div><dt>Job</dt><dd>{{ job.id }}</dd></div>
            <div><dt>Autor (UUID)</dt><dd>{{ job.owner_user_id }}</dd></div>
            <div><dt>Atualizado em</dt><dd><time :datetime="job.updated_at">{{ new Date(job.updated_at).toLocaleString('pt-BR') }}</time></dd></div>
          </dl>
          <details><summary>Configuração enviada ao gerador</summary><pre>{{ JSON.stringify(job.config, null, 2) }}</pre></details>
          <p v-if="activeJob" class="hint">O progresso é atualizado automaticamente.</p>
        </section>
        <RouterLink
          v-if="(job && !activeJob) || unavailableJob"
          class="new-generation"
          :to="{ path: '/laboratory', query: { ...route.query, job: undefined, dataset: undefined }, hash: route.hash }"
        >Configurar nova geração</RouterLink>
        <form ref="generationForm" v-if="!hasReference" class="generation-layout" novalidate :aria-busy="submitting" @submit.prevent="generate">
          <section class="panel configuration" aria-labelledby="generation-title">
            <h2 id="generation-title">Configuração da geração</h2>
            <p v-if="Object.keys(fieldErrors).length" role="alert" class="feedback error">Revise os parâmetros indicados antes de gerar o dataset.</p>
            <fieldset aria-labelledby="generation-title" :disabled="submitting || uncertainSubmission">
              <div class="fields">
                <div v-for="field in essentialFields" :key="field.key" class="field">
                  <label :for="field.key">{{ field.label }}</label>
                  <input :id="field.key" v-model.number="config[field.key]" :name="field.key" type="number" :min="field.min" :max="field.max" :step="field.step" required :aria-invalid="fieldErrors[field.key] ? true : undefined" :aria-describedby="`${field.key}-help${fieldErrors[field.key] ? ` ${field.key}-error` : ''}`">
                  <small :id="`${field.key}-help`">{{ field.help }}</small>
                  <p v-if="fieldErrors[field.key]" :id="`${field.key}-error`" class="field-error">{{ fieldErrors[field.key] }}</p>
                </div>
              </div>
              <details class="advanced">
                <summary>Opções avançadas</summary>
                <div class="fields">
                  <div v-for="field in advancedFields" :key="field.key" class="field">
                    <label :for="field.key">{{ field.label }}</label>
                    <input :id="field.key" v-model.number="config[field.key]" :name="field.key" type="number" :min="field.min" :max="field.max" :step="field.step" required :aria-invalid="fieldErrors[field.key] ? true : undefined" :aria-describedby="`${field.key}-help${fieldErrors[field.key] ? ` ${field.key}-error` : ''}`">
                    <small :id="`${field.key}-help`">{{ field.help }}</small>
                    <p v-if="fieldErrors[field.key]" :id="`${field.key}-error`" class="field-error">{{ fieldErrors[field.key] }}</p>
                  </div>
                  <div class="field environment-field">
                    <label for="environment">Ambiente (UUID opcional)</label>
                    <input id="environment" v-model="environment" name="environment_id" type="text" spellcheck="false" :aria-invalid="fieldErrors.environment ? true : undefined" :aria-describedby="`environment-help${fieldErrors.environment ? ' environment-error' : ''}`">
                    <small id="environment-help">Vazio gera um dataset privado sem vínculo com um ambiente.</small>
                    <p v-if="fieldErrors.environment" id="environment-error" class="field-error">{{ fieldErrors.environment }}</p>
                  </div>
                </div>
                <fieldset class="choice-group">
                  <legend>Tipos de sensores (selecione ao menos um)</legend>
                  <div class="choices"><label v-for="[key, label] in sensorChoices" :key="key"><input v-model="config.sensor_types" type="checkbox" name="sensor_types" :value="key" :aria-invalid="fieldErrors.sensor_types ? true : undefined" :aria-describedby="fieldErrors.sensor_types ? 'sensor_types-error' : undefined">{{ label }}</label></div>
                  <p v-if="fieldErrors.sensor_types" id="sensor_types-error" class="field-error">{{ fieldErrors.sensor_types }}</p>
                </fieldset>
                <fieldset class="choice-group">
                  <legend>Modos de falha (selecione ao menos um)</legend>
                  <div class="choices"><label v-for="[key, label] in failureChoices" :key="key"><input v-model="config.failure_modes" type="checkbox" name="failure_modes" :value="key" :aria-invalid="fieldErrors.failure_modes ? true : undefined" :aria-describedby="fieldErrors.failure_modes ? 'failure_modes-error' : undefined">{{ label }}</label></div>
                  <p v-if="fieldErrors.failure_modes" id="failure_modes-error" class="field-error">{{ fieldErrors.failure_modes }}</p>
                </fieldset>
                <fieldset class="choice-group">
                  <legend>Modos de operação (selecione ao menos um)</legend>
                  <div class="choices"><label v-for="[key, label] in operatingChoices" :key="key"><input v-model="config.operating_modes" type="checkbox" name="operating_modes" :value="key" :aria-invalid="fieldErrors.operating_modes ? true : undefined" :aria-describedby="fieldErrors.operating_modes ? 'operating_modes-error' : undefined">{{ label }}</label></div>
                  <p v-if="fieldErrors.operating_modes" id="operating_modes-error" class="field-error">{{ fieldErrors.operating_modes }}</p>
                </fieldset>
              </details>
            </fieldset>
          </section>
          <section class="panel execution" aria-labelledby="estimate-title">
            <h2 id="estimate-title">Estimativa e execução</h2>
            <dl class="estimate">
              <div><dt>Linhas</dt><dd>{{ number(config.total_units) }} linhas</dd></div>
              <div><dt>Sensores</dt><dd>{{ number(config.equipment_count * config.sensor_types.length) }} sensores</dd></div>
              <div><dt>Equipamentos</dt><dd>{{ number(config.equipment_count) }}</dd></div>
              <div><dt>Dias simulados</dt><dd>{{ number(config.days) }}</dd></div>
              <div><dt>Espaço aproximado</dt><dd>{{ number(config.total_units / 1000000 * 85) }} MB em NPY</dd></div>
            </dl>
            <p class="hint">Sensores = equipamentos × tipos selecionados. A estimativa de espaço considera o arquivo NPY. Os metadados ocupam espaço adicional.</p>
            <p v-if="error" role="alert" class="feedback error">{{ error }}</p>
            <button class="primary" type="submit" :disabled="submitting || uncertainSubmission">{{ submitting ? 'Enviando…' : 'Gerar dados de teste' }}</button>
          </section>
        </form>
        <JobResumeLinks />
        <section class="panel" aria-labelledby="limits-title">
          <h2 id="limits-title">Limitações da simulação</h2>
          <p>Dados sintéticos, sem calibração industrial. Ruído, valores faltantes ou fora do padrão, degradação e vida útil restante (RUL) vêm do modelo de simulação; não comprovam desempenho em equipamento real. RUL censurada não representa uma falha observada e deve ser excluída da avaliação. Este laboratório não consulta nem grava telemetria ao vivo.</p>
        </section>
      </template>
    </div>
  </main>
</template>

<style scoped>
.laboratory { padding: var(--cs-space-48); }
.shell { max-width: 1280px; margin-inline: auto; min-width: 0; }
.heading { margin-bottom: var(--cs-space-24); }
h2 { font-size: var(--cs-type-20); margin-bottom: var(--cs-space-24); }
h3 { margin-top: var(--cs-space-24); font-weight: 600; }
p { line-height: 1.6; margin-block: var(--cs-space-8); }
.generation-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr); gap: var(--cs-space-24); align-items: start; margin-bottom: var(--cs-space-24); }
.panel { background: var(--cs-color-surface); padding: var(--cs-space-24); border-radius: var(--cs-radius-panel); min-width: 0; margin-bottom: var(--cs-space-24); }
.generation-layout > .panel { margin-bottom: 0; }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); }
.field { display: grid; gap: var(--cs-space-8); align-content: start; min-width: 0; }
.advanced { margin-top: var(--cs-space-16); border-top: 1px solid var(--cs-color-line); }
.advanced[open] > summary { margin-bottom: var(--cs-space-16); }
.technical-details { margin-top: var(--cs-space-16); }
.retry { margin-bottom: var(--cs-space-16); }
.result-heading { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); align-items: center; justify-content: space-between; }
.result-heading h2 { margin-bottom: 0; }
.environment-field { grid-column: 1 / -1; }
label, legend { font-weight: 600; }
small { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); line-height: 1.5; }
fieldset { min-width: 0; }
legend { padding-bottom: var(--cs-space-16); }
.choice-group { margin-top: var(--cs-space-24); padding-top: var(--cs-space-16); border-top: 1px solid var(--cs-color-line); }
.choices { display: flex; flex-wrap: wrap; gap: var(--cs-space-8) var(--cs-space-16); }
.choices label { display: inline-flex; gap: var(--cs-space-8); align-items: center; max-width: 100%; min-height: 44px; font-weight: 400; overflow-wrap: anywhere; }
input[type="checkbox"] { accent-color: var(--cs-color-accent); width: 18px; height: 18px; min-height: 0; flex-shrink: 0; padding: 0; }
fieldset:disabled { color: var(--cs-color-ink-muted); }
.execution button { margin-top: var(--cs-space-16); width: 100%; }
.estimate { margin-top: 0; }
.estimate div { justify-content: space-between; padding-block: var(--cs-space-12); border-bottom: 1px solid var(--cs-color-line); }
.estimate dt { color: var(--cs-color-ink-muted); font-weight: 400; }.estimate dd { font-weight: 600; }
.job-status { font-weight: 600; color: var(--cs-color-accent); }
progress {
  appearance: none;
  display: block;
  width: 100%;
  height: var(--cs-space-8);
  overflow: hidden;
  border: 0;
  border-radius: var(--cs-radius-8);
  background: var(--cs-color-surface-muted);
}
progress::-webkit-progress-bar { background: var(--cs-color-surface-muted); }
progress::-webkit-progress-value { background: var(--cs-color-accent); }
progress::-moz-progress-bar { background: var(--cs-color-accent); }
dl { margin-block: var(--cs-space-16); }
dl div { display: flex; flex-wrap: wrap; gap: var(--cs-space-8); } dt { font-weight: 600; } dd { overflow-wrap: anywhere; min-width: 0; }
summary { min-height: 44px; display: list-item; align-content: center; cursor: pointer; color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
.training-link, .new-generation { display: inline-flex; align-items: center; min-height: 44px; color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
.training-link { padding: var(--cs-space-8) var(--cs-space-16); border: 1px solid currentColor; border-radius: var(--cs-radius-8); font-weight: 600; }
.new-generation { margin-top: calc(-1 * var(--cs-space-16)); }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: var(--cs-type-14); padding: var(--cs-space-16); background: var(--cs-color-canvas); }
.table-scroll { overflow-x: auto; max-width: 100%; margin-block: var(--cs-space-16); }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: var(--cs-type-14); }
caption { text-align: left; padding-bottom: var(--cs-space-8); }
th, td { padding: var(--cs-space-16); border-bottom: 1px solid var(--cs-color-line); white-space: nowrap; } th { font-weight: 600; }
@media (max-width: 1100px) {
  .laboratory { padding: var(--cs-space-16); }
  .generation-layout { grid-template-columns: minmax(0, 1fr); }
  .panel { padding: var(--cs-space-16); }
}
@media (max-width: 600px) { .fields { grid-template-columns: minmax(0, 1fr); } }
</style>
