<script setup lang="ts">
import {
  Chart as ChartJS, Legend, LineElement, LinearScale, PointElement, Tooltip,
  type ChartData, type ChartOptions,
} from 'chart.js'
import { computed, onMounted, ref, shallowRef, useTemplateRef, watch } from 'vue'
import { Line } from 'vue-chartjs'

import { fetchAlerts, type AlertRecord } from './alerts-api'
import { fetchMonitoringHistory, type HistoricalReading, type HistoryPeriod } from './monitoring-history'
import { buildTemperatureChart, describeHistoryCoverage, formatReadingTime } from './temperature-chart'
import { monitoringPollingIntervalMs } from './monitoring-polling'

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, Legend)

const props = defineProps<{
  auth: string | null
  deviceId: string | null
  period: HistoryPeriod
  revision?: number
}>()

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const periodMinutes: Readonly<Record<HistoryPeriod, number>> = {
  '15m': 15, '1h': 60, '6h': 360, '24h': 1440,
}
const alerts = ref<readonly AlertRecord[]>([])
const current = ref<readonly HistoricalReading[]>([])
const previous = ref<readonly HistoricalReading[]>([])
const limits = ref({ current: 300, previous: 300 })
const alertPhase = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const comparisonPhase = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const alertsLoaded = ref(false)
const alertDetailsShown = ref(false)
const comparisonLoaded = ref(false)
let refreshNow = () => {}
let queueRefresh = () => {}
const windows = ref({ currentStart: '', currentEnd: '', previousStart: '', previousEnd: '' })
const panel = useTemplateRef<HTMLElement>('panel')
const colors = shallowRef({ accent: '', muted: '', line: '' })

onMounted(() => {
  const style = getComputedStyle(panel.value!)
  colors.value = {
    accent: style.getPropertyValue('--cs-color-accent').trim(),
    muted: style.getPropertyValue('--cs-color-ink-muted').trim(),
    line: style.getPropertyValue('--cs-color-line').trim(),
  }
})

watch([() => props.auth, () => props.deviceId, () => props.period],
  ([auth, deviceId, period], _previous, onCleanup) => {
    alerts.value = []
    current.value = []
    previous.value = []
    alertsLoaded.value = false
    alertDetailsShown.value = false
    comparisonLoaded.value = false
    alertPhase.value = 'idle'
    comparisonPhase.value = 'idle'
    refreshNow = queueRefresh = () => {}
    if (!auth || !deviceId) return

    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let busy = false
    let pending = false
    let lastStarted = 0
    onCleanup(() => {
      controller.abort()
      clearTimeout(timer)
    })
    const schedule = () => {
      pending = true
      if (busy || timer !== undefined || controller.signal.aborted) return
      timer = setTimeout(() => {
        timer = undefined
        void refresh()
      }, Math.max(0, lastStarted + monitoringPollingIntervalMs - Date.now()))
    }
    const refresh = async () => {
      if (controller.signal.aborted) return
      if (busy) { pending = true; return }
      clearTimeout(timer)
      timer = undefined
      pending = false
      busy = true
      const end = lastStarted = Date.now()
      const duration = periodMinutes[period] * 60_000
      const nextWindows = {
        currentStart: new Date(end - duration).toISOString(),
        currentEnd: new Date(end).toISOString(),
        previousStart: new Date(end - 2 * duration).toISOString(),
        previousEnd: new Date(end - duration).toISOString(),
      }
      if (!alertsLoaded.value) alertPhase.value = 'loading'
      if (!comparisonLoaded.value) comparisonPhase.value = 'loading'
      const fetcher = (input: RequestInfo | URL, init?: RequestInit) =>
        fetch(input, { ...init, signal: controller.signal })
      const [alertResult, currentResult, previousResult] = await Promise.allSettled([
        fetchAlerts({ baseUrl: apiBaseUrl, deviceId, auth,
          start: nextWindows.currentStart, end: nextWindows.currentEnd, fetcher }),
        fetchMonitoringHistory({ baseUrl: apiBaseUrl, deviceId, period, token: auth,
          start: nextWindows.currentStart, end: nextWindows.currentEnd, fetcher }),
        fetchMonitoringHistory({ baseUrl: apiBaseUrl, deviceId, period, token: auth,
          start: nextWindows.previousStart, end: nextWindows.previousEnd, fetcher }),
      ])
      if (controller.signal.aborted) return

      if (alertResult.status === 'fulfilled') {
        alerts.value = alertResult.value
        alertsLoaded.value = true
        alertDetailsShown.value ||= alertResult.value.length > 0
        alertPhase.value = 'ready'
      } else {
        alertPhase.value = 'error'
      }
      if (currentResult.status === 'fulfilled' && previousResult.status === 'fulfilled' &&
          currentResult.value.deviceId === deviceId && previousResult.value.deviceId === deviceId) {
        current.value = currentResult.value.readings
        previous.value = previousResult.value.readings
        windows.value = nextWindows
        limits.value = { current: currentResult.value.limit, previous: previousResult.value.limit }
        comparisonLoaded.value = true
        comparisonPhase.value = 'ready'
      } else {
        comparisonPhase.value = 'error'
      }
      busy = false
      if (pending) schedule()
    }
    refreshNow = () => { void refresh() }
    queueRefresh = schedule
    void refresh()
  }, { immediate: true })

watch(() => props.revision, () => queueRefresh())

const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const openAlerts = computed(() => alerts.value.filter((alert) => alert.status === 'open').length)
const comparisonPeriods = computed(() => [
  { name: 'selecionado', readings: current.value, start: windows.value.currentStart, end: windows.value.currentEnd, limit: limits.value.current },
  { name: 'anterior', readings: previous.value, start: windows.value.previousStart, end: windows.value.previousEnd, limit: limits.value.previous },
].map((interval) => {
  const readings = [...interval.readings].sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at))
  return { ...interval, readings, series: buildTemperatureChart(readings) }
}))
const periodsWithReadings = computed(() => comparisonPeriods.value.filter((interval) => interval.readings.length > 0))
const missingPeriod = computed(() => comparisonPeriods.value.find((interval) => !interval.readings.length))
const comparisonLabel = computed(() => periodsWithReadings.value.length === 2
  ? 'Gráfico de temperaturas dos períodos selecionado e anterior, alinhados pelo tempo decorrido'
  : `Gráfico de temperatura do período ${periodsWithReadings.value[0]?.name}`)
const chartData = computed<ChartData<'line', { x: number; y: number | null }[]>>(() => ({
  datasets: periodsWithReadings.value.map((interval) => {
    const isPrevious = interval.name === 'anterior'
    const color = isPrevious ? colors.value.muted : colors.value.accent
    const offset = Date.parse(interval.start)
    return {
      label: `Período ${interval.name}`,
      data: interval.series.points.map(({ x, y }) => ({ x: (x - offset) / 60_000, y })),
      borderColor: color,
      backgroundColor: color,
      borderDash: isPrevious ? [6, 4] : [],
      borderWidth: 2,
      pointRadius: interval.readings.length >= interval.limit ? 1 : 2,
      pointHoverRadius: 4,
      tension: 0,
      spanGaps: false,
    }
  }),
}))

const chartOptions = computed<ChartOptions<'line'>>(() => ({
  locale: 'pt-BR',
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  parsing: false,
  plugins: { legend: { labels: { color: colors.value.muted } } },
  scales: {
    x: {
      type: 'linear', min: 0, max: periodMinutes[props.period],
      title: { display: true, text: 'Minutos desde o início de cada período', color: colors.value.muted },
      ticks: { color: colors.value.muted },
      grid: { color: colors.value.line },
    },
    y: {
      title: { display: true, text: 'Temperatura (°C)', color: colors.value.muted },
      ticks: { color: colors.value.muted },
      grid: { color: colors.value.line },
    },
  },
}))

function describe(readings: readonly HistoricalReading[]) {
  const mean = readings.reduce((sum, reading) => sum + reading.temperature_c, 0) / readings.length
  return `média de ${mean.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} °C.`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
  }).format(new Date(value))
}
</script>

<template>
  <div ref="panel" class="grid items-start gap-4 xl:gap-6" :class="{ 'xl:grid-cols-2': $slots.default }">
    <section aria-labelledby="device-alerts-title" class="panel min-w-0 rounded-panel border border-line bg-surface px-4 py-3">
      <h2 id="device-alerts-title" class="font-semibold">Alertas do dispositivo <span class="text-sm font-normal text-ink-muted">· {{ period }}</span></h2>
      <p v-if="!deviceId || !auth" class="mt-1 text-sm text-ink-muted">Selecione um dispositivo e entre na conta para consultar alertas.</p>
      <p v-else-if="alertPhase === 'loading'" class="mt-1 text-sm text-ink-muted" role="status">Carregando alertas…</p>
      <p v-else-if="alertPhase === 'error'" class="mt-1 text-sm text-status-stale" role="status">{{ alertsLoaded ? 'Não foi possível atualizar os alertas. Exibindo os últimos dados recebidos.' : 'Não foi possível carregar os alertas.' }}</p>
      <p v-if="alertsLoaded" class="mt-1 text-sm" :class="openAlerts ? 'font-medium text-status-attention' : 'text-ink-muted'" role="status">
        {{ alerts.length ? `${openAlerts} em aberto · ${alerts.length} no período` : 'Nenhum alerta neste período.' }}
        <span v-if="alerts.length >= 300">A consulta atingiu o limite de 300 alertas.</span>
      </p>
      <details v-if="alertDetailsShown">
        <summary class="min-h-11 cursor-pointer py-2 text-sm font-medium text-accent">Ver alertas do período</summary>
        <ul v-if="alerts.length" class="divide-y divide-line">
          <li v-for="alert in alerts" :key="alert.alert_id" class="py-3 text-sm">
            <p class="font-medium">{{ alert.kind === 'temperature_high' ? 'Temperatura acima do limite' : 'Temperatura abaixo do limite' }} · {{ alert.status === 'open' ? 'Aberto' : 'Encerrado' }}</p>
            <p class="mt-1 text-ink-muted">Aberto em {{ formatDate(alert.opened_at) }}<template v-if="alert.closed_at"> · Encerrado em {{ formatDate(alert.closed_at) }}</template></p>
          </li>
        </ul>
        <p v-else class="text-sm text-ink-muted">A última consulta não encontrou alertas neste período.</p>
      </details>
    </section>

    <slot />

    <section aria-labelledby="temperature-comparison-title" class="comparison col-span-full min-w-0 rounded-panel border border-line bg-surface p-6">
      <header class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="temperature-comparison-title" class="text-xl font-semibold">Comparação de temperatura</h2>
          <p class="mt-1 text-sm text-ink-muted">Períodos de {{ period }}: selecionado e anterior.</p>
        </div>
        <button v-if="deviceId && auth" type="button" class="min-h-11 rounded-md border border-control-border px-3 py-2 text-sm font-medium text-accent hover:bg-surface-muted" @click="refreshNow">Atualizar alertas e comparação</button>
      </header>
      <p v-if="!deviceId || !auth" class="mt-5 text-sm text-ink-muted">Selecione um dispositivo para comparar leituras.</p>
      <p v-else-if="comparisonPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">Carregando comparação…</p>
      <p v-else-if="comparisonPhase === 'error'" class="mt-5 text-sm text-status-stale" role="status">{{ comparisonLoaded ? 'Não foi possível atualizar a comparação. Exibindo os últimos dados recebidos.' : 'Não foi possível comparar as leituras.' }}</p>
      <template v-if="comparisonLoaded">
        <p v-if="!periodsWithReadings.length" class="mt-5 text-sm text-ink-muted">Não há leituras em nenhum dos dois períodos.</p>
        <template v-else>
          <div id="comparison-note" class="mt-4 max-w-prose text-sm leading-6 text-ink-muted">
            <p v-if="missingPeriod" class="font-medium text-ink">Sem leituras no período {{ missingPeriod.name }} para comparar.</p>
            <p v-else>O gráfico alinha os períodos pelos minutos desde o início de cada um.</p>
            <p v-if="periodsWithReadings.some((interval) => interval.series.gaps)">A linha é interrompida onde passaram mais de 30 s sem leitura.</p>
          </div>
          <dl class="mt-4 flex flex-wrap gap-x-8 gap-y-3 text-sm">
            <div v-for="interval in periodsWithReadings" :key="interval.name">
              <dt class="font-medium">Período {{ interval.name }}</dt>
              <dd class="mt-1 text-ink-muted">{{ describe(interval.readings) }} {{ interval.readings.length }} {{ interval.readings.length === 1 ? 'leitura' : 'leituras' }}.</dd>
              <dd v-if="interval.readings.length >= interval.limit" class="text-status-stale">Limite de {{ interval.limit }} atingido. Pode haver leituras anteriores neste período.</dd>
            </div>
          </dl>
          <div role="img" :aria-label="comparisonLabel" aria-describedby="comparison-note" class="mt-4 h-72 min-w-0 overflow-hidden">
            <Line aria-hidden="true" :data="chartData" :options="chartOptions" />
          </div>
          <details class="mt-4 border-t border-line pt-2">
            <summary class="min-h-11 cursor-pointer py-2 font-medium text-accent">Ver leituras de temperatura em tabela</summary>
            <div v-for="interval in periodsWithReadings" :key="interval.name" role="region" :aria-label="`Leituras do período ${interval.name}`" tabindex="0" class="mt-3 max-h-80 overflow-auto">
              <table class="w-full border-collapse text-left text-sm">
                <caption class="mb-2 text-left text-ink-muted">Período {{ interval.name }} · temperatura · fuso {{ timeZone }}</caption>
                <thead><tr class="border-b border-line"><th scope="col" class="py-2 pr-4">Horário</th><th scope="col" class="py-2 text-right">Temperatura</th></tr></thead>
                <tbody><tr v-for="(reading, index) in interval.readings" :key="`${reading.received_at}-${index}`" class="border-b border-line">
                  <td class="py-2 pr-4"><time :datetime="reading.received_at">{{ formatReadingTime(reading.received_at, timeZone) }}</time></td>
                  <td class="py-2 text-right">{{ reading.temperature_c.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) }} °C</td>
                </tr></tbody>
              </table>
            </div>
          </details>
          <details>
            <summary class="min-h-11 cursor-pointer py-2 font-medium text-accent">Ver horários e cobertura</summary>
            <p v-for="interval in periodsWithReadings" :key="interval.name" class="mb-2 max-w-prose text-sm leading-6 text-ink-muted">
              <strong>Período {{ interval.name }}:</strong> {{ formatReadingTime(interval.start, timeZone) }} a {{ formatReadingTime(interval.end, timeZone) }}.
              {{ describeHistoryCoverage(interval.readings, interval.limit, timeZone) }}
              <template v-if="interval.series.gaps">{{ interval.series.gaps }} {{ interval.series.gaps === 1 ? 'lacuna' : 'lacunas' }} de mais de 30 s.</template>
            </p>
          </details>
        </template>
      </template>
    </section>
  </div>
</template>

<style scoped>
.panel, .comparison { overflow-wrap: anywhere; }
@media (max-width: 767px) { .comparison { padding: var(--cs-space-16); } }
</style>
