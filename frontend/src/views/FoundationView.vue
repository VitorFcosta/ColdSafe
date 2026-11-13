<script setup lang="ts">
import LiveDataRegion from '../features/monitoring/LiveDataRegion.vue'
import MonitoringEmptyState from '../features/monitoring/MonitoringEmptyState.vue'
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useMonitoringContext } from '../features/monitoring/use-monitoring-context'
import { clearSession, dashboardSelection, saveDashboardSelection, sessionToken } from '../features/account/session'
import AlertsComparisonPanel from '../features/monitoring/AlertsComparisonPanel.vue'
import LedControl from '../features/monitoring/LedControl.vue'
import { actuatorLabel, useActuators } from '../features/monitoring/use-actuators'
import TemperatureHistoryChart from '../features/monitoring/TemperatureHistoryChart.vue'
import PredictionPanel from '../features/monitoring/PredictionPanel.vue'
import {
  fetchMonitoringHistory, historyPeriods, type HistoryPeriod, type MonitoringHistory,
} from '../features/monitoring/monitoring-history'
import { formatFreshness, useMonitoringSummary, type MonitoringEvent } from '../features/monitoring/use-monitoring-summary'
import { aiotEnabled } from '../features/monitoring/monitoring-version'
import AreaNavigation from '../features/navigation/AreaNavigation.vue'
import { sensorMetrics, type SensorMetricKey } from '../features/monitoring/sensor-metrics'
import { monitoringPollingIntervalMs } from '../features/monitoring/monitoring-polling'
import type { Prediction } from '../features/monitoring/aiot-api'

const dataHidden = ref(false)
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const router = useRouter()
const restoredSelection = dashboardSelection.value
const { environments, devices, environmentId: selectedEnvironmentId, deviceUuid: selectedDeviceUuid,
  selectedDevice, selectionNotice, catalogPhase, loadEnvironments, revokeSelection } = useMonitoringContext()
const selectedMqttId = computed(() => selectedDevice.value?.mqtt_device_id ?? null)
const selectedActuatorId = computed(() => aiotEnabled ? selectedMqttId.value : selectedDeviceUuid.value)
const selectedMetric = ref<SensorMetricKey>('temperature_c')
const availableMetrics = sensorMetrics
const selectedMetricLabel = computed(() => sensorMetrics.find((metric) => metric.key === selectedMetric.value)!.label)
const selectedPeriod = ref<HistoryPeriod>(historyPeriods.find((period) => period === restoredSelection?.period) ?? '1h')
const history = ref<MonitoringHistory | null>(null)
const historyPhase = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const eventsRevision = ref(0)
let latestHistoryRequest = 0
let historyController: AbortController | null = null
let historyRefreshTimer: ReturnType<typeof setTimeout> | null = null

const legacyActuatorEvent = ref<MonitoringEvent | null>(null)
const streamedPrediction = ref<Prediction | null>(null)
watch([sessionToken, selectedMqttId], () => { streamedPrediction.value = null }, { flush: 'sync' })
function handleEvent(event: MonitoringEvent) {
  if (event.schema_version === 3) {
    if (event.type === 'prediction') {
      const previous = streamedPrediction.value
      if (previous) {
        const difference = Date.parse(event.data.input_received_at) - Date.parse(previous.data.input_received_at)
        if (difference < 0 || (difference === 0 && Date.parse(event.occurred_at) < Date.parse(previous.occurred_at))) return
      }
      streamedPrediction.value = event
    }
    return
  }
  eventsRevision.value += 1
  legacyActuatorEvent.value = event
}

const { loadSummary, monitoringState, refreshRevision, summary, connectionState, ageSeconds } =
  useMonitoringSummary(sessionToken, selectedMqttId, handleEvent)
const { led, buzzer, actuatorPhase, commandError, commandSubmitting, loadActuators, toggleLed } =
  useActuators(sessionToken, selectedActuatorId, refreshRevision, connectionState, legacyActuatorEvent)

watch(connectionState, (state) => {
  if (state === 'forbidden') revokeSelection()
  if (state === 'unauthorized') {
    clearSession()
    void router.push('/login')
  }
})

const stateDetails = computed(() => {
  switch (monitoringState.value.kind) {
    case 'normal': return { label: 'Normal', message: 'Temperatura dentro da faixa configurada.', tone: 'normal' }
    case 'attention': return { label: 'Atenção', message: 'Temperatura perto de um limite. Confira a próxima leitura e as condições do ambiente.', tone: 'attention' }
    case 'critical': return { label: 'Crítico', message: 'Temperatura fora da faixa configurada. Verifique o ambiente e o sensor.', tone: 'critical' }
    case 'stale': return { label: 'Leitura desatualizada', message: 'A última leitura não confirma a temperatura de agora. Verifique o dispositivo e aguarde uma nova leitura.', tone: 'stale' }
    case 'no_data': return { label: 'Sem dados', message: 'Ainda não recebemos uma leitura válida. Verifique se o dispositivo está ativo e enviando dados.', tone: 'stale' }
    default: return null
  }
})

const formattedFreshness = computed(() => formatFreshness(ageSeconds.value ?? undefined))
const formattedReceivedAt = computed(() => formatDateTime(summary.value?.reading?.received_at))
const actuatorObservation = computed(() => {
  const snapshot = summary.value
  if (!snapshot?.equipment || !snapshot.reading || snapshot.device.id !== selectedMqttId.value ||
      snapshot.environment.id !== selectedEnvironmentId.value) return
  return { equipment: snapshot.equipment, receivedAt: snapshot.reading.received_at }
})
const measurements = computed(() => sensorMetrics.map((metric) => ({
  ...metric,
  raw: summary.value?.reading?.[metric.key],
  value: formatMeasurement(summary.value?.reading?.[metric.key], metric.unit,
    ['vibration_rms_mm_s', 'motor_current_a'].includes(metric.key) ? 3 : 1),
})))

onUnmounted(() => {
  latestHistoryRequest += 1
  historyController?.abort()
  if (historyRefreshTimer !== null) clearTimeout(historyRefreshTimer)
})

watch([selectedEnvironmentId, selectedDeviceUuid, selectedPeriod, catalogPhase], () => {
  if (catalogPhase.value !== 'ready' || !selectedDevice.value) return
  saveDashboardSelection({
    environmentId: selectedEnvironmentId.value,
    deviceUuid: selectedDeviceUuid.value,
    period: selectedPeriod.value,
  })
})

watch([sessionToken, selectedMqttId, selectedPeriod], ([token, deviceId]) => {
  latestHistoryRequest += 1
  historyController?.abort()
  historyController = null
  if (historyRefreshTimer !== null) clearTimeout(historyRefreshTimer)
  historyRefreshTimer = null
  history.value = null
  historyPhase.value = 'idle'
  if (token && deviceId) void loadHistory(deviceId)
})

function scheduleHistoryRefresh() {
  if (historyRefreshTimer !== null || !sessionToken.value || !selectedMqttId.value) return
  historyRefreshTimer = setTimeout(() => {
    historyRefreshTimer = null
    if (historyController !== null) scheduleHistoryRefresh()
    else if (selectedMqttId.value) void loadHistory(selectedMqttId.value)
  }, monitoringPollingIntervalMs)
}

watch(refreshRevision, scheduleHistoryRefresh)

async function loadHistory(deviceId: string) {
  const token = sessionToken.value
  if (!token || historyController !== null) return
  if (historyRefreshTimer !== null) clearTimeout(historyRefreshTimer)
  historyRefreshTimer = null
  const controller = new AbortController()
  historyController = controller
  const requestId = ++latestHistoryRequest
  historyPhase.value = history.value === null ? 'loading' : 'ready'
  try {
    const result = await fetchMonitoringHistory({
      baseUrl: apiBaseUrl, deviceId, period: selectedPeriod.value, token,
      fetcher: (input, init) => fetch(input, { ...init, signal: controller.signal }),
    })
    if (controller.signal.aborted || requestId !== latestHistoryRequest || selectedMqttId.value !== deviceId || sessionToken.value !== token) return
    if (result.deviceId !== deviceId) throw new Error('Dispositivo inesperado no histórico.')
    history.value = result
    historyPhase.value = 'ready'
  } catch {
    if (controller.signal.aborted || requestId !== latestHistoryRequest) return
    historyPhase.value = 'error'
  } finally {
    if (historyController === controller) historyController = null
  }
}

watch(refreshRevision, () => { eventsRevision.value += 1 })

function formatMeasurement(value: number | null | undefined, unit: string, precision = 1) {
  return value == null ? '—' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: precision })} ${unit}`
}

function formatDateTime(value: string | undefined) {
  if (value === undefined) return '—'

  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short',
  }).format(new Date(value))
}
</script>

<template>
  <main class="dashboard min-h-screen bg-canvas text-ink">
    <div class="dashboard-shell">

      <section aria-labelledby="dashboard-title">
        <header class="area-heading dashboard-heading">
          <h1 id="dashboard-title" tabindex="-1">Visão geral</h1>
          <AreaNavigation />
        </header>

        <section class="panel selection-panel" aria-label="Selecionar ambiente e dispositivo">
          <div class="selection-fields">
            <label>Ambiente
              <select v-model="selectedEnvironmentId" :disabled="catalogPhase === 'loading' || environments.length === 0">
                <option value="" disabled>Selecione um ambiente</option>
                <option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option>
              </select>
            </label>
            <label>Dispositivo
              <select v-model="selectedDeviceUuid" :disabled="devices.every((device) => !device.is_active)">
                <option value="" disabled>Selecione um dispositivo</option>
                <option v-for="device in devices.filter((item) => item.is_active)" :key="device.id" :value="device.id">{{ device.name }} · {{ device.mqtt_device_id }}</option>
              </select>
            </label>
          </div>
          <p v-if="catalogPhase === 'error'" role="alert" class="mt-3 text-sm text-status-critical">Não foi possível carregar ambientes ou dispositivos. <button type="button" class="underline" @click="loadEnvironments">Tentar novamente</button></p>
          <MonitoringEmptyState v-else-if="catalogPhase === 'ready' && environments.length === 0" missing="environment" class="mt-3 text-sm text-ink-muted" />
          <MonitoringEmptyState v-else-if="catalogPhase === 'ready' && selectedEnvironmentId && devices.every((device) => !device.is_active)" missing="device" class="mt-3 text-sm text-ink-muted" />
          <p v-if="selectionNotice" role="status" class="mt-3 text-sm text-ink-muted">{{ selectionNotice }}</p>
          <p v-if="selectedDevice" v-show="!dataHidden" class="mt-3 text-sm text-ink-muted" aria-live="polite">
            Conexão com servidor: {{ connectionState === 'connected' ? 'conectada' : connectionState === 'connecting' ? 'conectando' : connectionState === 'forbidden' ? 'acesso negado' : 'desconectada; tentando reconectar' }}.
            <span v-if="monitoringState.kind === 'stale'">O sensor não enviou leitura recente.</span>
          </p>
        </section>

        <div v-show="selectedDevice" class="contents">
        <LiveDataRegion v-model="dataHidden" :reset-key="selectedMqttId ?? ''">

        <section
          v-if="selectedDevice && monitoringState.kind === 'loading'"
          aria-busy="true"
          aria-label="Carregando diagnóstico atual"
          class="grid gap-6 sm:grid-cols-2"
        >
          <div v-for="index in 2" :key="index" class="h-40 rounded-panel border border-line bg-surface-muted" />
          <p class="text-sm text-ink-muted">Carregando diagnóstico atual…</p>
        </section>

        <section v-else-if="selectedDevice && monitoringState.kind === 'service_error'" role="alert" class="panel border-status-critical mt-6">
          <h2 class="text-xl font-semibold">Diagnóstico indisponível</h2>
          <p class="mt-2 max-w-xl leading-7 text-ink-muted">
            Não foi possível buscar as leituras. O painel não mostra leituras antigas como se fossem atuais.
          </p>
          <button type="button" class="mt-5 rounded-md bg-accent px-4 py-3 font-medium text-accent-ink hover:bg-accent-hover" @click="loadSummary">
            Tentar novamente
          </button>
        </section>

        <section v-else-if="selectedDevice && summary && summary.environment.id !== selectedEnvironmentId" role="alert" class="panel border-status-critical mt-6">
          <h2 class="text-xl font-semibold">Diagnóstico do ambiente indisponível</h2>
          <p class="mt-2 text-ink-muted">O servidor enviou dados de outro ambiente. As leituras desta seleção não serão mostradas.</p>
          <button type="button" class="mt-5 rounded-md bg-accent px-4 py-3 font-medium text-accent-ink hover:bg-accent-hover" @click="loadSummary">Tentar novamente</button>
        </section>

        <template v-else-if="selectedDevice && summary && summary.device.id === selectedMqttId && summary.environment.id === selectedEnvironmentId && stateDetails">
          <section aria-label="Diagnóstico atual" class="status-overview">
            <section aria-label="Medições do ambiente" class="metrics-grid" aria-describedby="reading-origin">
              <article v-for="metric in measurements" :key="metric.key" class="measurement" :data-tone="metric.key === 'temperature_c' ? stateDetails.tone : undefined">
                <h2>{{ metric.label }}</h2>
                <p class="metric-value">{{ metric.value }}</p>
                <template v-if="metric.key === 'temperature_c'">
                  <h3 class="measurement-condition" aria-live="polite">{{ stateDetails.label }}</h3>
                  <p class="measurement-age">{{ formattedFreshness }}</p>
                </template>
                <p v-else class="measurement-condition">{{ metric.raw == null ? 'Sem leitura' : monitoringState.kind === 'stale' ? 'Leitura antiga' : 'Leitura atual' }}</p>
              </article>
            </section>
            <div id="reading-origin" class="reading-meta">
              <p class="reading-condition" :data-tone="stateDetails.tone">{{ stateDetails.message }}</p>
              <p>Última leitura recebida: {{ formattedReceivedAt }}</p>
              <p>Faixa configurada: {{ summary.thresholds.min_c }}–{{ summary.thresholds.max_c }} °C</p>
              <p v-if="summary.persistence" role="status">{{ summary.persistence === 'pending' ? 'Leitura recebida. Falta salvar no histórico.' : 'Leitura salva no histórico.' }}</p>
              <p v-if="summary.equipment">Ventilador na última leitura: {{ summary.equipment.running ? 'Em funcionamento' : 'Parado' }}.</p>
            </div>
          </section>
        </template>

        <AlertsComparisonPanel :auth="sessionToken" :device-id="selectedMqttId" :period="selectedPeriod" :revision="eventsRevision">
          <details v-if="selectedDevice" class="panel actuator-panel" aria-label="Estado da luz e do som de aviso">
            <summary class="actuator-summary">
              <span class="actuator-summary-title">Luz e som de aviso</span>
              <span v-if="actuatorObservation" class="actuator-summary-state text-ink-muted">
                Última leitura: luz {{ actuatorObservation.equipment.led.actual_state ? 'ligada' : 'desligada' }} · som {{ actuatorObservation.equipment.buzzer.actual_state ? 'ligado' : 'desligado' }}<template v-if="ageSeconds !== null"> · {{ formattedFreshness }}</template>.
                <template v-if="monitoringState.kind === 'stale' || ageSeconds === null"> Estado atual não confirmado.</template>
              </span>
              <span v-if="actuatorPhase === 'loading'" class="actuator-summary-state" role="status">Consultando a luz e o som…</span>
              <span v-else-if="actuatorPhase === 'error'" class="actuator-summary-state text-status-critical" role="alert">Não foi possível consultar a luz e o som.</span>
              <span v-else class="actuator-summary-state" aria-live="polite">
                <template v-if="actuatorObservation && !led && !buzzer">Pedidos de luz e som sem confirmação registrada.</template>
                <template v-else>Pedidos · Luz manual: {{ actuatorLabel(led) }} · Som de aviso automático: {{ actuatorLabel(buzzer) }}</template>
              </span>
              <span v-if="commandError" class="actuator-summary-state text-status-critical" role="alert">{{ commandError }}</span>
            </summary>
            <div class="actuator-content">
              <div class="actuator-grid">
                <div>
                  <h3 class="font-medium">Luz manual</h3>
                  <LedControl :led="led" :phase="actuatorPhase" :submitting="commandSubmitting" :error="commandError"
                    :observation="actuatorObservation ? { state: actuatorObservation.equipment.led.actual_state, receivedAt: actuatorObservation.receivedAt, ageSeconds } : undefined"
                    @toggle="toggleLed" @refresh="selectedActuatorId && loadActuators(selectedActuatorId)" />
                </div>
                <div>
                  <h3 class="font-medium">Som de aviso automático</h3>
                  <p class="mt-2" aria-live="polite">{{ actuatorLabel(buzzer) }}</p>
                  <p v-if="actuatorObservation" class="mt-2 text-sm text-ink-muted">Som de aviso na última leitura: {{ actuatorObservation.equipment.buzzer.actual_state ? 'Ligado' : 'Desligado' }}. {{ formattedFreshness }}.</p>
                </div>
              </div>
            </div>
          </details>

          <div v-if="selectedDevice && summary && summary.device.id === selectedMqttId && summary.environment.id === selectedEnvironmentId && stateDetails" class="monitoring-analysis col-span-full">
            <section aria-labelledby="temperature-history-title" class="panel history-panel">
              <h2 id="temperature-history-title" class="text-xl font-semibold">Histórico · {{ selectedMetricLabel.toLocaleLowerCase('pt-BR') }}</h2>
              <div class="history-controls">
                <fieldset aria-label="Período do histórico">
                  <legend>Período</legend>
                  <div class="period-control">
                    <button
                      v-for="period in historyPeriods"
                      :key="period"
                      type="button"
                      :aria-pressed="selectedPeriod === period"
                      @click="selectedPeriod = period"
                    >
                      {{ period }}
                    </button>
                  </div>
                </fieldset>
                <label>Medição do gráfico
                  <select v-model="selectedMetric" aria-label="Medição do gráfico">
                    <option v-for="metric in availableMetrics" :key="metric.key" :value="metric.key">{{ metric.label }} ({{ metric.unit }})</option>
                  </select>
                </label>
              </div>
              <p class="mt-3 text-sm text-ink-muted">O período vale para o histórico, os alertas e a comparação. A medição muda só este gráfico.</p>
              <p v-if="historyPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">
                Carregando histórico de {{ selectedMetricLabel.toLocaleLowerCase('pt-BR') }}…
              </p>
              <TemperatureHistoryChart v-if="history" :readings="history.readings" :period="selectedPeriod" :start="history.start" :end="history.end" :limit="history.limit" :thresholds="summary.thresholds" :metric="selectedMetric" />
              <p v-if="historyPhase === 'error'" class="history-error mt-5 text-sm leading-6" role="status">
                {{ history ? 'Não foi possível atualizar o histórico. Exibindo a última consulta concluída.' : 'O diagnóstico atual continua disponível, mas o histórico não pôde ser carregado.' }}
                <button type="button" class="min-h-11 font-medium text-accent underline" @click="selectedMqttId && loadHistory(selectedMqttId)">Tentar novamente</button>
              </p>
            </section>

            <PredictionPanel v-if="aiotEnabled" :summary="summary" :age-seconds="ageSeconds" :streamed-prediction="streamedPrediction" />
          </div>
        </AlertsComparisonPanel>

        <p v-if="selectedDevice" class="mt-8 text-xs leading-6 text-ink-muted">O painel atualiza sozinho e busca as leituras mais recentes quando a conexão volta.</p>
        </LiveDataRegion>
        </div>
      </section>
      <footer class="mt-8 border-t border-line pt-6 text-xs leading-6 text-ink-muted">
        Protótipo acadêmico: não é equipamento médico, sanitário ou regulatório certificado.
      </footer>
    </div>
  </main>
</template>

<style scoped>
.dashboard { padding: var(--cs-space-48); }
.dashboard-shell { max-width: 1280px; margin-inline: auto; }

.dashboard-heading { margin-bottom: var(--cs-space-24); }
.panel { min-width: 0; padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.panel[role="alert"] { border-color: var(--cs-color-status-critical); }
.selection-panel { background: transparent; border: 0; padding: 0; margin-bottom: var(--cs-space-16); }
.selection-fields, .actuator-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); }
.selection-fields label { display: grid; gap: var(--cs-space-8); font-size: var(--cs-type-14); font-weight: 600; }
.selection-fields select { min-height: 44px; min-width: 0; padding: var(--cs-space-8); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); }
.actuator-grid { margin-top: var(--cs-space-24); }
.actuator-panel { padding: var(--cs-space-12) var(--cs-space-16); overflow-wrap: anywhere; }
.actuator-summary { min-height: 44px; cursor: pointer; }
.actuator-summary-title { margin-left: var(--cs-space-4); font-weight: 600; }
.actuator-summary-state { display: block; margin-top: var(--cs-space-4); font-size: var(--cs-type-14); line-height: 1.5; }
.actuator-content { margin-top: var(--cs-space-24); padding-top: var(--cs-space-24); border-top: 1px solid var(--cs-color-line); }
.metrics-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cs-space-12); }
.measurement { min-width: 0; padding: var(--cs-space-16); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); overflow-wrap: anywhere; }
.measurement h2 { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); font-weight: 600; line-height: 1.5; }
.metric-value { margin-top: var(--cs-space-16); font-size: var(--cs-type-24); line-height: 1.3; font-weight: 650; }
.measurement-condition { margin-top: var(--cs-space-8); color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); line-height: 1.5; }
.measurement-age { color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); line-height: 1.5; }
[data-tone='normal'] { --status-color: var(--cs-color-status-normal); }
[data-tone='attention'] { --status-color: var(--cs-color-status-attention); }
[data-tone='critical'] { --status-color: var(--cs-color-status-critical); }
[data-tone='stale'] { --status-color: var(--cs-color-status-stale); }
.measurement[data-tone] { background: var(--cs-color-surface-muted); }
.measurement[data-tone] .metric-value { font-size: var(--cs-type-32); }
.measurement[data-tone] .measurement-condition, .reading-condition { color: var(--status-color); }
.reading-meta { display: flex; flex-wrap: wrap; gap: var(--cs-space-8) var(--cs-space-24); margin-block: var(--cs-space-16) var(--cs-space-24); color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); line-height: 1.5; }
.reading-condition { width: 100%; }
.monitoring-analysis { display: grid; grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr); align-items: start; gap: var(--cs-space-24); }
.monitoring-analysis > :only-child { grid-column: 1 / -1; }
.monitoring-analysis :deep(.prediction-panel) { margin-top: 0; }
.monitoring-analysis :deep(.prediction-values), .monitoring-analysis :deep(.prediction-meta) { grid-template-columns: minmax(0, 1fr); }
.history-panel { min-width: 0; padding: var(--cs-space-24); }
.history-error { padding: var(--cs-space-16); border: 1px solid var(--cs-color-status-stale); border-radius: var(--cs-radius-8); background: var(--cs-color-stale-surface); color: var(--cs-color-status-stale); }
@media (min-width: 80rem) { .metrics-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
@media (max-width: 74rem) { .monitoring-analysis { grid-template-columns: minmax(0, 1fr); } }
.history-controls { display: flex; flex-wrap: wrap; align-items: end; gap: var(--cs-space-12) var(--cs-space-24); margin-top: var(--cs-space-16); }
.history-controls fieldset, .history-controls label { min-width: 0; max-width: 100%; }
.history-controls label, .history-controls legend { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); font-weight: 600; }
.history-controls legend { margin-bottom: var(--cs-space-8); }
.history-controls select { display: block; width: 100%; min-height: calc(var(--cs-control-min-height) + 2 * var(--cs-space-4)); margin-top: var(--cs-space-8); padding: var(--cs-space-8); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); color: var(--cs-color-ink); }
.period-control { display: flex; flex-wrap: wrap; min-width: 0; padding: var(--cs-space-4); border-radius: var(--cs-radius-4); background: var(--cs-color-surface-muted); }
.period-control button { flex: 1 0 auto; min-width: max-content; min-height: 44px; padding: var(--cs-space-8) var(--cs-space-16); border-radius: var(--cs-radius-4); font-size: var(--cs-type-14); transition: background-color var(--cs-motion-quick); cursor: pointer; }
.period-control button:hover { background: var(--cs-color-line); }
.period-control button[aria-pressed='true'] { background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
@media (max-width: 767px) {
  .dashboard { padding: var(--cs-space-24); }
  .dashboard-heading { margin-bottom: var(--cs-space-16); }
  .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-12); }
  .selection-fields { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-12); }
  .actuator-grid { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-16); }
  .panel, .history-panel { padding: var(--cs-space-16); }
  .selection-panel { margin-bottom: var(--cs-space-16); }
  .history-panel { margin-top: var(--cs-space-16); }
  .metric-value { margin-top: var(--cs-space-12); }
}
@media (max-width: 374px) {
  .dashboard { padding: var(--cs-space-16); }

  .selection-fields { grid-template-columns: minmax(0, 1fr); }
  .measurement { padding: var(--cs-space-12); }
}
</style>
