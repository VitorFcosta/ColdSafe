<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { listDevices, listEnvironments, type Device, type Environment } from '../features/account/catalog'
import { clearSession, logout, sessionToken } from '../features/account/session'
import AlertsComparisonPanel from '../features/monitoring/AlertsComparisonPanel.vue'
import { fetchActuators, fetchCommand, isCommand, requestLed, type ActuatorCommand } from '../features/monitoring/actuators'
import TemperatureHistoryChart from '../features/monitoring/TemperatureHistoryChart.vue'
import {
  fetchMonitoringHistory, historyPeriods, type HistoryPeriod, type MonitoringHistory,
} from '../features/monitoring/monitoring-history'
import { useMonitoringSummary, type MonitoringEvent } from '../features/monitoring/use-monitoring-summary'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const router = useRouter()
const environments = ref<Environment[]>([])
const devices = ref<Device[]>([])
const selectedEnvironmentId = ref('')
const selectedDeviceUuid = ref('')
const catalogPhase = ref<'loading' | 'ready' | 'error'>('loading')
const selectedDevice = computed(() => devices.value.find((item) => item.id === selectedDeviceUuid.value && item.is_active))
const selectedMqttId = computed(() => selectedDevice.value?.mqtt_device_id ?? null)
const selectedPeriod = ref<HistoryPeriod>('1h')
const history = ref<MonitoringHistory | null>(null)
const historyPhase = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const led = ref<ActuatorCommand | null>(null)
const buzzer = ref<ActuatorCommand | null>(null)
const actuatorPhase = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const commandError = ref('')
const logoutError = ref('')
const eventsRevision = ref(0)
let latestCatalogRequest = 0
let latestHistoryRequest = 0
let latestActuatorRequest = 0
let pendingTimer: ReturnType<typeof setInterval> | null = null
let catalogRetryTimer: ReturnType<typeof setTimeout> | null = null
let pendingChecks = 0

function handleEvent(event: MonitoringEvent) {
  eventsRevision.value += 1
  if (event.type !== 'command_status' || !isCommand(event.data)) return
  if (event.data.actuator === 'led') led.value = event.data
  else buzzer.value = event.data
  if (event.data.actuator === 'led' && event.data.status !== 'pending') stopPendingCheck()
}

const { loadSummary, monitoringState, refreshRevision, summary, connectionState } =
  useMonitoringSummary(sessionToken, selectedMqttId, handleEvent)

watch(connectionState, (state) => {
  if (state === 'unauthorized') {
    clearSession()
    void router.push('/login')
  }
})

const stateDetails = computed(() => {
  switch (monitoringState.value.kind) {
    case 'normal': return { label: 'Normal', message: 'Temperatura dentro da faixa configurada.', tone: 'normal' }
    case 'attention': return { label: 'Atenção', message: 'Temperatura próxima de um limite configurado.', tone: 'attention' }
    case 'critical': return { label: 'Crítico', message: 'Temperatura fora da faixa configurada.', tone: 'critical' }
    case 'stale': return { label: 'Leitura desatualizada', message: 'Última leitura conhecida. A situação atual não está confirmada.', tone: 'stale' }
    case 'no_data': return { label: 'Sem dados', message: 'Ainda não há leitura válida para este dispositivo.', tone: 'stale' }
    default: return null
  }
})

const formattedTemperature = computed(() => formatMeasurement(summary.value?.reading?.temperature_c, '°C'))
const formattedHumidity = computed(() => formatMeasurement(summary.value?.reading?.humidity_percent, '%'))
const formattedLight = computed(() => formatMeasurement(summary.value?.reading?.light_percent ?? undefined, '%'))
const formattedFreshness = computed(() => formatFreshness(summary.value?.freshness?.age_seconds))
const formattedReceivedAt = computed(() => formatDateTime(summary.value?.reading?.received_at))

onMounted(() => { void loadEnvironments() })
onUnmounted(() => {
  latestCatalogRequest += 1
  stopPendingCheck()
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
    selectedEnvironmentId.value = result.some((item) => item.id === previousEnvironmentId)
      ? previousEnvironmentId : (result[0]?.id ?? '')
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
    selectedDeviceUuid.value = result.find((item) => item.is_active)?.id ?? ''
    catalogPhase.value = 'ready'
  } catch {
    if (requestId !== latestCatalogRequest) return
    catalogPhase.value = 'error'
    retryCatalog(() => {
      if (selectedEnvironmentId.value === environmentId) void loadDevices(environmentId)
    })
  }
}

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

watch(selectedDeviceUuid, (deviceUuid) => {
  latestActuatorRequest += 1
  led.value = null
  buzzer.value = null
  commandError.value = ''
  stopPendingCheck()
  if (!deviceUuid) {
    actuatorPhase.value = 'idle'
    return
  }
  void loadActuators(deviceUuid)
})

watch(connectionState, (state, previous) => {
  if (state === 'connected' && previous !== 'connected' && selectedDeviceUuid.value) {
    void loadActuators(selectedDeviceUuid.value)
  }
})

async function loadActuators(deviceUuid: string) {
  const token = sessionToken.value
  if (!token) return
  const requestId = ++latestActuatorRequest
  actuatorPhase.value = 'loading'
  try {
    const result = await fetchActuators(token, deviceUuid)
    if (requestId !== latestActuatorRequest || selectedDeviceUuid.value !== deviceUuid) return
    led.value = result.led
    buzzer.value = result.buzzer
    actuatorPhase.value = 'ready'
    if (result.led?.status === 'pending') startPendingCheck(result.led.command_id, deviceUuid)
  } catch {
    if (requestId === latestActuatorRequest) actuatorPhase.value = 'error'
  }
}

async function toggleLed() {
  const token = sessionToken.value
  const deviceUuid = selectedDeviceUuid.value
  if (!token || !deviceUuid || led.value?.status === 'pending') return
  commandError.value = ''
  try {
    const result = await requestLed(token, deviceUuid, led.value?.confirmed_state !== true)
    if (selectedDeviceUuid.value !== deviceUuid) return
    led.value = result
    if (result.status === 'pending') startPendingCheck(result.command_id, deviceUuid)
  } catch {
    commandError.value = 'Não foi possível enviar o comando. Tente novamente.'
  }
}

function stopPendingCheck() {
  if (pendingTimer !== null) clearInterval(pendingTimer)
  pendingTimer = null
  pendingChecks = 0
}

function startPendingCheck(commandId: string, deviceUuid: string) {
  stopPendingCheck()
  pendingTimer = setInterval(async () => {
    const token = sessionToken.value
    if (!token || selectedDeviceUuid.value !== deviceUuid || pendingChecks++ >= 35) {
      stopPendingCheck()
      return
    }
    try {
      const result = await fetchCommand(token, commandId)
      if (selectedDeviceUuid.value !== deviceUuid || led.value?.command_id !== commandId) return
      led.value = result
      if (result.status !== 'pending') stopPendingCheck()
    } catch {
      commandError.value = 'Confirmação indisponível. Consulte o estado novamente.'
    }
  }, 1000)
}

const actuatorLabel = (command: ActuatorCommand | null) => {
  if (command === null) return 'Sem confirmação registrada'
  if (command.status === 'confirmed') return command.confirmed_state ? 'Ligado' : 'Desligado'
  if (command.status === 'pending') return 'Aguardando confirmação'
  return command.status === 'rejected' ? 'Comando rejeitado' : 'Sem confirmação'
}

function formatMeasurement(value: number | undefined, unit: string) {
  return value === undefined ? '—' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${unit}`
}

function formatFreshness(ageSeconds: number | undefined) {
  if (ageSeconds === undefined) return 'Sem leitura recebida'
  if (ageSeconds < 5) return 'Agora mesmo'
  if (ageSeconds < 60) return `Há ${Math.floor(ageSeconds)} s`

  const minutes = Math.floor(ageSeconds / 60)
  const seconds = Math.floor(ageSeconds % 60)
  return seconds === 0 ? `Há ${minutes} min` : `Há ${minutes} min e ${seconds} s`
}

function formatDateTime(value: string | undefined) {
  if (value === undefined) return '—'

  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(new Date(value))
}
</script>

<template>
  <main class="dashboard min-h-screen bg-canvas text-ink">
    <div class="dashboard-shell">
      <nav aria-label="Navegação principal" class="dashboard-nav">
        <a href="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</a>
        <div class="nav-actions">
          <RouterLink to="/manage">Ambientes e dispositivos</RouterLink>
          <button type="button" @click="handleLogout">Sair</button>
        </div>
      </nav>
      <p v-if="logoutError" role="alert" class="mt-4 text-sm text-status-critical">{{ logoutError }}</p>

      <section aria-labelledby="dashboard-title">
        <header class="dashboard-heading">
          <p class="eyebrow">Visão geral</p>
          <h1 id="dashboard-title">Diagnóstico do ambiente</h1>
          <p class="mt-2 text-sm text-ink-muted">
            <template v-if="summary">{{ summary.environment.name }} <span aria-hidden="true"> / </span> {{ summary.device.id }}</template>
            <template v-else>Selecione um ambiente e um dispositivo para monitorar.</template>
          </p>
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
          <p v-else-if="catalogPhase === 'ready' && environments.length === 0" class="mt-3 text-sm text-ink-muted">Nenhum ambiente cadastrado. <RouterLink to="/manage" class="underline">Criar ambiente</RouterLink></p>
          <p v-else-if="catalogPhase === 'ready' && selectedEnvironmentId && devices.every((device) => !device.is_active)" class="mt-3 text-sm text-ink-muted">Nenhum dispositivo ativo neste ambiente. <RouterLink to="/manage" class="underline">Gerenciar dispositivos</RouterLink></p>
          <p v-if="selectedDevice" class="mt-3 text-sm text-ink-muted" aria-live="polite">
            Canal em tempo real: {{ connectionState === 'connected' ? 'conectado' : connectionState === 'connecting' ? 'conectando' : connectionState === 'forbidden' ? 'acesso negado' : 'desconectado; tentando reconectar' }}.
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

        <template v-else-if="selectedDevice && summary && stateDetails">
          <section aria-label="Diagnóstico atual" class="status-grid">
            <article class="status-panel" :data-tone="stateDetails.tone" aria-live="polite">
              <h2 class="text-xl font-semibold">{{ stateDetails.label }}</h2>
              <p class="mt-2 text-sm leading-6 text-ink-muted">{{ stateDetails.message }}</p>
            </article>
            <article class="panel">
              <h2 class="text-sm font-medium text-ink-muted">Atualidade da leitura</h2>
              <p class="mt-4 text-2xl font-medium">{{ formattedFreshness }}</p>
              <p class="mt-4 text-sm leading-6 text-ink-muted">Recebida em {{ formattedReceivedAt }}</p>
            </article>
          </section>

          <section aria-label="Medições do ambiente" class="metrics-grid">
            <article class="panel">
              <h2 class="text-sm font-medium text-ink-muted">Temperatura</h2>
              <p class="metric-value temperature">{{ formattedTemperature }}</p>
              <p class="mt-3 text-sm leading-6 text-ink-muted">
                Faixa configurada: {{ summary.thresholds.min_c }}–{{ summary.thresholds.max_c }} °C
              </p>
            </article>
            <article class="panel">
              <h2 class="text-sm font-medium text-ink-muted">Umidade</h2>
              <p class="metric-value humidity">{{ formattedHumidity }}</p>
              <p class="mt-3 text-sm leading-6 text-ink-muted">Última leitura válida recebida pela API.</p>
            </article>
            <article class="panel">
              <h2 class="text-sm font-medium text-ink-muted">Luminosidade</h2>
              <p class="metric-value humidity">{{ formattedLight }}</p>
              <p class="mt-3 text-sm leading-6 text-ink-muted">Leituras antigas podem não ter este sensor.</p>
            </article>
          </section>
        </template>

        <section v-if="selectedDevice" class="panel history-panel" aria-label="Estado dos atuadores">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p class="eyebrow">Atuadores</p>
              <h2 class="mt-2 text-2xl font-semibold">LED e buzzer</h2>
            </div>
            <button type="button" class="rounded-md border border-line px-4 py-3 text-sm hover:bg-surface-muted" @click="loadActuators(selectedDeviceUuid)">Atualizar estado</button>
          </div>
          <p v-if="actuatorPhase === 'loading'" class="mt-4 text-sm text-ink-muted">Consultando estado confirmado…</p>
          <p v-if="actuatorPhase === 'error'" role="status" class="mt-4 text-sm text-status-critical">Estado dos atuadores indisponível.</p>
          <div class="actuator-grid">
            <div>
              <h3 class="font-medium">LED manual</h3>
              <p class="mt-2" aria-live="polite">{{ actuatorLabel(led) }}</p>
              <button type="button" class="mt-3 rounded-md bg-accent px-4 py-3 font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-50" :disabled="actuatorPhase !== 'ready' || led?.status === 'pending'" @click="toggleLed">
                {{ led?.confirmed_state === true ? 'Desligar LED' : 'Ligar LED' }}
              </button>
            </div>
            <div>
              <h3 class="font-medium">Buzzer automático</h3>
              <p class="mt-2" aria-live="polite">{{ actuatorLabel(buzzer) }}</p>
            </div>
          </div>
          <p v-if="commandError" role="alert" class="mt-4 text-sm text-status-critical">{{ commandError }}</p>
        </section>

        <section v-if="summary && stateDetails" aria-labelledby="temperature-history-title" class="panel history-panel">
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
          </div>
          <p v-if="historyPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">
            Carregando histórico de temperatura…
          </p>
          <TemperatureHistoryChart v-else-if="historyPhase === 'ready' && history" :readings="history.readings" :period="selectedPeriod" />
          <p v-else-if="historyPhase === 'error'" class="mt-5 border-l-4 border-status-stale pl-4 text-sm leading-6 text-ink-muted" role="status">
            O diagnóstico atual continua disponível, mas o histórico de temperatura não pôde ser carregado.
          </p>
        </section>

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
.dashboard-nav { display: flex; align-items: center; justify-content: space-between; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.nav-actions { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); font-size: var(--cs-type-14); }
.nav-actions a:hover, .nav-actions button:hover { text-decoration: underline; }
.brand { display: inline-flex; align-items: center; gap: var(--cs-space-12); font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; white-space: nowrap; }
.eyebrow { color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); line-height: 1.5; text-transform: uppercase; }
.dashboard-heading { margin-block: var(--cs-space-32); }
h1 { margin-top: var(--cs-space-8); font-size: var(--cs-type-32); font-weight: 600; line-height: 1.2; letter-spacing: -0.025em; }
.panel { min-width: 0; padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.panel[role="alert"] { border-color: var(--cs-color-status-critical); }
.selection-panel { margin-bottom: var(--cs-space-24); }
.selection-fields, .actuator-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); }
.selection-fields label { display: grid; gap: var(--cs-space-8); font-size: var(--cs-type-14); font-weight: 600; }
.selection-fields select { min-height: 44px; min-width: 0; padding: var(--cs-space-8); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); }
.selection-fields select:focus-visible, button:focus-visible, a:focus-visible { outline: 2px solid var(--cs-focus-ring); outline-offset: 2px; }
.actuator-grid { margin-top: var(--cs-space-24); }
.status-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); align-items: start; gap: var(--cs-space-24); }
.status-panel { min-width: 0; padding: var(--cs-space-24); border: 1px solid var(--status-color); border-radius: var(--cs-radius-panel); color: var(--status-color); background: var(--status-surface); }
.status-panel[data-tone='normal'] { --status-color: var(--cs-color-status-normal); --status-surface: var(--cs-color-normal-surface); }
.status-panel[data-tone='attention'] { --status-color: var(--cs-color-status-attention); --status-surface: var(--cs-color-attention-surface); }
.status-panel[data-tone='critical'] { --status-color: var(--cs-color-status-critical); --status-surface: var(--cs-color-critical-surface); }
.status-panel[data-tone='stale'] { --status-color: var(--cs-color-status-stale); --status-surface: var(--cs-color-stale-surface); }
.metrics-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: var(--cs-space-24); margin-top: var(--cs-space-32); }
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
  .dashboard-nav { gap: var(--cs-space-12); padding-bottom: var(--cs-space-24); }
  .nav-actions { justify-content: flex-end; gap: var(--cs-space-8); }
  .dashboard-nav .eyebrow { max-width: 132px; text-align: right; font-size: 10px; }
  .dashboard-heading { margin-block: var(--cs-space-24); }
  h1 { font-size: var(--cs-type-24); }
  .status-grid, .metrics-grid { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-16); }
  .selection-fields, .actuator-grid { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-16); }
  .panel, .status-panel, .history-panel { padding: var(--cs-space-16); }
  .metrics-grid, .history-panel { margin-top: var(--cs-space-16); }
  .temperature { font-size: var(--cs-type-48); }
  .humidity { font-size: var(--cs-type-48); }
  .metric-value { margin-top: var(--cs-space-12); }
  .period-control button { min-width: 0; }
}
@media (max-width: 374px) {
  .dashboard { padding: var(--cs-space-16); }
  .brand { font-size: var(--cs-type-20); }
}
</style>
