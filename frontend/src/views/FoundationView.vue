<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { listDevices, listEnvironments, type Device, type Environment } from '../features/account/catalog'
import { clearSession, dashboardSelection, logout, saveDashboardSelection, sessionToken } from '../features/account/session'
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
import { sensorMetrics, type SensorMetricKey } from '../features/monitoring/sensor-metrics'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const diagnosticsEnabled = import.meta.env.VITE_DIAGNOSTICS_ENABLED === 'true'
const rabbitmqManagementUrl = `http://${window.location.hostname}:15672`
const router = useRouter()
const restoredSelection = dashboardSelection.value
const environments = ref<Environment[]>([])
const devices = ref<Device[]>([])
const selectedEnvironmentId = ref(restoredSelection?.environmentId ?? '')
const selectedDeviceUuid = ref('')
const selectionNotice = ref('')
const catalogPhase = ref<'loading' | 'ready' | 'error'>('loading')
const selectedDevice = computed(() => devices.value.find((item) => item.id === selectedDeviceUuid.value && item.is_active))
const selectedMqttId = computed(() => selectedDevice.value?.mqtt_device_id ?? null)
const selectedActuatorId = computed(() => aiotEnabled ? selectedMqttId.value : selectedDeviceUuid.value)
const selectedMetric = ref<SensorMetricKey>('temperature_c')
const availableMetrics = computed(() => sensorMetrics.filter((metric) =>
  aiotEnabled || summary.value?.equipment || ['temperature_c', 'humidity_percent', 'light_percent'].includes(metric.key)))
const selectedPeriod = ref<HistoryPeriod>(historyPeriods.find((period) => period === restoredSelection?.period) ?? '1h')
const history = ref<MonitoringHistory | null>(null)
const historyPhase = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const logoutError = ref('')
const eventsRevision = ref(0)
let latestCatalogRequest = 0
let latestHistoryRequest = 0
let catalogRetryTimer: ReturnType<typeof setTimeout> | null = null

const legacyActuatorEvent = ref<MonitoringEvent | null>(null)
function handleEvent(event: MonitoringEvent) {
  if (event.schema_version === 3) return
  eventsRevision.value += 1
  legacyActuatorEvent.value = event
}

const { loadSummary, monitoringState, refreshRevision, summary, connectionState, ageSeconds } =
  useMonitoringSummary(sessionToken, selectedMqttId, handleEvent)
const { led, buzzer, actuatorPhase, commandError, commandSubmitting, loadActuators, toggleLed } =
  useActuators(sessionToken, selectedActuatorId, refreshRevision, connectionState, legacyActuatorEvent)

watch(connectionState, (state) => {
  if (state === 'unauthorized') {
    clearSession()
    void router.push('/login')
  }
})

const stateDetails = computed(() => {
  switch (monitoringState.value.kind) {
    case 'normal': return { label: 'Normal', message: 'Temperatura dentro da faixa configurada.', tone: 'normal' }
    case 'attention': return { label: 'Atenção', message: 'Temperatura próxima de um limite configurado. Confira a próxima leitura e as condições do ambiente.', tone: 'attention' }
    case 'critical': return { label: 'Crítico', message: 'Temperatura fora da faixa configurada. Verifique o ambiente e o sensor.', tone: 'critical' }
    case 'stale': return { label: 'Leitura desatualizada', message: 'Última leitura conhecida. A situação atual não está confirmada. Verifique o dispositivo e aguarde uma leitura nova.', tone: 'stale' }
    case 'no_data': return { label: 'Sem dados', message: 'Ainda não há leitura válida para este dispositivo. Verifique se ele está ativo e enviando dados.', tone: 'stale' }
    default: return null
  }
})

const formattedTemperature = computed(() => formatMeasurement(summary.value?.reading?.temperature_c, '°C'))
const formattedHumidity = computed(() => formatMeasurement(summary.value?.reading?.humidity_percent, '%'))
const formattedLight = computed(() => formatMeasurement(summary.value?.reading?.light_percent ?? undefined, '%'))
const formattedFreshness = computed(() => formatFreshness(ageSeconds.value ?? undefined))
const formattedReceivedAt = computed(() => formatDateTime(summary.value?.reading?.received_at))
const motorMetrics = computed(() => sensorMetrics.slice(3).map((metric) => ({
  ...metric, value: formatMeasurement(summary.value?.reading?.[metric.key], metric.unit, 3),
})))

onMounted(() => { void loadEnvironments() })
onUnmounted(() => {
  latestCatalogRequest += 1
  if (catalogRetryTimer !== null) clearTimeout(catalogRetryTimer)
})

function retryCatalog(load: () => void) {
  if (catalogRetryTimer !== null || !sessionToken.value) return
  catalogRetryTimer = setTimeout(() => {
    catalogRetryTimer = null
    if (sessionToken.value) load()
  }, 2000)
}

async function handleLogout() {
  logoutError.value = ''
  try {
    await logout()
    await router.push('/login')
  } catch {
    logoutError.value = 'Não foi possível encerrar a sessão. Tente novamente.'
  }
}

async function loadEnvironments() {
  const token = sessionToken.value
  if (!token) return
  if (catalogRetryTimer !== null) clearTimeout(catalogRetryTimer)
  catalogRetryTimer = null
  const requestId = ++latestCatalogRequest
  catalogPhase.value = 'loading'
  try {
    const result = await listEnvironments(token)
    if (requestId !== latestCatalogRequest) return
    environments.value = result
    const previousEnvironmentId = selectedEnvironmentId.value
    const environmentStillAvailable = result.some((item) => item.id === previousEnvironmentId)
    selectedEnvironmentId.value = environmentStillAvailable ? previousEnvironmentId : (result[0]?.id ?? '')
    if (restoredSelection?.environmentId && !environmentStillAvailable) {
      selectionNotice.value = 'O ambiente selecionado não está mais disponível. Exibindo o primeiro ambiente autorizado.'
    }
    catalogPhase.value = 'ready'
    if (selectedEnvironmentId.value === previousEnvironmentId && devices.value.length === 0 && previousEnvironmentId) {
      void loadDevices(previousEnvironmentId)
    }
  } catch {
    if (requestId !== latestCatalogRequest) return
    catalogPhase.value = 'error'
    retryCatalog(() => { void loadEnvironments() })
  }
}

watch(selectedEnvironmentId, (environmentId) => { void loadDevices(environmentId) })

async function loadDevices(environmentId: string) {
  const token = sessionToken.value
  if (catalogRetryTimer !== null) clearTimeout(catalogRetryTimer)
  catalogRetryTimer = null
  const requestId = ++latestCatalogRequest
  devices.value = []
  selectedDeviceUuid.value = ''
  if (!token || !environmentId) return
  catalogPhase.value = 'loading'
  try {
    const result = await listDevices(token, environmentId)
    if (requestId !== latestCatalogRequest) return
    devices.value = result
    const preferredDevice = restoredSelection?.environmentId === environmentId
      ? result.find((item) => item.id === restoredSelection.deviceUuid && item.is_active) : undefined
    selectedDeviceUuid.value = preferredDevice?.id ?? result.find((item) => item.is_active)?.id ?? ''
    if (restoredSelection?.environmentId === environmentId && restoredSelection.deviceUuid && !preferredDevice) {
      selectionNotice.value = selectedDeviceUuid.value
        ? 'O dispositivo selecionado não está mais ativo ou disponível. Exibindo outro dispositivo ativo.'
        : 'O dispositivo selecionado não está mais ativo ou disponível. Nenhum dispositivo ativo neste ambiente.'
    }
    catalogPhase.value = 'ready'
  } catch {
    if (requestId !== latestCatalogRequest) return
    catalogPhase.value = 'error'
    retryCatalog(() => {
      if (selectedEnvironmentId.value === environmentId) void loadDevices(environmentId)
    })
  }
}

watch([selectedEnvironmentId, selectedDeviceUuid, selectedPeriod, catalogPhase], () => {
  if (catalogPhase.value !== 'ready' || !selectedDevice.value) return
  saveDashboardSelection({
    environmentId: selectedEnvironmentId.value,
    deviceUuid: selectedDeviceUuid.value,
    period: selectedPeriod.value,
  })
})

watch([selectedMqttId, selectedPeriod, refreshRevision], ([deviceId]) => {
  latestHistoryRequest += 1
  history.value = null
  historyPhase.value = 'idle'
  if (deviceId) void loadHistory(deviceId)
})

async function loadHistory(deviceId: string) {
  const token = sessionToken.value
  if (!token) return
  const requestId = ++latestHistoryRequest
  historyPhase.value = 'loading'
  try {
    const result = await fetchMonitoringHistory({
      baseUrl: apiBaseUrl, deviceId, period: selectedPeriod.value, token, fetcher: fetch,
    })
    if (requestId !== latestHistoryRequest || selectedMqttId.value !== deviceId) return
    if (result.deviceId !== deviceId) throw new Error('Dispositivo inesperado no histórico.')
    history.value = result
    historyPhase.value = 'ready'
  } catch {
    if (requestId !== latestHistoryRequest) return
    historyPhase.value = 'error'
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
    <a class="skip-link" href="#dashboard-title">Ir para o conteúdo</a>
    <div class="dashboard-shell">
      <header class="dashboard-nav">
        <a href="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</a>
        <nav aria-label="Navegação principal" class="nav-actions">
          <RouterLink to="/dashboard" aria-current="page">Monitoramento</RouterLink>
          <RouterLink to="/insights">Insights</RouterLink><RouterLink to="/digital-twin">Gêmeo digital</RouterLink>
          <RouterLink to="/manage">Ambientes e dispositivos</RouterLink>
          <RouterLink to="/messaging">Mensageria</RouterLink>
          <RouterLink to="/laboratory">Laboratório</RouterLink>
          <RouterLink to="/training">Treinamento</RouterLink><RouterLink to="/assistant">Assistente</RouterLink>
          <a href="/docs" target="_blank" rel="noopener noreferrer">Documentação da API</a>
          <a v-if="diagnosticsEnabled" :href="rabbitmqManagementUrl" target="_blank" rel="noopener noreferrer">RabbitMQ local</a>
        </nav>
        <button class="sign-out" type="button" @click="handleLogout">Sair</button>
      </header>
      <p v-if="logoutError" role="alert" class="mt-4 text-sm text-status-critical">{{ logoutError }}</p>

      <section aria-labelledby="dashboard-title">
        <header class="dashboard-heading">
          <p class="eyebrow">Visão geral</p>
          <h1 id="dashboard-title" tabindex="-1">Diagnóstico do ambiente</h1>
          <p class="mt-2 text-sm text-ink-muted">
            <template v-if="selectedDevice && summary?.device.id === selectedMqttId && summary.environment.id === selectedEnvironmentId">{{ summary.environment.name }} <span aria-hidden="true"> / </span> {{ summary.device.id }}</template>
            <template v-else>Selecione um ambiente e um dispositivo para monitorar.</template>
          </p>
        </header>

        <section class="panel selection-panel" aria-label="Selecionar ambiente e dispositivo">
          <div class="selection-fields">
            <label>Ambiente
              <select v-model="selectedEnvironmentId" :disabled="catalogPhase === 'loading' || environments.length === 0" @change="selectionNotice = ''">
                <option value="" disabled>Selecione um ambiente</option>
                <option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option>
              </select>
            </label>
            <label>Dispositivo
              <select v-model="selectedDeviceUuid" :disabled="devices.every((device) => !device.is_active)" @change="selectionNotice = ''">
                <option value="" disabled>Selecione um dispositivo</option>
                <option v-for="device in devices.filter((item) => item.is_active)" :key="device.id" :value="device.id">{{ device.name }} · {{ device.mqtt_device_id }}</option>
              </select>
            </label>
          </div>
          <p v-if="catalogPhase === 'error'" role="alert" class="mt-3 text-sm text-status-critical">Não foi possível carregar ambientes ou dispositivos. <button type="button" class="underline" @click="loadEnvironments">Tentar novamente</button></p>
          <p v-else-if="catalogPhase === 'ready' && environments.length === 0" class="mt-3 text-sm text-ink-muted">Nenhum ambiente cadastrado. <RouterLink to="/manage" class="underline">Criar ambiente</RouterLink></p>
          <p v-else-if="catalogPhase === 'ready' && selectedEnvironmentId && devices.every((device) => !device.is_active)" class="mt-3 text-sm text-ink-muted">Nenhum dispositivo ativo neste ambiente. <RouterLink to="/manage" class="underline">Gerenciar dispositivos</RouterLink></p>
          <p v-if="selectionNotice" role="status" class="mt-3 text-sm text-ink-muted">{{ selectionNotice }}</p>
          <p v-if="selectedDevice" class="mt-3 text-sm text-ink-muted" aria-live="polite">
            Conexão com servidor: {{ connectionState === 'connected' ? 'conectada' : connectionState === 'connecting' ? 'conectando' : connectionState === 'forbidden' ? 'acesso negado' : 'desconectada; tentando reconectar' }}.
            <span v-if="monitoringState.kind === 'stale'">O sensor não enviou leitura recente.</span>
          </p>
        </section>

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
            Não foi possível consultar a API agora. Nenhuma leitura anterior será exibida como se fosse atual.
          </p>
          <button type="button" class="mt-5 rounded-md bg-accent px-4 py-3 font-medium text-accent-ink hover:bg-accent-hover" @click="loadSummary">
            Tentar novamente
          </button>
        </section>

        <section v-else-if="selectedDevice && summary && summary.environment.id !== selectedEnvironmentId" role="alert" class="panel border-status-critical mt-6">
          <h2 class="text-xl font-semibold">Diagnóstico do ambiente indisponível</h2>
          <p class="mt-2 text-ink-muted">A API retornou dados de outro ambiente. Nenhuma leitura será mostrada para a seleção atual.</p>
          <button type="button" class="mt-5 rounded-md bg-accent px-4 py-3 font-medium text-accent-ink hover:bg-accent-hover" @click="loadSummary">Tentar novamente</button>
        </section>

        <template v-else-if="selectedDevice && summary && summary.device.id === selectedMqttId && summary.environment.id === selectedEnvironmentId && stateDetails">
          <section aria-label="Diagnóstico atual" class="status-grid">
            <article class="status-panel" :data-tone="stateDetails.tone">
              <div class="status-main">
                <div>
                  <p class="text-sm font-medium">{{ monitoringState.kind === 'stale' ? 'Temperatura da última leitura' : 'Temperatura' }}</p>
                  <p class="metric-value temperature">{{ formattedTemperature }}</p>
                </div>
                <div aria-live="polite">
                  <h2 class="text-xl font-semibold">{{ stateDetails.label }}</h2>
                  <p class="mt-2 text-sm leading-6 text-ink-muted">{{ stateDetails.message }}</p>
                </div>
              </div>
              <div class="reading-meta">
                <p>Atualidade da leitura: <strong>{{ formattedFreshness }}</strong></p>
                <p>Recebida em {{ formattedReceivedAt }}</p>
                <p>Faixa configurada: {{ summary.thresholds.min_c }}–{{ summary.thresholds.max_c }} °C</p>
                <p v-if="summary.persistence" role="status">{{ summary.persistence === 'pending' ? 'Gravação em andamento; leitura recebida pela API.' : 'Leitura gravada no histórico.' }}</p>
                <p v-if="summary.equipment">Ventilador na última leitura: {{ summary.equipment.running ? 'Em funcionamento' : 'Parado' }}.</p>
              </div>
            </article>
          </section>

          <PredictionPanel v-if="aiotEnabled" :summary="summary" :age-seconds="ageSeconds" />

          <section aria-label="Medições do ambiente" class="metrics-grid">
            <article class="panel">
              <h2 class="text-sm font-medium text-ink-muted">{{ monitoringState.kind === 'stale' ? 'Umidade da última leitura' : 'Umidade' }}</h2>
              <p class="metric-value humidity">{{ formattedHumidity }}</p>
              <p class="mt-3 text-sm leading-6 text-ink-muted">Última leitura válida recebida pela API.</p>
            </article>
            <article class="panel">
              <h2 class="text-sm font-medium text-ink-muted">{{ monitoringState.kind === 'stale' ? 'Luminosidade da última leitura' : 'Luminosidade' }}</h2>
              <p class="metric-value humidity">{{ formattedLight }}</p>
              <p class="mt-3 text-sm leading-6 text-ink-muted">Leituras antigas podem não ter este sensor.</p>
            </article>
            <template v-if="aiotEnabled || summary.equipment">
              <article v-for="metric in motorMetrics" :key="metric.key" class="panel">
                <h2 class="text-sm font-medium text-ink-muted">{{ metric.label }}</h2>
                <p class="metric-value humidity">{{ metric.value }}</p>
                <p class="mt-3 text-sm leading-6 text-ink-muted">{{ summary.reading ? 'Valor da última leitura recebida.' : 'Aguardando a primeira leitura.' }}</p>
              </article>
            </template>
          </section>
        </template>

        <section v-if="selectedDevice && summary && summary.device.id === selectedMqttId && summary.environment.id === selectedEnvironmentId && stateDetails" aria-labelledby="temperature-history-title" class="panel history-panel">
          <div class="flex flex-col flex-wrap gap-5 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p class="eyebrow">Histórico de temperatura</p>
              <h2 id="temperature-history-title" class="mt-2 text-2xl font-semibold">Variação recente</h2>
            </div>
            <fieldset class="period-control" aria-label="Período do histórico">
              <legend class="sr-only">Escolha o período do histórico</legend>
              <button
                v-for="period in historyPeriods"
                :key="period"
                type="button"
                :aria-pressed="selectedPeriod === period"
                @click="selectedPeriod = period"
              >
                {{ period }}
              </button>
            </fieldset>
            <label class="min-w-0 w-full text-sm font-medium text-ink-muted sm:w-auto">Medição do gráfico
              <select v-model="selectedMetric" aria-label="Medição do gráfico" class="mt-2 block min-h-11 w-full min-w-0 max-w-full rounded-md border border-control-border bg-surface px-3 py-2 text-ink">
                <option v-for="metric in availableMetrics" :key="metric.key" :value="metric.key">{{ metric.label }} ({{ metric.unit }})</option>
              </select>
            </label>
          </div>
          <p v-if="historyPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">
            Carregando histórico de temperatura…
          </p>
          <TemperatureHistoryChart v-else-if="historyPhase === 'ready' && history" :readings="history.readings" :period="selectedPeriod" :start="history.start" :end="history.end" :limit="history.limit" :thresholds="summary.thresholds" :metric="selectedMetric" />
          <p v-else-if="historyPhase === 'error'" class="mt-5 border-l-4 border-status-stale pl-4 text-sm leading-6 text-ink-muted" role="status">
            O diagnóstico atual continua disponível, mas o histórico de temperatura não pôde ser carregado.
            <button type="button" class="min-h-11 font-medium text-accent underline" @click="selectedMqttId && loadHistory(selectedMqttId)">Tentar novamente</button>
          </p>
        </section>

        <details v-if="selectedDevice" class="panel history-panel" aria-label="Estado dos atuadores">
          <summary class="actuator-summary">
            <span class="eyebrow">Atuadores</span>
            <span class="actuator-summary-title">Luz e Som de aviso</span>
            <span v-if="actuatorPhase === 'loading'" class="actuator-summary-state" role="status">Consultando estado confirmado…</span>
            <span v-else-if="actuatorPhase === 'error'" class="actuator-summary-state text-status-critical" role="alert">Estado dos atuadores indisponível.</span>
            <span v-else class="actuator-summary-state" aria-live="polite">
              Luz manual: {{ actuatorLabel(led) }} · Som de aviso automático: {{ actuatorLabel(buzzer) }}
            </span>
            <span v-if="commandError" class="actuator-summary-state text-status-critical" role="alert">{{ commandError }}</span>
          </summary>
          <div class="actuator-content">
            <div class="actuator-grid">
              <div>
                <h3 class="font-medium">Luz manual</h3>
                <LedControl :led="led" :phase="actuatorPhase" :submitting="commandSubmitting" :error="commandError" @toggle="toggleLed" @refresh="selectedActuatorId && loadActuators(selectedActuatorId)" />
                <p v-if="summary?.equipment" class="mt-2 text-sm text-ink-muted">Luz observada na última leitura: {{ summary.equipment.led.actual_state ? 'Ligado' : 'Desligado' }}. {{ formattedFreshness }}.</p>
              </div>
              <div>
                <h3 class="font-medium">Som de aviso automático</h3>
                <p class="mt-2" aria-live="polite">{{ actuatorLabel(buzzer) }}</p>
                <p v-if="summary?.equipment" class="mt-2 text-sm text-ink-muted">Buzzer observado na última leitura: {{ summary.equipment.buzzer.actual_state ? 'Ligado' : 'Desligado' }}. {{ formattedFreshness }}.</p>
              </div>
            </div>
          </div>
        </details>

        <AlertsComparisonPanel v-if="selectedMqttId && sessionToken" :auth="sessionToken" :device-id="selectedMqttId" :period="selectedPeriod" :revision="eventsRevision" />
        <p class="mt-8 text-xs leading-6 text-ink-muted">Atualização por WebSocket; estado recuperado pela API ao reconectar.</p>
      </section>
      <footer class="mt-8 border-t border-line pt-6 text-xs leading-6 text-ink-muted">
        Protótipo acadêmico: não é equipamento médico, sanitário ou regulatório certificado.
      </footer>
    </div>
  </main>
</template>

<style scoped>
.dashboard { padding: var(--cs-space-48); }
.dashboard-shell { max-width: 1200px; margin-inline: auto; }
.dashboard-nav { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.nav-actions { display: flex; flex-wrap: wrap; min-width: 0; max-width: 100%; gap: var(--cs-space-16); font-size: var(--cs-type-14); }
.nav-actions a, .sign-out { display: inline-flex; align-items: center; min-height: 44px; }
.nav-actions a:hover, .sign-out:hover { text-decoration: underline; }
.sign-out { color: var(--cs-color-accent); text-decoration: underline; cursor: pointer; }
.brand { display: inline-flex; align-items: center; gap: var(--cs-space-12); margin-right: auto; font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; white-space: nowrap; }
.eyebrow { color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); line-height: 1.5; text-transform: uppercase; }
.dashboard-heading { margin-block: var(--cs-space-32); }
h1 { margin-top: var(--cs-space-8); font-size: var(--cs-type-32); font-weight: 600; line-height: 1.2; letter-spacing: -0.025em; }
.panel { min-width: 0; padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.panel[role="alert"] { border-color: var(--cs-color-status-critical); }
.selection-panel { margin-bottom: var(--cs-space-24); }
.selection-fields, .actuator-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); }
.selection-fields label { display: grid; gap: var(--cs-space-8); font-size: var(--cs-type-14); font-weight: 600; }
.selection-fields select { min-height: 44px; min-width: 0; padding: var(--cs-space-8); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); }
.actuator-grid { margin-top: var(--cs-space-24); }
.actuator-summary { min-height: 44px; cursor: pointer; }
.actuator-summary-title { margin-left: var(--cs-space-8); font-size: var(--cs-type-24); font-weight: 600; }
.actuator-summary-state { display: block; margin-top: var(--cs-space-8); font-size: var(--cs-type-14); line-height: 1.5; }
.actuator-content { margin-top: var(--cs-space-24); padding-top: var(--cs-space-24); border-top: 1px solid var(--cs-color-line); }
.status-panel { min-width: 0; padding: var(--cs-space-24); border: 1px solid var(--status-color); border-radius: var(--cs-radius-panel); color: var(--status-color); background: var(--status-surface); }
.status-main { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); align-items: center; }
.status-panel .temperature { margin-top: var(--cs-space-8); color: var(--cs-color-ink); overflow-wrap: anywhere; }
.reading-meta { display: flex; flex-wrap: wrap; gap: var(--cs-space-8) var(--cs-space-24); margin-top: var(--cs-space-16); padding-top: var(--cs-space-16); border-top: 1px solid var(--cs-color-line); color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); line-height: 1.5; }
.reading-meta strong { color: var(--cs-color-ink); font-weight: 600; }
.status-panel[data-tone='normal'] { --status-color: var(--cs-color-status-normal); --status-surface: var(--cs-color-normal-surface); }
.status-panel[data-tone='attention'] { --status-color: var(--cs-color-status-attention); --status-surface: var(--cs-color-attention-surface); }
.status-panel[data-tone='critical'] { --status-color: var(--cs-color-status-critical); --status-surface: var(--cs-color-critical-surface); }
.status-panel[data-tone='stale'] { --status-color: var(--cs-color-status-stale); --status-surface: var(--cs-color-stale-surface); }
.metrics-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: var(--cs-space-24); margin-top: var(--cs-space-16); }
.metric-value { margin-top: var(--cs-space-16); line-height: 1.1; letter-spacing: -0.035em; font-weight: 500; }
.temperature { font-size: var(--cs-type-64); }
.humidity { font-size: var(--cs-type-48); }
.history-panel { margin-top: var(--cs-space-32); padding: var(--cs-space-32); }
.period-control { display: flex; padding: var(--cs-space-4); border-radius: var(--cs-radius-4); background: var(--cs-color-surface-muted); }
.period-control button { flex: 1; min-width: 64px; min-height: 44px; padding: var(--cs-space-8) var(--cs-space-16); border-radius: var(--cs-radius-4); font-size: var(--cs-type-14); transition: background-color var(--cs-motion-quick); cursor: pointer; }
.period-control button:hover { background: var(--cs-color-line); }
.period-control button[aria-pressed='true'] { background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
@media (max-width: 767px) {
  .dashboard { padding: var(--cs-space-24); }
  .dashboard-nav { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--cs-space-8); padding-bottom: var(--cs-space-16); }
  .nav-actions { grid-column: 1 / -1; grid-row: 2; flex-wrap: nowrap; gap: var(--cs-space-16); overflow-x: auto; }
  .nav-actions a { flex-shrink: 0; }
  .dashboard-nav .eyebrow { max-width: 132px; text-align: right; font-size: 10px; }
  .dashboard-heading { margin-block: var(--cs-space-16); }
  .dashboard-heading p { overflow-wrap: anywhere; }
  h1 { font-size: var(--cs-type-24); }
  .status-main { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-12); }
  .metrics-grid { gap: var(--cs-space-12); }
  .selection-fields { gap: var(--cs-space-12); }
  .actuator-grid { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-16); }
  .panel, .status-panel, .history-panel { padding: var(--cs-space-16); }
  .selection-panel { margin-bottom: var(--cs-space-16); }
  .history-panel { margin-top: var(--cs-space-16); }
  .temperature { font-size: clamp(2.5rem, 12vw, 4rem); }
  .humidity { font-size: var(--cs-type-32); }
  .metric-value { margin-top: var(--cs-space-12); }
  .period-control button { min-width: 0; }
}
@media (max-width: 374px) {
  .dashboard { padding: var(--cs-space-16); }
  .brand { font-size: var(--cs-type-20); }
  .selection-fields { grid-template-columns: minmax(0, 1fr); }
  .metrics-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
