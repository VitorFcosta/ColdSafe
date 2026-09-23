<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import TemperatureHistoryChart from '../features/monitoring/TemperatureHistoryChart.vue'
import {
  fetchMonitoringHistory,
  historyPeriods,
  type HistoryPeriod,
  type MonitoringHistory,
} from '../features/monitoring/monitoring-history'
import { useMonitoringSummary } from '../features/monitoring/use-monitoring-summary'

const { loadSummary, monitoringState, refreshRevision, summary } = useMonitoringSummary()
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const selectedPeriod = ref<HistoryPeriod>('1h')
const history = ref<MonitoringHistory | null>(null)
const historyPhase = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
let latestHistoryRequest = 0

const stateDetails = computed(() => {
  switch (monitoringState.value.kind) {
    case 'normal':
      return { label: 'Normal', message: 'Temperatura dentro da faixa demonstrativa.', tone: 'normal' }
    case 'attention':
      return { label: 'Atenção', message: 'Temperatura próxima de um limite demonstrativo.', tone: 'attention' }
    case 'critical':
      return { label: 'Crítico', message: 'Temperatura fora da faixa demonstrativa.', tone: 'critical' }
    case 'stale':
      return { label: 'Leitura desatualizada', message: 'Última leitura conhecida. A situação atual não está confirmada.', tone: 'stale' }
    case 'no_data':
      return { label: 'Sem dados', message: 'Ainda não há leitura válida para este ambiente.', tone: 'stale' }
    default:
      return null
  }
})

const formattedTemperature = computed(() => formatMeasurement(summary.value?.reading?.temperature_c, '°C'))
const formattedHumidity = computed(() => formatMeasurement(summary.value?.reading?.humidity_percent, '%'))
const formattedFreshness = computed(() => formatFreshness(summary.value?.freshness?.age_seconds))
const formattedReceivedAt = computed(() => formatDateTime(summary.value?.reading?.received_at))

watch(
  [() => summary.value?.device.id, selectedPeriod, refreshRevision],
  ([deviceId]) => {
    if (deviceId !== undefined) {
      void loadHistory(deviceId)
    }
  },
)

async function loadHistory(deviceId: string) {
  const requestId = ++latestHistoryRequest
  historyPhase.value = 'loading'

  try {
    const result = await fetchMonitoringHistory({
      baseUrl: apiBaseUrl,
      deviceId,
      period: selectedPeriod.value,
      fetcher: fetch,
    })

    if (requestId !== latestHistoryRequest) return

    history.value = result
    historyPhase.value = 'ready'
  } catch {
    if (requestId !== latestHistoryRequest) return

    historyPhase.value = 'error'
  }
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
        <p class="eyebrow">Monitoramento / Laboratório</p>
      </nav>

      <section aria-labelledby="dashboard-title">
        <header class="dashboard-heading">
          <p class="eyebrow">Visão geral</p>
          <h1 id="dashboard-title">Diagnóstico do ambiente</h1>
          <p class="mt-2 text-sm text-ink-muted">
            <template v-if="summary">{{ summary.environment.name }} <span aria-hidden="true"> / </span> {{ summary.device.id }}</template>
            <template v-else>Monitoramento do laboratório refrigerado</template>
          </p>
        </header>

        <section
          v-if="monitoringState.kind === 'loading'"
          aria-busy="true"
          aria-label="Carregando diagnóstico atual"
          class="grid gap-6 sm:grid-cols-2"
        >
          <div v-for="index in 2" :key="index" class="h-40 rounded-panel border border-line bg-surface-muted" />
          <p class="text-sm text-ink-muted">Carregando diagnóstico atual…</p>
        </section>

        <section v-else-if="monitoringState.kind === 'service_error'" role="alert" class="panel border-status-critical">
          <h2 class="text-xl font-semibold">Diagnóstico indisponível</h2>
          <p class="mt-2 max-w-xl leading-7 text-ink-muted">
            Não foi possível consultar a API agora. Nenhuma leitura anterior será exibida como se fosse atual.
          </p>
          <button type="button" class="mt-5 rounded-md bg-accent px-4 py-3 font-medium text-accent-ink hover:bg-accent-hover" @click="loadSummary">
            Tentar novamente
          </button>
        </section>

        <template v-else-if="summary && stateDetails">
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
                Faixa demonstrativa: {{ summary.thresholds.min_c }}–{{ summary.thresholds.max_c }} °C
              </p>
            </article>
            <article class="panel">
              <h2 class="text-sm font-medium text-ink-muted">Umidade</h2>
              <p class="metric-value humidity">{{ formattedHumidity }}</p>
              <p class="mt-3 text-sm leading-6 text-ink-muted">Última leitura válida recebida pela API.</p>
            </article>
          </section>
        </template>

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

        <p class="mt-8 text-xs leading-6 text-ink-muted">Atualização a cada 5 segundos · Um ambiente, um dispositivo.</p>
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
.brand { display: inline-flex; align-items: center; gap: var(--cs-space-12); font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; white-space: nowrap; }
.eyebrow { color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); line-height: 1.5; text-transform: uppercase; }
.dashboard-heading { margin-block: var(--cs-space-32); }
h1 { margin-top: var(--cs-space-8); font-size: var(--cs-type-32); font-weight: 600; line-height: 1.2; letter-spacing: -0.025em; }
.panel { min-width: 0; padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.panel[role="alert"] { border-color: var(--cs-color-status-critical); }
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
  .dashboard-nav .eyebrow { max-width: 132px; text-align: right; font-size: 10px; }
  .dashboard-heading { margin-block: var(--cs-space-24); }
  h1 { font-size: var(--cs-type-24); }
  .status-grid, .metrics-grid { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-16); }
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
