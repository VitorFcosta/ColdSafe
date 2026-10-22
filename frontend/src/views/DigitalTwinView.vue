<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { listDevices, listEnvironments, type Device, type Environment } from '../features/account/catalog'
import { clearSession, logout, refreshSessionIdentity, sessionToken } from '../features/account/session'
import DigitalTwinScene from '../features/digital-twin/DigitalTwinScene.vue'
import TwinItemPanel from '../features/digital-twin/TwinItemPanel.vue'
import { buildTwinItems, buildTwinVisualState, twinColors, twinStatusLabels as statusLabels } from '../features/digital-twin/twin-state'
import { fetchInsights, InsightsAccessError, type InsightsSnapshot } from '../features/insights/insights-api'
import { aiotEnabled } from '../features/monitoring/monitoring-version'
import { useMonitoringSummary } from '../features/monitoring/use-monitoring-summary'

const router = useRouter()
const environments = ref<Environment[]>([])
const devices = ref<Device[]>([])
const environmentId = ref('')
const deviceUuid = ref('')
const selectedDevice = computed(() => devices.value.find((device) => device.id === deviceUuid.value && device.environment_id === environmentId.value && device.is_active))
const denied = ref(false)
const catalogLoading = ref(false)
const catalogFailed = ref(false)
const insights = ref<InsightsSnapshot | null>(null)
const insightsFailed = ref(false)
const selectedId = ref<string | null>(null)
const logoutError = ref('')
const mqttId = computed(() => aiotEnabled && !denied.value ? selectedDevice.value?.mqtt_device_id ?? null : null)
const { summary, monitoringState, refreshRevision, connectionState, ageSeconds } = useMonitoringSummary(sessionToken, mqttId)
const scopedSummary = computed(() => {
  const current = summary.value
  const device = selectedDevice.value
  if (!aiotEnabled || !sessionToken.value || denied.value || !device || !current ||
    current.device.id !== device.mqtt_device_id || current.environment.id !== device.environment_id ||
    (current.reading && (current.reading.device_record_id !== device.id || current.reading.environment_id !== device.environment_id))) return null
  return current
})
const fresh = computed(() => ['normal', 'attention', 'critical'].includes(monitoringState.value.kind))
const items = computed(() => buildTwinItems(scopedSummary.value, fresh.value && scopedSummary.value !== null, insightsFailed.value ? null : insights.value))
const visual = computed(() => buildTwinVisualState(scopedSummary.value, fresh.value))
const selected = computed(() => items.value.find((item) => item.id !== null && item.id === selectedId.value))
const monitorMessage = computed(() => {
  if (denied.value) return 'Acesso ao equipamento indisponível. Selecione outro equipamento ou entre novamente.'
  if (monitoringState.value.kind === 'service_error') return 'Monitoramento indisponível. A situação atual não está confirmada.'
  if (monitoringState.value.kind === 'stale') return 'Leitura desatualizada. Aguardando dados recentes.'
  if (!scopedSummary.value || !fresh.value) return 'Sem dados atuais confirmados para este equipamento.'
  return 'Monitoramento atualizado a partir do resumo autorizado.'
})

watch(sessionToken, (token, _old, onCleanup) => {
  let active = true
  onCleanup(() => { active = false })
  environments.value = []; devices.value = []; environmentId.value = ''; deviceUuid.value = ''
  catalogFailed.value = false; catalogLoading.value = Boolean(token && aiotEnabled)
  if (!token) { void router.replace('/login'); return }
  if (!aiotEnabled) return
  void listEnvironments(token).then((result) => {
    if (!active) return
    environments.value = result; environmentId.value = result[0]?.id ?? ''
  }).catch(() => { if (active) catalogFailed.value = true })
    .finally(() => { if (active && !environmentId.value) catalogLoading.value = false })
}, { immediate: true, flush: 'sync' })

watch([sessionToken, environmentId], ([token, id], _old, onCleanup) => {
  let active = true
  onCleanup(() => { active = false })
  devices.value = []; deviceUuid.value = ''
  if (!aiotEnabled || !token || !id) return
  catalogLoading.value = true; catalogFailed.value = false
  void listDevices(token, id).then((result) => {
    if (!active) return
    devices.value = result.filter((device) => device.environment_id === id && device.is_active)
    deviceUuid.value = devices.value[0]?.id ?? ''
  }).catch(() => { if (active) catalogFailed.value = true })
    .finally(() => { if (active) catalogLoading.value = false })
}, { immediate: true, flush: 'sync' })

watch([sessionToken, selectedDevice], () => {
  denied.value = false; insights.value = null; insightsFailed.value = false; selectedId.value = null
}, { flush: 'sync' })

function denyAccess(status: number, token: string) {
  denied.value = true; insights.value = null; selectedId.value = null
  summary.value = null
  if (status === 401) { if (sessionToken.value === token) clearSession() }
  else void refreshSessionIdentity().catch(() => { /* Access remains blocked until selection changes. */ })
}

watch(connectionState, (state) => {
  if (sessionToken.value && (state === 'forbidden' || state === 'unauthorized')) denyAccess(state === 'unauthorized' ? 401 : 403, sessionToken.value)
}, { flush: 'sync' })

watch([sessionToken, selectedDevice], ([token, device], _old, onCleanup) => {
  if (!aiotEnabled || !token || !device || denied.value) return
  let active = true
  let pending = false
  let queued = false
  let requestRevision = 0
  let controller: AbortController | null = null
  let deadline: ReturnType<typeof setTimeout> | undefined
  async function refresh() {
    if (!active || denied.value) return
    if (pending) { queued = true; return }
    pending = true
    queued = false
    const revision = ++requestRevision
    controller = new AbortController()
    const signal = controller.signal
    deadline = setTimeout(() => {
      requestRevision += 1
      pending = false
      queued = false
      insightsFailed.value = true
      controller?.abort()
    }, 8000)
    const requestDeadline = deadline
    try {
      const result = await fetchInsights(token!, device!, signal)
      if (!active || denied.value || revision !== requestRevision) return
      insights.value = result
      insightsFailed.value = false
    } catch (error: unknown) {
      if (!active || denied.value || revision !== requestRevision) return
      insightsFailed.value = true
      queued = false
      if (error instanceof InsightsAccessError) denyAccess(error.status, token!)
    } finally {
      clearTimeout(requestDeadline)
      if (active && revision === requestRevision) {
        pending = false
        if (queued) void refresh()
      }
    }
  }
  const stopRefresh = watch(refreshRevision, () => { void refresh() }, { flush: 'sync' })
  onCleanup(() => { active = false; stopRefresh(); clearTimeout(deadline); controller?.abort() })
  void refresh()
}, { immediate: true, flush: 'sync' })

watch(items, (next) => {
  if (!next.some((item) => item.id !== null && item.id === selectedId.value)) selectedId.value = null
}, { flush: 'sync' })
function selectItem(id: string) {
  if (items.value.some((item) => item.id === id)) selectedId.value = id
}
async function signOut() {
  logoutError.value = ''
  try { await logout() } catch { logoutError.value = 'Não foi possível encerrar a sessão. Tente novamente.' }
}
</script>

<template>
  <main class="digital-twin">
    <a class="skip-link" href="#digital-twin-title">Ir para o conteúdo</a>
    <div class="shell">
      <header class="nav">
        <RouterLink to="/" class="brand">◉ ColdSafe</RouterLink>
        <nav aria-label="Navegação principal">
          <RouterLink to="/dashboard">Monitoramento</RouterLink><RouterLink to="/insights">Insights</RouterLink>
          <RouterLink to="/digital-twin" aria-current="page">Gêmeo digital</RouterLink><RouterLink to="/manage">Ambientes e dispositivos</RouterLink>
          <RouterLink to="/messaging">Mensageria</RouterLink><RouterLink to="/laboratory">Laboratório</RouterLink><RouterLink to="/training">Treinamento</RouterLink><RouterLink to="/assistant">Assistente</RouterLink>
        </nav>
        <button type="button" @click="signOut">Sair</button>
      </header>
      <p v-if="logoutError" role="alert">{{ logoutError }}</p>
      <section><p class="eyebrow">Representação do equipamento</p><h1 id="digital-twin-title" tabindex="-1">Gêmeo digital</h1><p>Explore sensores, atuadores e equipamento pelos seus identificadores reais.</p></section>
      <p v-if="!aiotEnabled" class="panel" role="status">O gêmeo digital requer AIoT v3 habilitado. Não há inventário de componentes disponível no modo legado.</p>
      <template v-else>
        <section class="panel" aria-label="Selecionar equipamento">
          <div class="fields">
            <label>Ambiente<select v-model="environmentId" name="environment"><option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option></select></label>
            <label>Equipamento<select v-model="deviceUuid" name="device"><option v-for="device in devices" :key="device.id" :value="device.id">{{ device.name }}</option></select></label>
          </div>
          <p v-if="catalogFailed" role="alert">Não foi possível carregar o catálogo. Reabra esta página para tentar novamente.</p>
          <p v-else-if="catalogLoading" role="status">Carregando equipamentos autorizados…</p>
          <p v-else-if="!environments.length" role="status">Nenhum ambiente autorizado. <RouterLink to="/manage">Gerenciar ambientes</RouterLink></p>
          <p v-else-if="!devices.length" role="status">Nenhum equipamento ativo neste ambiente.</p>
        </section>
        <p v-if="selectedDevice" role="status" aria-live="polite">{{ monitorMessage }}</p>
        <p v-if="insightsFailed && !denied" role="alert">Não foi possível atualizar os Insights. O estado preditivo não está confirmado; ausência de dados não significa recuperação.</p>
        <p v-if="insights?.active_alerts.length && !denied" role="status">Alerta preditivo persistente na última consulta confirmada. Ausência de dados não significa encerramento. <RouterLink to="/insights">Consultar Insights</RouterLink></p>
        <template v-if="selectedDevice && !denied && sessionToken">
          <section class="panel" aria-label="Legenda de estados">
            <h2>Estados dos componentes</h2>
            <ul class="legend"><li v-for="(label, status) in statusLabels" :key="status"><span class="dot" :style="{ backgroundColor: `#${twinColors[status].toString(16).padStart(6, '0')}` }" aria-hidden="true" />{{ label }}</li></ul>
            <p>As faixas de temperatura ambiente vêm das regras do ambiente. Os demais sensores não têm faixas operacionais configuradas; seus valores não confirmam operação segura.</p>
            <p>A cor do ventilador segue o alerta persistente e as faixas de recuperação preditivas; sem previsão confirmada fica sem dados. LED e buzzer mostram o estado observado na telemetria.</p>
          </section>
          <div class="workspace">
            <section class="panel scene" aria-label="Visualização do gêmeo digital"><DigitalTwinScene :key="`${environmentId}:${deviceUuid}`" :items="items" :selected-id="selectedId" :visual="visual" @select="selectItem" /></section>
            <section class="panel" aria-label="Componentes do gêmeo digital">
              <h2>Componentes</h2>
              <p>A lista oferece os mesmos componentes e estados da cena e pode ser usada pelo teclado.</p>
              <ul class="components"><li v-for="item in items" :key="item.key"><button type="button" :aria-pressed="item.id !== null && selectedId === item.id" :disabled="item.id === null" @click="item.id && selectItem(item.id)"><strong>{{ item.label }}</strong><span>ID: {{ item.id ?? 'Sem identificador confirmado' }}</span><span>{{ item.value }} · {{ statusLabels[item.status] }}</span></button></li></ul>
            </section>
          </div>
          <TwinItemPanel v-if="selected && scopedSummary && selectedDevice" :key="`${environmentId}:${deviceUuid}`" :item="selected" :summary="scopedSummary" :device="selectedDevice" :token="sessionToken" :fresh="fresh" :age-seconds="ageSeconds" :revision="refreshRevision" :connection-state="connectionState" />
        </template>
      </template>
    </div>
  </main>
</template>

<style scoped>
.digital-twin { min-height: 100vh; padding: var(--cs-space-48); color: var(--cs-color-ink); background: var(--cs-color-canvas); }
.shell { max-width: 1280px; margin: auto; display: grid; gap: var(--cs-space-24); min-width: 0; }
.nav, .nav nav, .legend { display: flex; flex-wrap: wrap; align-items: center; gap: var(--cs-space-16); }.nav { justify-content: space-between; border-bottom: 1px solid var(--cs-color-line); padding-bottom: var(--cs-space-24); }.brand { font-weight: 700; }
a, button { color: var(--cs-color-accent); }.nav a, button { min-height: 44px; }.nav a { display: inline-flex; align-items: center; }button { cursor: pointer; }button:disabled { cursor: default; }a:hover, button:hover { text-decoration: underline; }:is(a, button, select):focus-visible { outline: 3px solid var(--cs-color-accent); outline-offset: 3px; }
h1 { font-size: var(--cs-type-32); }h2 { font-size: var(--cs-type-20); }h1, h2 { font-weight: 600; }.eyebrow { text-transform: uppercase; letter-spacing: .12em; color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); }
.panel { min-width: 0; padding: var(--cs-space-24); background: var(--cs-color-surface); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); }
p { margin-top: var(--cs-space-12); line-height: 1.7; }p, a, button, dd { overflow-wrap: anywhere; }[role=alert] { border-left: 3px solid var(--cs-color-status-attention); padding-left: var(--cs-space-12); }
.fields, .workspace { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16); }label { display: grid; gap: var(--cs-space-8); font-weight: 600; }select { width: 100%; min-width: 0; min-height: 44px; padding: var(--cs-space-8); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-canvas); }
.legend { margin-top: var(--cs-space-16); }.legend li { display: flex; align-items: center; gap: var(--cs-space-8); }.dot { width: 14px; height: 14px; border-radius: 50%; }
.components { display: grid; gap: var(--cs-space-8); margin-top: var(--cs-space-16); }.components button { display: grid; gap: var(--cs-space-8); text-align: left; width: 100%; padding: var(--cs-space-12); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); }.components button[aria-pressed=true] { outline: 2px solid var(--cs-color-accent); }.components button:disabled { color: var(--cs-color-ink-muted); }.scene { padding: var(--cs-space-8); align-self: start; }dl { display: grid; gap: var(--cs-space-16); margin-top: var(--cs-space-16); }dt { color: var(--cs-color-ink-muted); }dd { margin-top: var(--cs-space-8); }
.skip-link { position: absolute; transform: translateY(-200%); }.skip-link:focus { transform: none; background: var(--cs-color-surface); padding: var(--cs-space-12); }
@media (max-width: 900px) { .digital-twin { padding: var(--cs-space-24); }.workspace { grid-template-columns: minmax(0, 1fr); }.nav nav { order: 3; width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }.nav a { min-width: 0; }.panel { padding: var(--cs-space-16); } }
@media (max-width: 420px) { .digital-twin { padding: var(--cs-space-16); }.fields { grid-template-columns: minmax(0, 1fr); }h1 { font-size: var(--cs-type-24); } }
</style>
