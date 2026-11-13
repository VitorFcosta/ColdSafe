<script setup lang="ts">
import LiveDataRegion from '../features/monitoring/LiveDataRegion.vue'
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useMonitoringContext } from '../features/monitoring/use-monitoring-context'
import { canWrite, clearSession, refreshSessionIdentity, sessionToken } from '../features/account/session'
import { fetchInsights, InsightsAccessError, parsePredictiveRules, savePredictiveRules, type InsightsSnapshot, type PredictiveRules } from '../features/insights/insights-api'
import { STALE_AFTER_SECONDS } from '../features/monitoring/monitoring-state'
import { useDraftProtection } from '../features/editing/draft-protection'
import AreaNavigation from '../features/navigation/AreaNavigation.vue'
import MonitoringEmptyState from '../features/monitoring/MonitoringEmptyState.vue'
import { formatFreshness } from '../features/monitoring/use-monitoring-summary'
import { formatReadingTime } from '../features/monitoring/temperature-chart'

const { environments, devices, environmentId, deviceUuid, selectedDevice,
  selectionNotice, catalogLoading, catalogFailed, loadEnvironments, revokeSelection } = useMonitoringContext()
const snapshot = ref<InsightsSnapshot | null>(null)
const failed = ref(false)
const denied = ref(false)
const loading = ref(false)
const draft = ref<PredictiveRules | null>(null)
const baseline = ref<PredictiveRules | null>(null)
const dirty = computed(() => Boolean(draft.value && baseline.value && JSON.stringify(draft.value) !== JSON.stringify(baseline.value)))
const saving = ref(false)
const saveNotice = ref('')
const validationAttempted = ref(false)
const editingRules = ref(false)
const editRulesButton = ref<HTMLButtonElement | null>(null)
const rulesForm = ref<HTMLFormElement | null>(null)
const draftGuard = useDraftProtection({
  dirty: computed(() => canWrite.value && dirty.value && !saving.value),
  label: computed(() => `Regras preditivas de ${selectedDevice.value?.name ?? 'equipamento selecionado'}`),
  discard: () => { draft.value = baseline.value ? { ...baseline.value } : null },
})

function changeScope(event: Event, target: 'environment' | 'device') {
  const control = event.target as HTMLSelectElement
  const id = control.value
  control.value = target === 'environment' ? environmentId.value : deviceUuid.value
  void draftGuard.request(() => {
    if (target === 'environment') environmentId.value = id
    else deviceUuid.value = id
  })
}
const now = ref(Date.now())
const fetchedAt = ref(Date.now())
let selectionRevision = 0
let rulesRevision = 0
let saveController: AbortController | null = null
const ageSeconds = computed(() => {
  const value = snapshot.value
  if (value?.age_seconds == null) return null
  const elapsed = Math.max(0, now.value - fetchedAt.value) / 1000
  const inputAge = value.prediction ? (now.value - Date.parse(value.prediction.data.input_received_at)) / 1000 : 0
  return Math.floor(Math.max(value.age_seconds + elapsed, inputAge, 0))
})
const stale = computed(() => snapshot.value?.availability === 'stale' || (ageSeconds.value !== null && ageSeconds.value > STALE_AFTER_SECONDS))
const available = computed(() => !failed.value && !denied.value && !stale.value && snapshot.value?.availability === 'available')
const statusMessage = computed(() => {
  if (denied.value) return 'Acesso ao equipamento indisponível. Selecione outro equipamento ou entre novamente.'
  if (failed.value) return 'Consulta indisponível'
  if (stale.value) return 'Previsão desatualizada. Aguardando uma leitura recente.'
  if (available.value) return 'Previsão disponível'
  if (snapshot.value?.availability === 'unavailable') return 'Previsão indisponível'
  return loading.value ? 'Consultando previsão…' : 'Sem previsão para este equipamento.'
})
const trendLabels = { improving: 'Em recuperação', declining: 'Em queda', stable: 'Estável' }
const reasonLabels = {
  no_model: 'Nenhum modelo ativo.', insufficient_history: 'Histórico insuficiente. Aguardando mais leituras para calcular a previsão.', invalid_features: 'Não foi possível calcular a previsão com estas leituras.',
  model_unavailable: 'Não foi possível executar o modelo ativo.', stale_input: 'Leitura desatualizada.',
}
const ruleFields: { key: keyof PredictiveRules; label: string; min: number; max?: number; step: string }[] = [
  { key: 'health_critical', label: 'Saúde crítica', min: 0, max: 100, step: 'any' },
  { key: 'health_recovery', label: 'Saúde de recuperação', min: 0, max: 100, step: 'any' },
  { key: 'rul_critical_hours', label: 'Limite crítico (h)', min: 0, step: 'any' },
  { key: 'rul_recovery_hours', label: 'Limite de recuperação (h)', min: 0, step: 'any' },
  { key: 'open_count', label: 'Previsões para abrir', min: 1, max: 100, step: '1' },
  { key: 'close_count', label: 'Previsões para encerrar', min: 1, max: 100, step: '1' },
]
const ruleGroups = [
  { label: 'Saúde estimada (/100)', fields: ruleFields.slice(0, 2) },
  { label: 'Vida útil restante (h)', fields: ruleFields.slice(2, 4) },
  { label: 'Persistência do alerta', fields: ruleFields.slice(4) },
]
const ruleErrors = computed(() => {
  const errors: Partial<Record<keyof PredictiveRules, string>> = {}
  const rules = draft.value
  if (!validationAttempted.value || !rules) return errors
  for (const field of ruleFields) {
    const value = rules[field.key]
    if (typeof value !== 'number' || !Number.isFinite(value)) errors[field.key] = 'Informe um número válido.'
    else if (field.step === '1' && !Number.isInteger(value)) errors[field.key] = 'Informe um número inteiro entre 1 e 100.'
    else if (value < field.min || (field.max !== undefined && value > field.max)) {
      errors[field.key] = field.max === undefined ? `Informe um valor maior ou igual a ${field.min}.` : `Informe um valor entre ${field.min} e ${field.max}.`
    }
  }
  if (!errors.health_critical && !errors.health_recovery && rules.health_recovery <= rules.health_critical) errors.health_recovery = 'A saúde de recuperação deve superar a saúde crítica.'
  if (!errors.rul_critical_hours && !errors.rul_recovery_hours && rules.rul_recovery_hours <= rules.rul_critical_hours) errors.rul_recovery_hours = 'O limite de recuperação deve superar o limite crítico.'
  return errors
})
async function startEditingRules() {
  editingRules.value = true
  saveNotice.value = ''
  await nextTick()
  rulesForm.value?.querySelector('input')?.focus()
}
async function finishEditingRules() {
  editingRules.value = false
  await nextTick()
  editRulesButton.value?.focus()
}
function cancelRules() {
  if (saving.value || !snapshot.value) return
  saveNotice.value = dirty.value ? 'Alterações descartadas.' : ''
  baseline.value = { ...snapshot.value.rules }
  draft.value = { ...baseline.value }
  validationAttempted.value = false
  void finishEditingRules()
}
const clock = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => { selectionRevision += 1; clearInterval(clock); saveController?.abort() })

function revokeAccess(error: InsightsAccessError) {
  snapshot.value = null
  baseline.value = null
  draft.value = null
  denied.value = true
  if (error.status === 401) clearSession()
  else void revokeSelection().then(() => refreshSessionIdentity()).catch(() => { /* Unknown permissions remain read-only. */ })
}

watch([sessionToken, selectedDevice], ([token, device], _old, onCleanup) => {
  selectionRevision += 1
  saveController?.abort()
  snapshot.value = null
  draft.value = null
  baseline.value = null
  failed.value = false
  denied.value = false
  loading.value = false
  saving.value = false
  saveNotice.value = ''
  validationAttempted.value = false
  editingRules.value = false
  if (!token || !device) return
  let active = true
  let pending = false
  let controller: AbortController | null = null
  let deadline: ReturnType<typeof setTimeout> | undefined
  async function refresh() {
    if (!active || pending || denied.value) return
    pending = true
    loading.value = true
    controller = new AbortController()
    const revision = rulesRevision
    deadline = setTimeout(() => controller?.abort(), 8000)
    try {
      const result = await fetchInsights(token!, device!, controller.signal)
      if (!active || revision !== rulesRevision) return
      snapshot.value = result
      failed.value = false
      fetchedAt.value = Date.now()
      now.value = Date.now()
      if (!dirty.value) { baseline.value = { ...result.rules }; draft.value = { ...result.rules } }
    } catch (error) {
      if (!active) return
      failed.value = true
      if (error instanceof InsightsAccessError) revokeAccess(error)
    } finally {
      clearTimeout(deadline)
      pending = false
      if (active) loading.value = false
    }
  }
  const poll = setInterval(() => { void refresh() }, 2000)
  onCleanup(() => { active = false; clearInterval(poll); clearTimeout(deadline); controller?.abort() })
  void refresh()
}, { immediate: true, flush: 'sync' })

async function saveRules() {
  const token = sessionToken.value
  const device = selectedDevice.value
  if (!canWrite.value || !token || !device || saving.value || denied.value) return
  const rules = parsePredictiveRules(draft.value)
  saveNotice.value = ''
  if (!rules) {
    validationAttempted.value = true
    saveNotice.value = 'Regras inválidas. Confira os campos indicados.'
    await nextTick()
    const first = ruleFields.find((field) => ruleErrors.value[field.key])
    if (first) rulesForm.value?.querySelector<HTMLInputElement>(`[name="${first.key}"]`)?.focus()
    return
  }
  validationAttempted.value = false
  const revision = selectionRevision
  saveController = new AbortController()
  const deadline = setTimeout(() => saveController?.abort(), 8000)
  saving.value = true
  try {
    const saved = await savePredictiveRules(token, device, rules, saveController.signal)
    if (revision !== selectionRevision || !canWrite.value) return
    rulesRevision += 1
    draft.value = { ...saved }
    if (snapshot.value) snapshot.value = { ...snapshot.value, rules: saved }
    baseline.value = { ...saved }
    saveNotice.value = 'Regras salvas.'
    void finishEditingRules()
  } catch (error) {
    if (revision !== selectionRevision) return
    saveNotice.value = 'Não foi possível salvar as regras. Confira o acesso e tente novamente.'
    if (error instanceof InsightsAccessError) revokeAccess(error)
  } finally {
    clearTimeout(deadline)
    if (revision === selectionRevision) saving.value = false
  }
}

const format = (value: number | null | undefined) => value?.toLocaleString('pt-BR', { maximumFractionDigits: 2 }) ?? '—'
const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const formatTime = (value: string) => formatReadingTime(value, timeZone)
const inputAgeLabel = computed(() => ageSeconds.value === null ? 'Sem leitura confirmada' : formatFreshness(ageSeconds.value))
</script>

<template>
  <main class="insights">
    <div class="shell">
      <header class="area-heading heading">
        <h1 id="insights-title" tabindex="-1">Saúde e previsões</h1>
        <AreaNavigation />
      </header>
      <section class="selection" aria-label="Selecionar ambiente e dispositivo">
        <div class="fields">
          <label for="insights-environment">Ambiente
            <select id="insights-environment" :value="environmentId" name="environment" @change="changeScope($event, 'environment')" :disabled="catalogLoading || !environments.length">
              <option value="" disabled>Selecione um ambiente</option><option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option>
            </select>
          </label>
          <label for="insights-device">Dispositivo
            <select id="insights-device" :value="deviceUuid" name="device" @change="changeScope($event, 'device')" :disabled="catalogLoading || !devices.length">
              <option value="" disabled>Selecione um dispositivo</option><option v-for="device in devices" :key="device.id" :value="device.id">{{ device.name }}</option>
            </select>
          </label>
        </div>
        <p v-if="selectionNotice" role="status">{{ selectionNotice }}</p>
        <p v-if="catalogFailed" role="alert" class="notice error">Não foi possível carregar ambientes ou dispositivos. <button type="button" @click="loadEnvironments">Tentar novamente</button></p>
        <p v-else-if="catalogLoading" role="status">Carregando ambientes e dispositivos…</p>
        <MonitoringEmptyState v-else-if="environments.length === 0" missing="environment" />
        <MonitoringEmptyState v-else-if="environmentId && devices.length === 0" missing="device" />
      </section>
      <LiveDataRegion v-if="selectedDevice" :reset-key="deviceUuid">
        <div class="analysis-grid">
          <section class="panel estimates" aria-label="Previsão do equipamento" :aria-busy="loading && !snapshot">
            <div class="section-heading">
              <h2>{{ selectedDevice.name }}</h2>
              <p class="availability" :class="{ outdated: stale && !failed }" role="status">{{ statusMessage }}</p>
            </div>
            <dl class="estimate-values">
              <div><dt>Saúde estimada</dt><dd>{{ available ? `${format(snapshot?.prediction?.data.health_score)} / 100` : '—' }}</dd></div>
              <div><dt>Vida útil restante</dt><dd>{{ available ? `${format(snapshot?.prediction?.data.rul_hours)} h` : '—' }}</dd></div>
              <div><dt>Idade da leitura</dt><dd>{{ inputAgeLabel }}</dd></div>
            </dl>
            <p v-if="failed && !denied" role="alert">Não foi possível atualizar a previsão.</p>
            <p v-else-if="!stale && snapshot?.prediction?.data.reason">{{ reasonLabels[snapshot.prediction.data.reason] }}</p>
            <p v-if="available && snapshot && snapshot.trend !== 'unknown'" class="prediction-situation">
              Situação da última previsão <strong>{{ trendLabels[snapshot.trend] }}</strong>
            </p>
            <p class="origin">Modelo treinado com dados gerados para teste, sem calibração em equipamento real.</p>
            <details class="origin-details">
              <summary>Origem da previsão e horários</summary>
              <dl class="metadata">
                <div><dt>Equipamento</dt><dd>{{ snapshot?.equipment_id ?? 'Não identificado' }}</dd></div>
                <div><dt>Versão do modelo</dt><dd>{{ snapshot?.prediction?.data.model_version ?? 'Sem modelo confirmado' }}</dd></div>
                <div><dt>Versão das variáveis</dt><dd>{{ snapshot?.prediction?.data.features_version ?? 'Sem versão confirmada' }}</dd></div>
                <div><dt>Horário da leitura usada</dt><dd><time v-if="snapshot?.prediction" :datetime="snapshot.prediction.data.input_received_at">{{ formatTime(snapshot.prediction.data.input_received_at) }}</time><span v-else>Sem leitura associada à previsão</span></dd></div>
                <div><dt>Previsão calculada em</dt><dd><time v-if="snapshot?.prediction" :datetime="snapshot.prediction.occurred_at">{{ formatTime(snapshot.prediction.occurred_at) }}</time><span v-else>Sem previsão confirmada</span></dd></div>
              </dl>
              <p>Horários no fuso {{ timeZone }}. A idade da leitura é contada a partir da chegada dos dados dos sensores.</p>
            </details>
          </section>
          <section class="panel alerts-panel" aria-labelledby="insights-alerts">
            <h2 id="insights-alerts">Alertas em aberto</h2>
            <p v-if="failed && snapshot?.active_alerts.length">Não foi possível atualizar os alertas. A lista é da última consulta.</p>
            <ul v-if="snapshot?.active_alerts.length" class="events">
              <li v-for="alert in snapshot.active_alerts" :key="alert.alert_id">
                <strong class="persistent-alert">Alerta preditivo</strong>
                <p>Aberto em <time :datetime="alert.opened_at">{{ formatTime(alert.opened_at) }}</time></p>
                <details><summary>Identificadores do evento</summary>
                  <dl class="event-ids">
                    <div><dt>Alerta</dt><dd>{{ alert.alert_id }}</dd></div>
                    <div><dt>Leitura de origem</dt><dd>{{ alert.source_event_id }}</dd></div>
                    <div><dt>Previsão de origem</dt><dd>{{ alert.prediction_event_id }}</dd></div>
                  </dl>
                </details>
              </li>
            </ul>
            <p v-else-if="available">Nenhum alerta preditivo em aberto na última consulta.</p>
            <p v-else-if="loading && !snapshot && !failed">Consultando alertas…</p>
            <p v-else>Situação atual dos alertas sem confirmação.</p>
          </section>
        </div>
        <section v-if="snapshot && draft && !denied" class="panel rules-panel" aria-label="Limites preditivos">
          <div class="rules-heading">
            <h2>Regras preditivas</h2>
            <button v-if="canWrite && !editingRules" ref="editRulesButton" class="rules-edit" type="button" @click="startEditingRules">Editar regras</button>
          </div>
          <p v-if="failed">Últimas regras confirmadas.</p>
          <dl class="applied-rules">
            <div>
              <dt>Para abrir um alerta</dt>
              <dd><strong>{{ snapshot.rules.open_count }} previsões críticas</strong> seguidas com saúde ≤ {{ snapshot.rules.health_critical }} ou vida útil ≤ {{ snapshot.rules.rul_critical_hours }} h.</dd>
            </div>
            <div>
              <dt>Para encerrar um alerta</dt>
              <dd><strong>{{ snapshot.rules.close_count }} previsões de recuperação</strong> seguidas com saúde ≥ {{ snapshot.rules.health_recovery }} e vida útil ≥ {{ snapshot.rules.rul_recovery_hours }} h.</dd>
            </div>
          </dl>
          <p v-if="!canWrite">Seu acesso é de leitura. Somente operadores e administradores podem alterar as regras.</p>
          <p>Limites de protótipo. O buzzer segue as regras de temperatura.</p>
          <form v-if="canWrite && editingRules" ref="rulesForm" aria-label="Regras preditivas" novalidate :aria-busy="saving" @submit.prevent="saveRules">
            <h3>Editar regras</h3>
            <p v-if="dirty && !saving" role="status" class="notice unsaved">Há alterações não salvas.</p>
            <div class="rule-groups">
              <fieldset v-for="group in ruleGroups" :key="group.label">
                <legend>{{ group.label }}</legend>
                <div v-for="field in group.fields" :key="field.key" class="rule-field">
                  <label :for="`rule-${field.key}`">{{ field.label }}</label>
                  <input :id="`rule-${field.key}`" v-model.number="draft[field.key]" :name="field.key" type="number" :min="field.min" :max="field.max" :step="field.step" required :disabled="saving" :aria-invalid="Boolean(ruleErrors[field.key])" :aria-describedby="`rule-${field.key}-hint${ruleErrors[field.key] ? ` rule-${field.key}-error` : ''}`" @input="saveNotice = ''" />
                  <p :id="`rule-${field.key}-hint`" class="field-hint">{{ field.step === '1' ? 'Inteiro de 1 a 100.' : field.max === 100 ? 'Valor de 0 a 100.' : 'Horas, a partir de zero.' }}</p>
                  <p v-if="ruleErrors[field.key]" :id="`rule-${field.key}-error`" class="field-error">{{ ruleErrors[field.key] }}</p>
                </div>
              </fieldset>
            </div>
            <div class="actions">
              <button type="submit" class="primary" :disabled="saving">{{ saving ? 'Salvando…' : 'Salvar regras' }}</button>
              <button type="button" :disabled="saving" @click="cancelRules">Cancelar edição</button>
            </div>
          </form>
          <p v-if="saveNotice" role="status" class="save-notice">{{ saveNotice }}</p>
        </section>
      </LiveDataRegion>
    </div>
  </main>
</template>

<style scoped>
.insights { min-height: 100vh; padding: var(--cs-space-32); color: var(--cs-color-ink); background: var(--cs-color-canvas); line-height: 1.5; overflow-wrap: anywhere; }
.shell { max-width: 1280px; margin: auto; min-width: 0; }
.heading { margin-bottom: var(--cs-space-24); }
h2 { font-size: var(--cs-type-20); font-weight: 650; }
p { margin-top: var(--cs-space-12); color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); line-height: 1.6; }
a { color: var(--cs-color-accent); text-decoration: underline; }
button, input, select { min-height: var(--cs-control-min-height); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); }
input, select { width: 100%; min-width: 0; padding: var(--cs-space-8) var(--cs-space-12); font-size: var(--cs-type-16); }
button { padding: var(--cs-space-12) var(--cs-space-16); font-size: var(--cs-type-14); font-weight: 600; cursor: pointer; }
button:hover:enabled { background: var(--cs-color-surface-muted); }
button:disabled { background: var(--cs-color-surface-muted); color: var(--cs-color-ink-muted); cursor: not-allowed; }
.primary { border-color: var(--cs-color-accent); background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
.primary:hover:enabled { background: var(--cs-color-accent-hover); }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); }
.fields label, .rule-field label { display: grid; gap: var(--cs-space-8); color: var(--cs-color-ink); font-size: var(--cs-type-14); font-weight: 600; }
.selection { margin-bottom: var(--cs-space-24); }
.panel { min-width: 0; padding: var(--cs-space-24); background: var(--cs-color-surface); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); }
.analysis-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); align-items: start; gap: var(--cs-space-24); }
.section-heading, .rules-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--cs-space-8) var(--cs-space-16); }
.section-heading p { margin: 0; }
.availability { font-weight: 600; }
.availability.outdated { color: var(--cs-color-status-stale); }
.estimate-values { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cs-space-16); margin-block: var(--cs-space-16); padding-block: var(--cs-space-16); border-block: 1px solid var(--cs-color-line); }
dt { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
dd { margin-top: var(--cs-space-4); }
.estimate-values dd { font-size: var(--cs-type-32); font-weight: 650; font-variant-numeric: tabular-nums; }
.estimate-values > div:last-child dd { font-size: var(--cs-type-20); }
.prediction-situation strong { margin-inline-start: var(--cs-space-8); color: var(--cs-color-ink); }
.origin { color: var(--cs-color-status-stale); }
summary { min-height: var(--cs-control-min-height); padding-block: var(--cs-space-12); color: var(--cs-color-accent); font-size: var(--cs-type-14); font-weight: 600; cursor: pointer; }
.origin-details { margin-top: var(--cs-space-12); border-top: 1px solid var(--cs-color-line); }
.metadata, .applied-rules { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16) var(--cs-space-24); }
.events { margin-top: var(--cs-space-16); }
.events li + li { margin-top: var(--cs-space-12); padding-top: var(--cs-space-12); border-top: 1px solid var(--cs-color-line); }
.events p { margin-top: var(--cs-space-4); }
.persistent-alert { display: inline-block; padding: var(--cs-space-4) var(--cs-space-8); border-radius: var(--cs-radius-4); background: var(--cs-color-attention-surface); color: var(--cs-color-status-attention); font-size: var(--cs-type-14); }
.event-ids { display: grid; gap: var(--cs-space-12); }
.rules-panel { margin-top: var(--cs-space-24); }
.applied-rules { margin-top: var(--cs-space-16); }
.applied-rules dt { font-weight: 600; }
.rules-panel h3 { font-weight: 650; }
.rules-panel form { margin-top: var(--cs-space-16); padding-top: var(--cs-space-16); border-top: 1px solid var(--cs-color-line); }
.rule-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cs-space-24); margin-top: var(--cs-space-24); }
fieldset { min-width: 0; }
legend { padding: 0; margin-bottom: var(--cs-space-16); font-weight: 600; }
.rule-field + .rule-field { margin-top: var(--cs-space-16); }
.rule-field input { margin-top: var(--cs-space-8); }
.field-hint, .field-error { margin-top: var(--cs-space-4); font-size: var(--cs-type-14); }
.field-error { color: var(--cs-color-status-critical); }
input[aria-invalid='true'] { border-color: var(--cs-color-status-critical); }
.notice { padding: var(--cs-space-16); border: 1px solid var(--cs-color-status-stale); border-radius: var(--cs-radius-8); background: var(--cs-color-stale-surface); color: var(--cs-color-status-stale); }
.notice.error { border-color: var(--cs-color-status-critical); background: var(--cs-color-critical-surface); color: var(--cs-color-status-critical); }
.notice.unsaved { border-color: var(--cs-color-status-attention); background: var(--cs-color-attention-surface); color: var(--cs-color-status-attention); }
.actions { display: flex; flex-wrap: wrap; gap: var(--cs-space-12); margin-top: var(--cs-space-24); }
.save-notice { color: var(--cs-color-ink); }
@media (max-width: 50rem) {
  .insights { padding: var(--cs-space-16); }
  .fields, .analysis-grid, .rule-groups { grid-template-columns: minmax(0, 1fr); }
  .fields, .rule-groups { gap: var(--cs-space-16); }
  .panel { padding: var(--cs-space-16); }
}
@media (max-width: 32rem) {
  .estimate-values { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metadata, .applied-rules { grid-template-columns: minmax(0, 1fr); }
}
</style>
