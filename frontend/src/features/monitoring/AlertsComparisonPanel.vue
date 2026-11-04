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
const comparisonPeriods = computed(() => [
  { label: 'Selecionado', readings: [...current.value].sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at)), start: windows.value.currentStart, end: windows.value.currentEnd },
  { label: 'Anterior', readings: [...previous.value].sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at)), start: windows.value.previousStart, end: windows.value.previousEnd },
])
const chartData = computed<ChartData<'line', { x: number; y: number | null }[]>>(() => ({
  datasets: [
    {
      label: 'Período selecionado',
      data: plot(current.value, windows.value.currentStart),
      borderColor: colors.value.accent,
      backgroundColor: colors.value.accent,
      pointRadius: 2,
      pointHoverRadius: 4,
      tension: 0,
      spanGaps: false,
    },
    {
      label: 'Período anterior',
      data: plot(previous.value, windows.value.previousStart),
      borderColor: colors.value.muted,
      backgroundColor: colors.value.muted,
      borderDash: [6, 4],
      pointRadius: 2,
      pointHoverRadius: 4,
      tension: 0,
      spanGaps: false,
    },
  ],
}))

const chartOptions = computed<ChartOptions<'line'>>(() => ({
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

function plot(readings: readonly HistoricalReading[], start: string) {
  const offset = Date.parse(start)
  return buildTemperatureChart(readings).points.map((point) => ({
    x: (point.x - offset) / 60_000,
    y: point.y,
  }))
}

function describe(readings: readonly HistoricalReading[]) {
  if (!readings.length) return 'Sem leituras neste intervalo.'
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
  <section ref="panel" aria-label="Alertas e comparação de períodos" class="mt-8 grid items-start gap-6 lg:grid-cols-2">
    <article class="min-w-0 rounded-panel border border-line bg-surface p-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 class="text-xl font-semibold">Alertas do dispositivo</h2>
          <p class="mt-2 text-sm text-ink-muted">Histórico · {{ period }}</p>
        </div>
        <button v-if="deviceId && auth" type="button" class="min-h-11 rounded-md border border-control-border px-3 py-2 text-sm hover:bg-surface-muted" @click="refreshNow">Atualizar</button>
      </div>
      <p v-if="!deviceId || !auth" class="mt-5 text-sm text-ink-muted">Selecione um dispositivo e entre na conta para consultar alertas.</p>
      <p v-else-if="alertPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">Carregando alertas…</p>
      <p v-else-if="alertPhase === 'error'" class="mt-5 text-sm text-ink-muted" role="status">{{ alertsLoaded ? 'Não foi possível atualizar os alertas. Exibindo os últimos dados recebidos.' : 'Não foi possível carregar os alertas.' }}</p>
      <p v-if="alertsLoaded && !alerts.length" class="mt-5 text-sm text-ink-muted">Nenhum alerta neste período para o dispositivo selecionado.</p>
      <ul v-else-if="alertsLoaded" class="mt-5 divide-y divide-line">
        <li v-for="alert in alerts" :key="alert.alert_id" class="py-3 text-sm">
          <p class="font-medium">{{ alert.kind === 'temperature_high' ? 'Temperatura acima do limite' : 'Temperatura abaixo do limite' }} · {{ alert.status === 'open' ? 'Aberto' : 'Encerrado' }}</p>
          <p class="mt-1 text-ink-muted">Aberto em {{ formatDate(alert.opened_at) }}<template v-if="alert.closed_at"> · Encerrado em {{ formatDate(alert.closed_at) }}</template></p>
        </li>
      </ul>
    </article>

    <article class="min-w-0 rounded-panel border border-line bg-surface p-6">
      <h2 class="text-xl font-semibold">Comparação de temperatura</h2>
      <p class="mt-2 font-medium">{{ period }} atual e anterior</p>
      <p class="mt-2 text-sm text-ink-muted">O período anterior termina quando o selecionado começa; ambos têm a mesma duração.</p>
      <p v-if="!deviceId || !auth" class="mt-5 text-sm text-ink-muted">Selecione um dispositivo para comparar leituras.</p>
      <p v-else-if="comparisonPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">Carregando comparação…</p>
      <p v-else-if="comparisonPhase === 'error'" class="mt-5 text-sm text-ink-muted" role="status">{{ comparisonLoaded ? 'Não foi possível atualizar a comparação. Exibindo os últimos dados recebidos.' : 'Não foi possível comparar as leituras.' }} <button type="button" class="min-h-11 font-medium text-accent underline" @click="refreshNow">Tentar novamente</button></p>
      <template v-if="comparisonLoaded">
        <dl class="mt-5 grid gap-4 text-sm sm:grid-cols-2">
          <div><dt class="font-medium">Selecionado</dt><dd class="mt-1 text-ink-muted">{{ describe(current) }}<br>{{ describeHistoryCoverage(current, limits.current) }}</dd></div>
          <div><dt class="font-medium">Anterior</dt><dd class="mt-1 text-ink-muted">{{ describe(previous) }}<br>{{ describeHistoryCoverage(previous, limits.previous) }}</dd></div>
        </dl>
        <p v-if="!current.length && !previous.length" class="mt-5 text-sm text-ink-muted">Não há leituras em nenhum dos dois períodos.</p>
        <div v-else role="img" aria-label="Gráfico de temperaturas dos períodos selecionado e anterior, alinhados pelo tempo decorrido" aria-describedby="comparison-note" class="mt-5 h-72 min-w-0 overflow-hidden">
          <Line aria-hidden="true" :data="chartData" :options="chartOptions" />
        </div>
        <p id="comparison-note" class="mt-3 text-xs leading-5 text-ink-muted">Cada consulta retorna até 300 leituras mais recentes do intervalo. Os dois intervalos são alinhados pelo tempo decorrido, não pelo horário do dia.</p>
        <p v-for="interval in comparisonPeriods" :key="interval.label" class="mt-2 text-sm text-ink-muted">
          {{ interval.label }}: {{ formatReadingTime(interval.start, timeZone) }} a {{ formatReadingTime(interval.end, timeZone) }}.
          {{ buildTemperatureChart(interval.readings).gaps }} lacuna(s) de mais de 30 s; a linha é interrompida nesses trechos.
        </p>
        <details v-if="current.length || previous.length" class="mt-5 border-t border-line pt-4">
          <summary class="min-h-11 cursor-pointer py-2 font-medium text-accent">Ver leituras dos dois períodos em tabela</summary>
          <div v-for="interval in comparisonPeriods" :key="interval.label" role="region" :aria-label="`Leituras do período ${interval.label.toLocaleLowerCase('pt-BR')}`" tabindex="0" class="mt-3 max-h-80 overflow-auto">
            <table class="w-full border-collapse text-left text-sm">
              <caption class="mb-2 text-left text-ink-muted">{{ interval.label }} · temperatura · fuso {{ timeZone }}</caption>
              <thead><tr class="border-b border-line"><th scope="col" class="py-2 pr-4">Horário</th><th scope="col" class="py-2 text-right">Temperatura</th></tr></thead>
              <tbody><tr v-for="(reading, index) in interval.readings" :key="`${reading.received_at}-${index}`" class="border-b border-line">
                <td class="py-2 pr-4"><time :datetime="reading.received_at">{{ formatReadingTime(reading.received_at, timeZone) }}</time></td>
                <td class="py-2 text-right">{{ reading.temperature_c.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) }} °C</td>
              </tr></tbody>
            </table>
          </div>
        </details>
      </template>
    </article>
  </section>
</template>

<style scoped>
article { overflow-wrap: anywhere; }
@media (max-width: 767px) { article { padding: var(--cs-space-16); } }
</style>
