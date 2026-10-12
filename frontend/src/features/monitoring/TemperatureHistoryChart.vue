<script setup lang="ts">
import {
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import { computed, onMounted, shallowRef, useTemplateRef } from 'vue'
import { Line } from 'vue-chartjs'

import type { HistoricalReading, HistoryPeriod } from './monitoring-history'
import { buildTemperatureChart, describeHistoryCoverage, describeTemperatureRange, formatHistoryTick, formatReadingTime } from './temperature-chart'

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, Legend)

const props = defineProps<{
  readings: readonly HistoricalReading[]
  period: HistoryPeriod
  start: string
  end: string
  limit: number
  thresholds: Readonly<{ min_c: number; max_c: number }> | null
}>()

const chartElement = useTemplateRef<HTMLElement>('chartElement')
const colors = shallowRef<{ accent?: string; muted?: string; line?: string; threshold?: string }>({})
const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const orderedReadings = computed(() => [...props.readings].sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at)))
const series = computed(() => buildTemperatureChart(orderedReadings.value))

onMounted(() => {
  const style = getComputedStyle(chartElement.value!)
  colors.value = {
    accent: style.getPropertyValue('--cs-color-accent').trim(),
    muted: style.getPropertyValue('--cs-color-ink-muted').trim(),
    line: style.getPropertyValue('--cs-color-line').trim(),
    threshold: style.getPropertyValue('--cs-color-status-attention').trim(),
  }
})

const chartData = computed<ChartData<'line', { x: number; y: number | null }[]>>(() => {
  const start = Date.parse(props.start)
  const end = Date.parse(props.end)
  return {
    datasets: [
      {
        label: 'Temperatura (°C)',
        data: [...series.value.points],
        borderColor: colors.value.accent,
        backgroundColor: colors.value.accent,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        spanGaps: false,
      },
      ...props.thresholds ? ([
        { label: `Mínimo atual: ${props.thresholds.min_c} °C`, data: [{ x: start, y: props.thresholds.min_c }, { x: end, y: props.thresholds.min_c }] },
        { label: `Máximo atual: ${props.thresholds.max_c} °C`, data: [{ x: start, y: props.thresholds.max_c }, { x: end, y: props.thresholds.max_c }] },
      ].map((dataset) => ({ ...dataset, borderColor: colors.value.threshold, borderDash: [6, 4], borderWidth: 1, pointRadius: 0, pointHoverRadius: 0 }))) : [],
    ],
  }
})

const chartOptions = computed<ChartOptions<'line'>>(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  parsing: false,
  plugins: {
    legend: { labels: { color: colors.value.muted } },
    tooltip: {
      filter: (context) => context.datasetIndex === 0,
      callbacks: {
        title: (items) => items[0]?.parsed.x != null ? formatHistoryTick(items[0].parsed.x, timeZone) : '',
        label: (context) => {
          const temperature = context.parsed.y
          return temperature === null
            ? 'Temperatura indisponível'
            : `Temperatura: ${temperature.toLocaleString('pt-BR')} °C`
        },
      },
    },
  },
  scales: {
    x: {
      type: 'linear', min: Date.parse(props.start), max: Date.parse(props.end),
      ticks: { color: colors.value.muted, maxRotation: 0, maxTicksLimit: 4,
        callback: (value) => formatHistoryTick(Number(value), timeZone) },
      grid: { color: colors.value.line },
    },
    y: {
      grid: { color: colors.value.line },
      title: { display: true, text: 'Temperatura (°C)', color: colors.value.muted },
      ticks: { color: colors.value.muted },
    },
  },
}))

const textualSummary = computed(() => describeTemperatureRange(orderedReadings.value, props.period))
const coverage = computed(() => describeHistoryCoverage(orderedReadings.value, props.limit, timeZone))
</script>

<template>
  <div ref="chartElement" class="mt-5 min-w-0">
    <p id="temperature-history-summary" class="text-sm leading-6 text-ink-muted">
      {{ textualSummary }}
      <template v-if="series.gaps"> {{ series.gaps }} {{ series.gaps === 1 ? 'lacuna' : 'lacunas' }} de mais de 30 s sem leitura; a linha é interrompida nesses trechos.</template>
      Horários no fuso deste navegador ({{ timeZone }}).
    </p>
    <p id="temperature-history-note" class="mt-2 text-sm leading-6 text-ink-muted">
      <template v-if="thresholds">Linhas tracejadas: limites atuais do ambiente, {{ thresholds.min_c }}–{{ thresholds.max_c }} °C. O histórico não informa quais limites valiam em cada leitura.</template>
      <template v-else>Limites atuais indisponíveis para este ambiente.</template>
      A consulta retorna até {{ limit }} leituras mais recentes do período.
    </p>
    <p id="temperature-history-coverage" class="mt-2 text-sm leading-6 text-ink-muted">{{ coverage }}</p>

    <div
      v-if="readings.length > 0"
      role="img"
      aria-label="Gráfico de linha da temperatura no período selecionado"
      aria-describedby="temperature-history-summary temperature-history-note temperature-history-coverage"
      class="mt-5 h-72"
    >
      <Line :data="chartData" :options="chartOptions" />
    </div>
    <details v-if="orderedReadings.length" class="mt-5 border-t border-line pt-4">
      <summary class="min-h-11 cursor-pointer py-2 font-medium text-accent">Ver {{ orderedReadings.length }} {{ orderedReadings.length === 1 ? 'leitura' : 'leituras' }} em tabela</summary>
      <div role="region" aria-label="Leituras individuais de temperatura" tabindex="0" class="mt-3 max-h-80 overflow-auto">
        <table class="w-full border-collapse text-left text-sm">
          <caption class="mb-2 text-left text-ink-muted">Leituras individuais do período selecionado, no fuso {{ timeZone }}</caption>
          <thead><tr class="border-b border-line"><th scope="col" class="py-2 pr-4">Horário</th><th scope="col" class="py-2">Temperatura</th></tr></thead>
          <tbody>
            <tr v-for="(reading, index) in orderedReadings" :key="`${reading.received_at}-${index}`" class="border-b border-line">
              <td class="py-2 pr-4"><time :datetime="reading.received_at">{{ formatReadingTime(reading.received_at, timeZone) }}</time></td>
              <td class="py-2">{{ reading.temperature_c.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) }} °C</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>
