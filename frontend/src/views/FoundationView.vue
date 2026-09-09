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
      return { label: 'Leitura desatualizada', message: 'A última telemetria ultrapassou 30 segundos.', tone: 'stale' }
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
  <main class="min-h-screen bg-canvas px-5 py-8 text-ink sm:px-10 sm:py-12">
    <section aria-labelledby="dashboard-title" class="mx-auto max-w-6xl">
      <header class="border-b border-line pb-6">
        <p class="font-mono text-sm tracking-wide text-ink-muted">ColdSafe / dashboard operacional</p>
        <h1 id="dashboard-title" class="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Diagnóstico do ambiente
        </h1>
        <p class="mt-3 max-w-2xl leading-7 text-ink-muted">
          Leitura atual do laboratório refrigerado para demonstração acadêmica.
        </p>
      </header>

      <section
        v-if="monitoringState.kind === 'loading'"
        aria-busy="true"
        aria-label="Carregando diagnóstico atual"
        class="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        <div v-for="index in 3" :key="index" class="h-40 animate-pulse rounded-panel border border-line bg-surface-muted" />
      </section>

      <section
        v-else-if="monitoringState.kind === 'service_error'"
        role="alert"
        class="mt-8 rounded-panel border border-status-critical bg-surface p-6 shadow-panel"
      >
        <h2 class="text-xl font-semibold">Diagnóstico indisponível</h2>
        <p class="mt-2 max-w-xl leading-7 text-ink-muted">
          Não foi possível consultar a API agora. Nenhuma leitura anterior será exibida como se fosse atual.
        </p>
        <button
          type="button"
          class="mt-5 rounded-md bg-accent px-4 py-2 font-medium text-white"
          @click="loadSummary"
        >
          Tentar novamente
        </button>
      </section>

      <section v-else-if="summary && stateDetails" class="mt-8 grid gap-4 lg:grid-cols-3">
        <article class="rounded-panel border border-line bg-surface p-6 shadow-panel lg:col-span-2">
          <p class="font-mono text-sm text-ink-muted">{{ summary.environment.id }}</p>
          <h2 class="mt-2 text-2xl font-semibold">{{ summary.environment.name }}</h2>
          <div
            class="mt-6 rounded-md border-l-4 bg-surface-muted px-5 py-4"
            :class="{
              'border-status-normal': stateDetails.tone === 'normal',
              'border-status-attention': stateDetails.tone === 'attention',
              'border-status-critical': stateDetails.tone === 'critical',
              'border-status-stale': stateDetails.tone === 'stale',
            }"
          >
            <p class="font-mono text-sm uppercase tracking-wider text-ink-muted">Situação atual</p>
            <p class="mt-1 text-2xl font-semibold">{{ stateDetails.label }}</p>
            <p class="mt-1 leading-6 text-ink-muted">{{ stateDetails.message }}</p>
          </div>
        </article>

        <article class="rounded-panel border border-line bg-surface p-6 shadow-panel">
          <p class="font-mono text-sm text-ink-muted">Atualidade da leitura</p>
          <p class="mt-3 text-2xl font-semibold">{{ formattedFreshness }}</p>
          <p class="mt-2 text-sm leading-6 text-ink-muted">Recebida em {{ formattedReceivedAt }}</p>
        </article>

        <article class="rounded-panel border border-line bg-surface p-6 shadow-panel">
          <p class="font-mono text-sm text-ink-muted">Temperatura</p>
          <p class="mt-3 text-4xl font-semibold">{{ formattedTemperature }}</p>
          <p class="mt-2 text-sm text-ink-muted">
            Faixa demonstrativa: {{ summary.thresholds.min_c }}–{{ summary.thresholds.max_c }} °C
          </p>
        </article>

        <article class="rounded-panel border border-line bg-surface p-6 shadow-panel">
          <p class="font-mono text-sm text-ink-muted">Umidade</p>
          <p class="mt-3 text-4xl font-semibold">{{ formattedHumidity }}</p>
          <p class="mt-2 text-sm text-ink-muted">Última leitura válida recebida pela API.</p>
        </article>

        <article class="rounded-panel border border-line bg-surface p-6 shadow-panel">
          <p class="font-mono text-sm text-ink-muted">Dispositivo</p>
          <p class="mt-3 text-xl font-semibold">{{ summary.device.id }}</p>
          <p class="mt-2 text-sm leading-6 text-ink-muted">
            Fonte da telemetria do ambiente demonstrativo.
          </p>
        </article>
      </section>

      <section v-if="summary && stateDetails" aria-labelledby="temperature-history-title" class="mt-8 rounded-panel border border-line bg-surface p-6 shadow-panel">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p class="font-mono text-sm text-ink-muted">Histórico de temperatura</p>
            <h2 id="temperature-history-title" class="mt-1 text-2xl font-semibold">Variação recente</h2>
          </div>
          <fieldset class="flex flex-wrap gap-2" aria-label="Período do histórico">
            <legend class="sr-only">Escolha o período do histórico</legend>
            <button
              v-for="period in historyPeriods"
              :key="period"
              type="button"
              :aria-pressed="selectedPeriod === period"
              class="rounded-md border px-3 py-2 font-mono text-sm font-medium transition-colors"
              :class="selectedPeriod === period ? 'border-accent bg-accent text-white' : 'border-line bg-surface text-ink hover:bg-surface-muted'"
              @click="selectedPeriod = period"
            >
              {{ period }}
            </button>
          </fieldset>
        </div>

        <p v-if="historyPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">
          Carregando histórico de temperatura…
        </p>
        <div v-else-if="historyPhase === 'ready' && history">
          <TemperatureHistoryChart :readings="history.readings" :period="selectedPeriod" />
        </div>
        <p v-else-if="historyPhase === 'error'" class="mt-5 border-l-4 border-status-stale pl-4 text-sm leading-6 text-ink-muted" role="status">
          O diagnóstico atual continua disponível, mas o histórico de temperatura não pôde ser carregado.
        </p>
      </section>

      <p class="mt-8 border-l-4 border-accent pl-4 text-sm leading-6 text-ink-muted">
        Protótipo acadêmico: não é equipamento médico, sanitário ou regulatório certificado.
      </p>
    </section>
  </main>
</template>
