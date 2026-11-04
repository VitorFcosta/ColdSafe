<script setup lang="ts">
import LiveDataRegion from '../features/monitoring/LiveDataRegion.vue'
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
const measurements = computed(() => items.value.filter((item) => item.kind === 'sensor'))
function itemCondition(item: TwinItem) {
  return item.kind === 'sensor' && item.key !== 'temperature_c' && item.status === 'normal' ? 'Leitura atual' : statusLabels[item.status]
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
      <header class="page-heading"><h1 id="digital-twin-title" tabindex="-1">Gêmeo digital</h1><p>Explore sensores, atuadores e equipamento pelos seus identificadores reais.</p></header>
      <template v-if="!aiotEnabled">
        <AreaNavigation />
        <section class="notice" aria-label="Gêmeo indisponível no modo legado">
          <p role="status">O gêmeo digital requer AIoT v3 habilitado. Não há inventário de componentes disponível no modo legado.</p>
          <RouterLink data-legacy-exit :to="monitoringLocation('/dashboard')">Ir para a Visão geral</RouterLink>
        </section>
      </template>
      <template v-else>
        <section class="context" aria-label="Selecionar equipamento">
          <div class="context-row">
          <div class="fields">
            <label>Ambiente<select v-model="environmentId" name="environment" :disabled="catalogLoading || !environments.length"><option value="" disabled>Selecione um ambiente</option><option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option></select></label>
            <label>Equipamento<select v-model="deviceUuid" name="device" :disabled="catalogLoading || !devices.length"><option value="" disabled>Selecione um dispositivo</option><option v-for="device in devices" :key="device.id" :value="device.id">{{ device.name }}</option></select></label>
          </div>
          <div v-if="selectedDevice && !denied" v-show="!dataHidden" class="connection">
            <p class="connection-label" :class="{ connected: connectionState === 'connected' }">{{ connectionState === 'connected' ? 'Servidor conectado' : 'Conexão não confirmada' }}</p>
            <p>{{ scopedSummary?.reading ? formatFreshness(ageSeconds ?? undefined) : 'Sem leitura recebida' }}</p>
          </div>
          </div>
          <p v-if="selectionNotice" role="status">{{ selectionNotice }}</p>
          <p v-if="catalogFailed" role="alert">Não foi possível carregar o catálogo. <button type="button" @click="loadEnvironments">Tentar novamente</button></p>
          <p v-else-if="catalogLoading" role="status">Carregando equipamentos autorizados…</p>
          <p v-else-if="!environments.length" role="status">Nenhum ambiente autorizado. <RouterLink to="/manage">Gerenciar ambientes</RouterLink></p>
          <p v-else-if="!devices.length" role="status">Nenhum equipamento ativo neste ambiente.</p>
        </section>
        <AreaNavigation />
        <LiveDataRegion v-model="dataHidden" :reset-key="deviceUuid">
        <p v-if="selectedDevice && (denied || !fresh || !scopedSummary)" class="monitor-status notice" role="status" aria-live="polite">{{ monitorMessage }}</p>
        <p v-if="insightsFailed && !denied" class="notice" role="alert">Não foi possível atualizar os Insights. O estado preditivo não está confirmado; ausência de dados não significa recuperação.</p>
        <p v-if="insights?.active_alerts.length && !denied" class="notice" role="status">Alerta preditivo persistente na última consulta confirmada. Ausência de dados não significa encerramento. <RouterLink :to="monitoringLocation('/insights')">Consultar Insights</RouterLink></p>
        <template v-if="selectedDevice && !denied && sessionToken">
          <section class="measurements" aria-label="Grandezas do equipamento">
            <dl><div v-for="item in measurements" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd><dd class="condition" :data-state="item.status">{{ itemCondition(item) }}</dd></div></dl>
          </section>
          <div class="workspace">
            <div class="scene-column">
              <section class="panel scene" aria-label="Visualização do gêmeo digital">
                <h2>{{ selectedDevice.name }}</h2><p class="scene-description">Representação ilustrativa · câmera fixa</p>
                <DigitalTwinScene :key="`${environmentId}:${deviceUuid}`" :paused="animationPaused || dataHidden" @update:paused="animationPaused = $event" :items="items" :selected-id="selectedId" :visual="visual" @select="selectItem" />
              </section>
              <section class="selected-reading" aria-label="Leitura selecionada">
                <template v-if="selected"><h2>{{ selected.label }}</h2><p class="selected-value">{{ selected.value }}</p><p>{{ itemCondition(selected) }} · {{ formatFreshness(ageSeconds ?? undefined) }}</p><p class="identifier">ID: {{ selected.id }}</p></template>
                <p v-else>Selecione um componente na cena ou na lista para consultar sua leitura.</p>
              </section>
              <a class="components-jump" href="#twin-components">Ir para a lista de {{ items.length }} componentes</a>
            </div>
            <section class="panel components-panel" aria-label="Componentes do gêmeo digital">
              <h2 id="twin-components" tabindex="-1">Componentes <span>· {{ items.length }}</span></h2>
              <p>A lista oferece os mesmos componentes e estados da cena e pode ser usada pelo teclado.</p>
              <ul class="components"><li v-for="item in items" :key="item.key"><button type="button" :aria-pressed="item.id !== null && selectedId === item.id" :disabled="item.id === null" @click="item.id && selectItem(item.id)"><strong>{{ item.label }}</strong><span class="component-value">{{ item.value }} · {{ itemCondition(item) }}</span><span class="identifier">ID: {{ item.id ?? 'Sem identificador confirmado' }}</span></button></li></ul>
              <details class="state-help"><summary>Como interpretar os estados</summary>
                <p>As faixas de temperatura ambiente vêm das regras do ambiente. Os demais sensores não têm faixas operacionais configuradas; seus valores não confirmam operação segura.</p>
                <p>O estado preditivo do ventilador aparece na lista e no painel, conforme os alertas persistentes e as faixas de recuperação; sem previsão confirmada fica sem dados. Os materiais do modelo são ilustrativos. LED e buzzer mostram o estado observado na telemetria.</p>
              </details>
            </section>
          </div>
          <TwinItemPanel v-if="selected && scopedSummary && selectedDevice" :key="`${environmentId}:${deviceUuid}`" :item="selected" :summary="scopedSummary" :device="selectedDevice" :token="sessionToken" :fresh="fresh" :age-seconds="ageSeconds" :revision="refreshRevision" :connection-state="connectionState" />
        </template>
        </LiveDataRegion>
      </template>
    </div>
  </main>
</template>

<style scoped>
.digital-twin { min-height: 100vh; padding: var(--cs-space-48); color: var(--cs-color-ink); background: var(--cs-color-canvas); }
.shell { max-width: 1280px; margin: auto; display: grid; gap: var(--cs-space-24); min-width: 0; }
a, button { color: var(--cs-color-accent); }button { min-height: var(--cs-control-min-height); cursor: pointer; }button:disabled { cursor: default; }a:hover { text-decoration: underline; }:is(a, button, select, summary, h2):focus-visible { outline: 3px solid var(--cs-focus-ring); outline-offset: 3px; }
h1 { font-size: var(--cs-type-32); }h2 { font-size: var(--cs-type-20); }h1, h2 { font-weight: 600; }
.panel, .selected-reading { min-width: 0; padding: var(--cs-space-24); background: var(--cs-color-surface); border-radius: var(--cs-radius-panel); }
p { margin-top: var(--cs-space-8); line-height: 1.6; }p, a, button, dd, dt { overflow-wrap: anywhere; }.page-heading p { color: var(--cs-color-ink-muted); }
.context-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--cs-space-24); align-items: end; }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16); }label { display: grid; gap: var(--cs-space-8); font-weight: 600; font-size: var(--cs-type-14); }select { width: 100%; min-width: 0; min-height: var(--cs-control-min-height); padding: var(--cs-space-8); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); }
.connection { font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }.connection-label { padding: var(--cs-space-4) var(--cs-space-8); background: var(--cs-color-stale-surface); color: var(--cs-color-status-stale); border-radius: var(--cs-radius-4); }.connection-label.connected { background: var(--cs-color-normal-surface); color: var(--cs-color-status-normal); }
.shell :deep(.local-navigation) { margin-bottom: 0; }.monitor-status { margin: 0; font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
.notice { padding: var(--cs-space-16); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-stale-surface); color: var(--cs-color-ink); }
.measurements dl { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: var(--cs-space-8); }.measurements dl > div { min-width: 0; padding: var(--cs-space-12); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }.measurements dt { font-size: var(--cs-type-12); }.measurements dd { margin-top: var(--cs-space-12); font-size: var(--cs-type-24); font-weight: 600; font-variant-numeric: tabular-nums; }.measurements .condition { margin-top: var(--cs-space-8); font-size: var(--cs-type-12); font-weight: 400; color: var(--cs-color-ink-muted); }
.condition[data-state=critical] { color: var(--cs-color-status-critical); }.condition[data-state=attention] { color: var(--cs-color-status-attention); }
.workspace { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr); gap: var(--cs-space-24); align-items: start; }.scene-column { min-width: 0; display: grid; gap: var(--cs-space-16); }.scene-description { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); margin-bottom: var(--cs-space-16); }.scene { padding: var(--cs-space-16); }
.scene :deep(.scene-wrap) { width: 100%; max-width: clamp(280px, 24vw, 360px); margin-inline: auto; }.scene :deep(.scene) { height: clamp(280px, 24vw, 360px); }.scene :deep(canvas) { max-width: 100%; }
.selected-reading, .components-jump { display: none; }.components-panel h2 span { color: var(--cs-color-ink-muted); }.components-panel > p { font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
.components { display: grid; gap: var(--cs-space-4); margin-top: var(--cs-space-16); }.components button { display: grid; gap: var(--cs-space-4); text-align: left; width: 100%; padding: var(--cs-space-12); border: 1px solid transparent; border-bottom-color: var(--cs-color-line); border-radius: var(--cs-radius-4); color: var(--cs-color-ink); font-size: var(--cs-type-14); }.components button:hover:enabled { background: var(--cs-color-surface-muted); }.components button[aria-pressed=true] { border-color: var(--cs-color-accent); background: var(--cs-color-surface-muted); }.components button:disabled { color: var(--cs-color-ink-muted); }.components strong { font-weight: 600; }.component-value { font-variant-numeric: tabular-nums; }.identifier { font-size: var(--cs-type-12); color: var(--cs-color-ink-muted); overflow-wrap: anywhere; }
.state-help { margin-top: var(--cs-space-16); font-size: var(--cs-type-14); }.state-help summary { min-height: var(--cs-control-min-height); display: list-item; align-content: center; cursor: pointer; color: var(--cs-color-accent); }.state-help p { color: var(--cs-color-ink-muted); }#twin-components { scroll-margin-top: var(--cs-space-24); }
@media (max-width: 1200px) { .measurements dl { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) { .digital-twin { padding: var(--cs-space-24); }.workspace { grid-template-columns: minmax(0, 1fr); }.panel, .selected-reading { padding: var(--cs-space-16); }.context-row { grid-template-columns: minmax(0, 1fr); }.connection { display: flex; flex-wrap: wrap; gap: var(--cs-space-12); align-items: center; }.connection p { margin-top: 0; }.measurements { display: none; }.selected-reading { display: block; }.selected-reading .selected-value { font-size: var(--cs-type-32); font-weight: 600; font-variant-numeric: tabular-nums; }.components-jump { display: flex; align-items: center; justify-content: center; min-height: var(--cs-control-min-height); padding: var(--cs-space-12) var(--cs-space-16); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); text-align: center; } }
@media (max-width: 420px) { .digital-twin { padding: var(--cs-space-16); }.fields { grid-template-columns: minmax(0, 1fr); }h1 { font-size: var(--cs-type-24); } }
</style>
