<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { listDevices, listEnvironments, type Device, type Environment } from '../features/account/catalog'
import { canWrite, clearSession, logout, refreshSessionIdentity, sessionToken } from '../features/account/session'
import { fetchInsights, InsightsAccessError, parsePredictiveRules, savePredictiveRules, type InsightsSnapshot, type PredictiveRules } from '../features/insights/insights-api'
import { STALE_AFTER_SECONDS } from '../features/monitoring/monitoring-state'

const router = useRouter()
const environments = ref<Environment[]>([])
const devices = ref<Device[]>([])
const environmentId = ref('')
const deviceUuid = ref('')
const selectedDevice = computed(() => devices.value.find((device) => device.id === deviceUuid.value && device.is_active))
const catalogLoading = ref(false)
const catalogFailed = ref(false)
const snapshot = ref<InsightsSnapshot | null>(null)
const failed = ref(false)
const denied = ref(false)
const loading = ref(false)
const draft = ref<PredictiveRules | null>(null)
const dirty = ref(false)
const saving = ref(false)
const saveNotice = ref('')
const logoutError = ref('')
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
  if (stale.value) return 'Previsão desatualizada. Aguardando uma entrada recente.'
  if (failed.value) return 'Consulta indisponível. A situação atual não está confirmada.'
  if (available.value) return 'Previsão disponível'
  if (snapshot.value?.availability === 'unavailable') return 'Previsão indisponível'
  return loading.value ? 'Consultando previsão…' : 'Sem previsão para este equipamento.'
})
const trendLabels = { improving: 'Em recuperação', declining: 'Em queda', stable: 'Estável', unknown: 'Desconhecida' }
const reasonLabels = {
  no_model: 'Nenhum modelo ativo.', insufficient_history: 'Histórico insuficiente.', invalid_features: 'Variáveis inválidas.',
  model_unavailable: 'Não foi possível executar o modelo ativo.', stale_input: 'Entrada desatualizada.',
}
const ruleFields: { key: keyof PredictiveRules; label: string; min: number; max?: number; step: string }[] = [
  { key: 'health_critical', label: 'Saúde crítica', min: 0, max: 100, step: 'any' },
  { key: 'health_recovery', label: 'Saúde de recuperação', min: 0, max: 100, step: 'any' },
  { key: 'rul_critical_hours', label: 'RUL crítico (h)', min: 0, step: 'any' },
  { key: 'rul_recovery_hours', label: 'RUL de recuperação (h)', min: 0, step: 'any' },
  { key: 'open_count', label: 'Previsões para abrir', min: 1, max: 100, step: '1' },
  { key: 'close_count', label: 'Previsões para encerrar', min: 1, max: 100, step: '1' },
]
const clock = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => { selectionRevision += 1; clearInterval(clock); saveController?.abort() })

watch(sessionToken, (token, _old, onCleanup) => {
  let active = true
  environments.value = []
  devices.value = []
  environmentId.value = ''
  deviceUuid.value = ''
  catalogFailed.value = false
  catalogLoading.value = Boolean(token)
  onCleanup(() => { active = false })
  if (!token) { void router.replace('/login'); return }
  void listEnvironments(token).then((result) => {
    if (!active) return
    environments.value = result
    environmentId.value = result[0]?.id ?? ''
  }).catch(() => { if (active) catalogFailed.value = true })
    .finally(() => { if (active && !environmentId.value) catalogLoading.value = false })
}, { immediate: true, flush: 'sync' })

watch([sessionToken, environmentId], ([token, id], _old, onCleanup) => {
  let active = true
  devices.value = []
  deviceUuid.value = ''
  onCleanup(() => { active = false })
  if (!token || !id) return
  catalogLoading.value = true
  catalogFailed.value = false
  void listDevices(token, id).then((result) => {
    if (!active) return
    devices.value = result.filter((device) => device.environment_id === id && device.is_active)
    deviceUuid.value = devices.value[0]?.id ?? ''
  }).catch(() => { if (active) catalogFailed.value = true })
    .finally(() => { if (active) catalogLoading.value = false })
}, { immediate: true, flush: 'sync' })

function revokeAccess(error: InsightsAccessError) {
  snapshot.value = null
  draft.value = null
  denied.value = true
  if (error.status === 401) clearSession()
  else void refreshSessionIdentity().catch(() => { /* Unknown permissions remain read-only. */ })
}

watch([sessionToken, selectedDevice], ([token, device], _old, onCleanup) => {
  selectionRevision += 1
  saveController?.abort()
  snapshot.value = null
  draft.value = null
  dirty.value = false
  failed.value = false
  denied.value = false
  loading.value = false
  saving.value = false
  saveNotice.value = ''
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
      if (!dirty.value) draft.value = { ...result.rules }
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
  if (!rules) { saveNotice.value = 'Regras inválidas. Recuperação deve superar o limite crítico; contagens inteiras entre 1 e 100.'; return }
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
    dirty.value = false
    saveNotice.value = 'Regras salvas. As próximas previsões usarão os limites confirmados.'
  } catch (error) {
    if (revision !== selectionRevision) return
    saveNotice.value = 'Não foi possível salvar as regras. Confira o acesso e tente novamente.'
    if (error instanceof InsightsAccessError) revokeAccess(error)
  } finally {
    clearTimeout(deadline)
    if (revision === selectionRevision) saving.value = false
  }
}

async function signOut() {
  logoutError.value = ''
  try { await logout() } catch { logoutError.value = 'Não foi possível encerrar a sessão. Tente novamente.' }
}
const format = (value: number | null | undefined) => value?.toLocaleString('pt-BR', { maximumFractionDigits: 2 }) ?? '—'
</script>

<template>
  <main class="insights">
    <a class="skip-link" href="#insights-title">Ir para o conteúdo</a>
    <div class="shell">
      <header class="nav">
        <RouterLink to="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</RouterLink>
        <nav aria-label="Navegação principal">
          <RouterLink to="/dashboard">Monitoramento</RouterLink><RouterLink to="/insights" aria-current="page">Insights</RouterLink><RouterLink to="/digital-twin">Gêmeo digital</RouterLink>
          <RouterLink to="/manage">Ambientes e dispositivos</RouterLink><RouterLink to="/messaging">Mensageria</RouterLink>
          <RouterLink to="/laboratory">Laboratório</RouterLink><RouterLink to="/training">Treinamento</RouterLink>
        </nav>
        <button type="button" @click="signOut">Sair</button>
      </header>
      <p v-if="logoutError" role="alert">{{ logoutError }}</p>
      <section class="heading"><p class="eyebrow">Manutenção preditiva</p><h1 id="insights-title" tabindex="-1">Insights</h1><p>Saúde estimada, vida útil restante e alertas persistentes por equipamento.</p></section>
      <section class="panel" aria-label="Selecionar equipamento">
        <div class="fields">
          <label>Ambiente<select v-model="environmentId" name="environment"><option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option></select></label>
          <label>Equipamento<select v-model="deviceUuid" name="device"><option v-for="device in devices" :key="device.id" :value="device.id">{{ device.name }}</option></select></label>
        </div>
        <p v-if="catalogFailed" role="alert">Não foi possível carregar o catálogo. Reabra esta página para tentar novamente.</p>
        <p v-else-if="catalogLoading" role="status">Carregando equipamentos autorizados…</p>
        <p v-else-if="environments.length === 0" role="status">Nenhum ambiente autorizado. <RouterLink to="/manage">Gerenciar ambientes</RouterLink></p>
        <p v-else-if="devices.length === 0" role="status">Nenhum equipamento ativo neste ambiente.</p>
      </section>
      <template v-if="selectedDevice">
        <section class="panel" aria-label="Insights do equipamento" :aria-busy="loading">
          <h2>{{ selectedDevice.name }}</h2>
          <p role="status" aria-live="polite">{{ statusMessage }}</p>
          <p v-if="failed && !denied" role="alert">Não foi possível atualizar os Insights. Ausência de dados não significa recuperação. Alertas da última consulta confirmada são mantidos.</p>
          <p v-if="!available && !denied">Ausência de previsão válida não significa recuperação.</p>
          <p v-if="snapshot?.prediction?.data.reason && !failed">{{ reasonLabels[snapshot.prediction.data.reason] }}</p>
          <dl>
            <div><dt>Saúde</dt><dd>{{ available ? `${format(snapshot?.prediction?.data.health_score)} / 100` : '—' }}</dd></div>
            <div><dt>RUL</dt><dd>{{ available ? `${format(snapshot?.prediction?.data.rul_hours)} h` : '—' }}</dd></div>
            <div><dt>Tendência</dt><dd>{{ available && snapshot ? trendLabels[snapshot.trend] : 'Desconhecida' }}</dd></div>
            <div><dt>Versão do modelo</dt><dd>{{ snapshot?.prediction?.data.model_version ?? 'Sem modelo confirmado' }}</dd></div>
            <div><dt>Idade da previsão</dt><dd>{{ ageSeconds !== null && snapshot?.prediction ? `há ${ageSeconds} s (desde a entrada)` : 'Sem previsão confirmada' }}</dd></div>
            <div v-if="!snapshot?.prediction && ageSeconds !== null"><dt>Idade da entrada</dt><dd>há {{ ageSeconds }} s</dd></div>
          </dl>
          <p>Estimativas do modelo para a entrada recebida. Uma previsão não renova a atualidade dos sensores.</p>
        </section>
        <section class="panel" aria-label="Alertas preditivos ativos">
          <h2>Alertas preditivos ativos</h2>
          <ul v-if="snapshot?.active_alerts.length"><li v-for="alert in snapshot.active_alerts" :key="alert.alert_id"><strong>Alerta preditivo persistente</strong> · Aberto em <time :datetime="alert.opened_at">{{ new Date(alert.opened_at).toLocaleString('pt-BR') }}</time></li></ul>
          <p v-else-if="available">Nenhum alerta preditivo ativo na última consulta confirmada.</p>
          <p v-else>Situação atual dos alertas não confirmada. Aguardando previsão válida e consulta disponível.</p>
          <p>Este alerta indica falha estimada do equipamento. O buzzer térmico continua separado e segue as regras de temperatura.</p>
        </section>
        <section v-if="snapshot && draft && !denied" class="panel" aria-label="Limites preditivos">
          <h2>Regras preditivas</h2>
          <p>Limites iniciais de protótipo, configuráveis e não calibrados para equipamentos reais. Valide os valores com dados do equipamento antes de usá-los operacionalmente.</p>
          <p>{{ snapshot.rules.open_count }} previsões críticas consecutivas para abrir; {{ snapshot.rules.close_count }} recuperadas consecutivas para encerrar.</p>
          <p>Abre quando saúde ≤ {{ snapshot.rules.health_critical }} ou RUL ≤ {{ snapshot.rules.rul_critical_hours }} h. Recupera quando saúde ≥ {{ snapshot.rules.health_recovery }} e RUL ≥ {{ snapshot.rules.rul_recovery_hours }} h.</p>
          <form v-if="canWrite" aria-label="Regras preditivas" @submit.prevent="saveRules">
            <div class="fields"><label v-for="field in ruleFields" :key="field.key">{{ field.label }}<input v-model.number="draft[field.key]" :name="field.key" type="number" :min="field.min" :max="field.max" :step="field.step" required :disabled="saving" @input="dirty = true; saveNotice = ''" /></label></div>
            <button type="submit" :disabled="saving">{{ saving ? 'Salvando…' : 'Salvar regras' }}</button>
          </form>
          <p v-else>Somente operadores e administradores podem alterar as regras. Seu acesso é de leitura.</p>
          <p v-if="saveNotice" role="status">{{ saveNotice }}</p>
        </section>
      </template>
    </div>
  </main>
</template>

<style scoped>
.insights { min-height: 100vh; padding: var(--cs-space-48); color: var(--cs-color-ink); background: var(--cs-color-canvas); }
.shell { max-width: 1280px; margin: auto; display: grid; gap: var(--cs-space-24); min-width: 0; }
.nav { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.brand { font-weight: 700; }.nav nav { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); font-size: var(--cs-type-14); }
a, button { color: var(--cs-color-accent); }.nav a, button { display: inline-flex; align-items: center; min-height: 44px; }button { cursor: pointer; }button:disabled { opacity: .6; cursor: not-allowed; }a:hover, button:hover { text-decoration: underline; }
h1 { font-size: var(--cs-type-32); font-weight: 600; }h2 { font-size: var(--cs-type-20); font-weight: 600; }.eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: var(--cs-type-12); color: var(--cs-color-ink-muted); }
.panel { min-width: 0; padding: var(--cs-space-24); background: var(--cs-color-surface); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); }
p { margin-top: var(--cs-space-12); line-height: 1.7; overflow-wrap: anywhere; }[role=alert] { border-left: 3px solid var(--cs-color-status-attention); padding-left: var(--cs-space-12); }
.fields, dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16); }label { display: grid; gap: var(--cs-space-8); font-weight: 600; }input, select { width: 100%; min-width: 0; min-height: 44px; padding: var(--cs-space-8); background: var(--cs-color-canvas); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); }
dl, form { margin-top: var(--cs-space-24); }dt { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }dd { margin-top: var(--cs-space-8); font-size: var(--cs-type-20); overflow-wrap: anywhere; }form button { margin-top: var(--cs-space-16); padding: var(--cs-space-8) var(--cs-space-16); border: 1px solid var(--cs-color-accent); border-radius: var(--cs-radius-4); }ul { padding-left: var(--cs-space-24); margin-top: var(--cs-space-16); list-style: disc; }li { overflow-wrap: anywhere; }
.skip-link { position: absolute; transform: translateY(-200%); }.skip-link:focus { transform: none; background: var(--cs-color-surface); padding: var(--cs-space-12); }
@media (max-width: 800px) { .insights { padding: var(--cs-space-24); }.nav { gap: var(--cs-space-8); }.nav nav { order: 3; width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }.nav a { min-width: 0; overflow-wrap: anywhere; }.panel { padding: var(--cs-space-16); }h1 { font-size: var(--cs-type-24); } }
@media (max-width: 420px) { .fields, dl { grid-template-columns: minmax(0, 1fr); } }
</style>
