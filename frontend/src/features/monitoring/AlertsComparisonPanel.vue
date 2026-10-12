<script setup lang="ts">
import {
  Chart as ChartJS, Legend, LineElement, LinearScale, PointElement, Tooltip,
  type ChartData, type ChartOptions,
} from 'chart.js'
import { computed, onMounted, ref, shallowRef, useTemplateRef, watch } from 'vue'
import { Line } from 'vue-chartjs'

import { fetchAlerts, type AlertRecord } from './alerts-api'
import { fetchMonitoringHistory, type HistoricalReading, type HistoryPeriod } from './monitoring-history'
import { describeHistoryCoverage } from './temperature-chart'

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
const refreshRevision = ref(0)
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

watch([() => props.auth, () => props.deviceId, () => props.period, () => props.revision, refreshRevision],
  async ([auth, deviceId, period], _previous, onCleanup) => {
    alerts.value = []
    current.value = []
    previous.value = []
    if (!auth || !deviceId) {
      alertPhase.value = 'idle'
      comparisonPhase.value = 'idle'
      return
    }

    const controller = new AbortController()
    onCleanup(() => controller.abort())
    const end = Date.now()
    const duration = periodMinutes[period] * 60_000
    windows.value = {
      currentStart: new Date(end - duration).toISOString(),
      currentEnd: new Date(end).toISOString(),
      previousStart: new Date(end - 2 * duration).toISOString(),
      previousEnd: new Date(end - duration).toISOString(),
    }
    alertPhase.value = 'loading'
    comparisonPhase.value = 'loading'
    const fetcher = (input: RequestInfo | URL, init?: RequestInit) =>
      fetch(input, { ...init, signal: controller.signal })
    const [alertResult, currentResult, previousResult] = await Promise.allSettled([
      fetchAlerts({ baseUrl: apiBaseUrl, deviceId, auth,
        start: windows.value.currentStart, end: windows.value.currentEnd, fetcher }),
      fetchMonitoringHistory({ baseUrl: apiBaseUrl, deviceId, period, token: auth,
        start: windows.value.currentStart, end: windows.value.currentEnd, fetcher }),
      fetchMonitoringHistory({ baseUrl: apiBaseUrl, deviceId, period, token: auth,
        start: windows.value.previousStart, end: windows.value.previousEnd, fetcher }),
    ])
    if (controller.signal.aborted) return

    if (alertResult.status === 'fulfilled') {
      alerts.value = alertResult.value
      alertPhase.value = 'ready'
    } else {
      alertPhase.value = 'error'
    }
    if (currentResult.status === 'fulfilled' && previousResult.status === 'fulfilled' &&
        currentResult.value.deviceId === deviceId && previousResult.value.deviceId === deviceId) {
      current.value = currentResult.value.readings
      previous.value = previousResult.value.readings
      limits.value = { current: currentResult.value.limit, previous: previousResult.value.limit }
      comparisonPhase.value = 'ready'
    } else {
      comparisonPhase.value = 'error'
    }
  }, { immediate: true })

const chartData = computed<ChartData<'line', { x: number; y: number }[]>>(() => ({
  datasets: [
    {
      label: 'Período selecionado',
      data: plot(current.value, windows.value.currentStart),
      borderColor: colors.value.accent,
      backgroundColor: colors.value.accent,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.2,
    },
    {
      label: 'Período anterior',
      data: plot(previous.value, windows.value.previousStart),
      borderColor: colors.value.muted,
      backgroundColor: colors.value.muted,
      borderDash: [6, 4],
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.2,
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
  return readings.map((reading) => ({
    x: (Date.parse(reading.received_at) - offset) / 60_000,
    y: reading.temperature_c,
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
  <section ref="panel" aria-label="Alertas e comparação de períodos" class="mt-8 grid gap-6 lg:grid-cols-2">
    <article class="min-w-0 rounded-panel border border-line bg-surface p-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-xs uppercase text-ink-muted">Histórico de alertas</p>
          <h2 class="mt-2 text-xl font-semibold">Alertas do dispositivo</h2>
        </div>
        <button v-if="deviceId && auth" type="button" class="min-h-11 rounded-md border border-control-border px-3 py-2 text-sm hover:bg-surface-muted" @click="refreshRevision++">Atualizar</button>
      </div>
      <p v-if="!deviceId || !auth" class="mt-5 text-sm text-ink-muted">Selecione um dispositivo e entre na conta para consultar alertas.</p>
      <p v-else-if="alertPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">Carregando alertas…</p>
      <p v-else-if="alertPhase === 'error'" class="mt-5 text-sm text-ink-muted" role="status">Não foi possível carregar os alertas.</p>
      <p v-else-if="alertPhase === 'ready' && !alerts.length" class="mt-5 text-sm text-ink-muted">Nenhum alerta neste período para o dispositivo selecionado.</p>
      <ul v-else-if="alertPhase === 'ready'" class="mt-5 divide-y divide-line">
        <li v-for="alert in alerts" :key="alert.alert_id" class="py-3 text-sm">
          <p class="font-medium">{{ alert.kind === 'temperature_high' ? 'Temperatura acima do limite' : 'Temperatura abaixo do limite' }} · {{ alert.status === 'open' ? 'Aberto' : 'Encerrado' }}</p>
          <p class="mt-1 text-ink-muted">Aberto em {{ formatDate(alert.opened_at) }}<template v-if="alert.closed_at"> · Encerrado em {{ formatDate(alert.closed_at) }}</template></p>
        </li>
      </ul>
    </article>

    <article class="min-w-0 rounded-panel border border-line bg-surface p-6">
      <p class="text-xs uppercase text-ink-muted">Comparação de temperatura</p>
      <h2 class="mt-2 text-xl font-semibold">{{ period }} atual e anterior</h2>
      <p class="mt-2 text-sm text-ink-muted">O período anterior termina quando o selecionado começa; ambos têm a mesma duração.</p>
      <p v-if="!deviceId || !auth" class="mt-5 text-sm text-ink-muted">Selecione um dispositivo para comparar leituras.</p>
      <p v-else-if="comparisonPhase === 'loading'" class="mt-5 text-sm text-ink-muted" aria-live="polite">Carregando comparação…</p>
      <p v-else-if="comparisonPhase === 'error'" class="mt-5 text-sm text-ink-muted" role="status">Não foi possível comparar as leituras. <button type="button" class="min-h-11 font-medium text-accent underline" @click="refreshRevision++">Tentar novamente</button></p>
      <template v-else-if="comparisonPhase === 'ready'">
        <dl class="mt-5 grid gap-4 text-sm sm:grid-cols-2">
          <div><dt class="font-medium">Selecionado</dt><dd class="mt-1 text-ink-muted">{{ describe(current) }}<br>{{ describeHistoryCoverage(current, limits.current) }}</dd></div>
          <div><dt class="font-medium">Anterior</dt><dd class="mt-1 text-ink-muted">{{ describe(previous) }}<br>{{ describeHistoryCoverage(previous, limits.previous) }}</dd></div>
        </dl>
        <p v-if="!current.length && !previous.length" class="mt-5 text-sm text-ink-muted">Não há leituras em nenhum dos dois períodos.</p>
        <div v-else role="img" aria-label="Gráfico de temperaturas dos períodos selecionado e anterior, alinhados pelo tempo decorrido" aria-describedby="comparison-note" class="mt-5 h-72 min-w-0 overflow-hidden">
          <Line :data="chartData" :options="chartOptions" />
        </div>
        <p id="comparison-note" class="mt-3 text-xs leading-5 text-ink-muted">Cada consulta retorna até 300 leituras mais recentes do intervalo. Os dois intervalos são alinhados pelo tempo decorrido, não pelo horário do dia.</p>
      </template>
    </article>
  </section>
</template>
