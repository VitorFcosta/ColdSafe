<script setup lang="ts">
import LiveDataRegion from '../features/monitoring/LiveDataRegion.vue'
import MonitoringEmptyState from '../features/monitoring/MonitoringEmptyState.vue'
import { computed, ref, watch } from 'vue'
import { useMonitoringContext } from '../features/monitoring/use-monitoring-context'
import { clearSession, refreshSessionIdentity, sessionToken } from '../features/account/session'
import DigitalTwinScene from '../features/digital-twin/DigitalTwinScene.vue'
import TwinItemPanel from '../features/digital-twin/TwinItemPanel.vue'
import { buildTwinItems, buildTwinVisualState, twinStatusLabels as statusLabels, type TwinItem } from '../features/digital-twin/twin-state'
import { fetchInsights, InsightsAccessError, type InsightsSnapshot } from '../features/insights/insights-api'
import { aiotEnabled } from '../features/monitoring/monitoring-version'
import { formatFreshness, useMonitoringSummary } from '../features/monitoring/use-monitoring-summary'
import AreaNavigation from '../features/navigation/AreaNavigation.vue'

const { environments, devices, environmentId, deviceUuid, selectedDevice,
  selectionNotice, catalogLoading, catalogFailed, loadEnvironments, monitoringLocation, revokeSelection } = useMonitoringContext(aiotEnabled)
const dataHidden = ref(false)
const denied = ref(false)
const insights = ref<InsightsSnapshot | null>(null)
const insightsFailed = ref(false)
const selectedId = ref<string | null>(null)
const animationPaused = ref(false)
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
const hasSelectableItems = computed(() => items.value.some(item => item.id !== null))
function itemReading(item: TwinItem) {
  if (item.kind === 'equipment' && fresh.value && scopedSummary.value?.equipment) {
    return `${item.value} · ${item.status === 'no_data' ? 'Sem previsão' : statusLabels[item.status]}`
  }
  if (item.status === 'attention' || item.status === 'critical' || (item.key === 'temperature_c' && item.status === 'normal')) {
    return `${item.value} · ${statusLabels[item.status]}`
  }
  return item.value
}
const monitorMessage = computed(() => {
  if (denied.value) return 'Acesso ao equipamento indisponível. Selecione outro equipamento ou entre novamente.'
  if (monitoringState.value.kind === 'service_error') return 'Monitoramento indisponível. A situação atual não está confirmada.'
  if (monitoringState.value.kind === 'stale') return 'Leitura desatualizada. Aguardando dados recentes.'
  if (!scopedSummary.value || !fresh.value) return 'Sem dados atuais confirmados para este equipamento.'
  return 'Monitoramento atualizado a partir do resumo autorizado.'
})

watch([sessionToken, selectedDevice], () => {
  denied.value = false; insights.value = null; insightsFailed.value = false; selectedId.value = null
}, { flush: 'sync' })

function denyAccess(status: number, token: string) {
  denied.value = true; insights.value = null; selectedId.value = null
  summary.value = null
  if (status === 401) { if (sessionToken.value === token) clearSession() }
  else void revokeSelection().then(() => refreshSessionIdentity()).catch(() => { /* Access remains blocked until selection changes. */ })
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
</script>

<template>
  <main class="digital-twin">
    <div class="shell">
      <header class="area-heading">
        <h1 id="digital-twin-title" tabindex="-1">Gêmeo digital</h1>
        <AreaNavigation />
      </header>
      <template v-if="!aiotEnabled">
        <section class="notice" aria-label="Gêmeo indisponível no modo legado">
          <p role="status">O gêmeo digital requer AIoT v3 habilitado. Não há inventário de componentes disponível no modo legado.</p>
          <RouterLink data-legacy-exit :to="monitoringLocation('/dashboard')">Ir para a Visão geral</RouterLink>
        </section>
      </template>
      <template v-else>
        <section class="context" aria-label="Selecionar ambiente e dispositivo">
          <div class="context-row">
          <div class="fields">
            <label>Ambiente<select v-model="environmentId" name="environment" :disabled="catalogLoading || !environments.length"><option value="" disabled>Selecione um ambiente</option><option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option></select></label>
            <label>Dispositivo<select v-model="deviceUuid" name="device" :disabled="catalogLoading || !devices.length"><option value="" disabled>Selecione um dispositivo</option><option v-for="device in devices" :key="device.id" :value="device.id">{{ device.name }}</option></select></label>
          </div>
          <div v-if="selectedDevice && !denied" v-show="!dataHidden" class="connection">
            <p class="connection-label" :class="{ connected: connectionState === 'connected' }">{{ connectionState === 'connected' ? 'Servidor conectado' : 'Conexão não confirmada' }}</p>
            <p>{{ scopedSummary?.reading ? formatFreshness(ageSeconds ?? undefined) : 'Sem leitura recebida' }}</p>
          </div>
          </div>
          <p v-if="selectionNotice" role="status">{{ selectionNotice }}</p>
          <p v-if="catalogFailed" role="alert">Não foi possível carregar ambientes ou dispositivos. <button type="button" @click="loadEnvironments">Tentar novamente</button></p>
          <p v-else-if="catalogLoading" role="status">Carregando ambientes e dispositivos…</p>
          <MonitoringEmptyState v-else-if="!environments.length" missing="environment" />
          <MonitoringEmptyState v-else-if="environmentId && !devices.length" missing="device" />
        </section>
        <div v-show="selectedDevice" class="contents">
          <LiveDataRegion v-model="dataHidden" :reset-key="deviceUuid">
            <p v-if="selectedDevice && (denied || !fresh || !scopedSummary)" class="monitor-status notice" role="status">{{ monitorMessage }}</p>
            <p v-if="insightsFailed && !denied" class="notice" role="alert">Não foi possível atualizar a previsão. Sem dados recentes, a recuperação do equipamento segue sem confirmação.</p>
            <p v-if="insights?.active_alerts.length && !denied" class="notice" role="status">Havia um alerta em aberto na última consulta. <RouterLink :to="monitoringLocation('/insights')">Ver saúde e previsões</RouterLink></p>
            <div v-if="selectedDevice && !denied && sessionToken" class="workspace">
              <section class="panel scene" aria-label="Visualização do gêmeo digital">
                <h2>{{ selectedDevice.name }}</h2>
                <DigitalTwinScene :key="`${environmentId}:${deviceUuid}`" :paused="animationPaused || dataHidden"
                  :items="items" :selected-id="selectedId" :visual="visual" @update:paused="animationPaused = $event" @select="selectItem" />
              </section>
              <a class="components-jump" href="#twin-components">Ir para a lista de {{ items.length }} componentes</a>
              <section class="panel components-panel" aria-label="Componentes do gêmeo digital">
                <h2 id="twin-components" tabindex="-1">Componentes</h2>
                <ul class="components">
                  <li v-for="item in items" :key="item.key">
                    <button type="button" :aria-pressed="item.id !== null && selectedId === item.id"
                      :disabled="item.id === null" @click="item.id && selectItem(item.id)">
                      <strong>{{ item.label }}</strong>
                      <span class="component-value" :data-state="item.status">{{ itemReading(item) }}</span>
                    </button>
                  </li>
                </ul>
                <details class="state-help">
                  <summary>Como interpretar os estados</summary>
                  <p>A temperatura ambiente usa os limites configurados para o ambiente. Os outros sensores mostram o valor medido.</p>
                  <p>A leitura mostra se o ventilador está em operação. A previsão e os alertas indicam Normal, Atenção ou Crítico. A luz e o som de aviso seguem a última leitura recente.</p>
                </details>
              </section>
              <TwinItemPanel v-if="selected && scopedSummary" :key="`${environmentId}:${deviceUuid}`"
                :item="selected" :summary="scopedSummary" :device="selectedDevice" :token="sessionToken" :fresh="fresh"
                :age-seconds="ageSeconds" :revision="refreshRevision" :connection-state="connectionState" />
              <section v-else class="panel inspection-placeholder" aria-labelledby="inspection-title">
                <h2 id="inspection-title">Componente selecionado</h2>
                <p>{{ hasSelectableItems ? 'Escolha uma peça na cena ou na lista.' : 'Aguardando a identificação das peças deste dispositivo.' }}</p>
              </section>
            </div>
          </LiveDataRegion>
        </div>
      </template>
    </div>
  </main>
</template>

<style scoped>
.digital-twin { min-height: 100vh; padding: var(--cs-space-48); color: var(--cs-color-ink); background: var(--cs-color-canvas); }
.shell { max-width: 1280px; margin: auto; display: grid; gap: var(--cs-space-16); min-width: 0; }
a, button { color: var(--cs-color-accent); }button { min-height: var(--cs-control-min-height); cursor: pointer; }button:disabled { cursor: default; }a:hover { text-decoration: underline; }:is(a, button, select, summary, h2):focus-visible { outline: 3px solid var(--cs-focus-ring); outline-offset: 3px; }
h2 { font-size: var(--cs-type-20); font-weight: 600; }
.panel { min-width: 0; padding: var(--cs-space-16); background: var(--cs-color-surface); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); }
p { margin-top: var(--cs-space-8); line-height: 1.6; }p, a, button, dd, dt { overflow-wrap: anywhere; }
.context-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--cs-space-24); align-items: end; }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16); }label { display: grid; gap: var(--cs-space-8); font-weight: 600; font-size: var(--cs-type-14); }select { width: 100%; min-width: 0; min-height: var(--cs-control-min-height); padding: var(--cs-space-8); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); }
.connection { font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }.connection-label { padding: var(--cs-space-4) var(--cs-space-8); background: var(--cs-color-stale-surface); color: var(--cs-color-status-stale); border-radius: var(--cs-radius-4); }.connection-label.connected { background: var(--cs-color-normal-surface); color: var(--cs-color-status-normal); }
.monitor-status { margin: 0; font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
.notice { padding: var(--cs-space-16); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-stale-surface); color: var(--cs-color-ink); }
.workspace { display: grid; grid-template-columns: minmax(0, 1.24fr) minmax(0, 1fr) minmax(0, 1fr); gap: var(--cs-space-16); align-items: start; }
.scene h2 { margin-bottom: var(--cs-space-12); overflow-wrap: anywhere; }
.scene :deep(.scene-wrap) { max-width: 440px; margin-inline: auto; }
.scene :deep(.scene) { height: clamp(280px, 24vw, 360px); }
.components-jump { display: none; }
.components { margin-top: var(--cs-space-8); }
.components button { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--cs-space-4) var(--cs-space-8); text-align: left; width: 100%; padding: var(--cs-space-8); border: 1px solid transparent; border-bottom-color: var(--cs-color-line); border-radius: var(--cs-radius-4); color: var(--cs-color-ink); font-size: var(--cs-type-14); }
.components button:hover:enabled { background: var(--cs-color-surface-muted); }
.components button[aria-pressed=true] { border-color: var(--cs-color-accent); background: var(--cs-color-surface-muted); }
.components button:disabled, .inspection-placeholder p { color: var(--cs-color-ink-muted); }
.components strong { font-weight: 600; }
.component-value { font-variant-numeric: tabular-nums; }
.component-value[data-state=critical] { color: var(--cs-color-status-critical); }
.component-value[data-state=attention] { color: var(--cs-color-status-attention); }
.state-help, .inspection-placeholder p { font-size: var(--cs-type-14); }
.state-help summary { min-height: var(--cs-control-min-height); display: list-item; align-content: center; cursor: pointer; color: var(--cs-color-accent); }
.state-help p { color: var(--cs-color-ink-muted); }
#twin-components { scroll-margin-top: var(--cs-space-24); }
@media (max-width: 1200px) {
  .workspace { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .workspace > :last-child { grid-column: 1 / -1; }
}
@media (max-width: 900px) {
  .digital-twin { padding: var(--cs-space-24); }
  .workspace, .context-row { grid-template-columns: minmax(0, 1fr); }
  .connection { display: flex; flex-wrap: wrap; gap: var(--cs-space-12); align-items: center; }
  .connection p { margin-top: 0; }
  .components-jump { display: flex; align-items: center; justify-content: center; min-height: var(--cs-control-min-height); padding: var(--cs-space-12) var(--cs-space-16); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); text-align: center; }
}
@media (max-width: 420px) { .digital-twin { padding: var(--cs-space-16); }.fields { grid-template-columns: minmax(0, 1fr); } }
</style>
