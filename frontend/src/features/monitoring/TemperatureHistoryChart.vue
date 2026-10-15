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
import { sensorMetricByKey, type SensorMetricKey } from './sensor-metrics'
import { buildTemperatureChart, describeHistoryCoverage, describeTemperatureRange, formatHistoryTick, formatMetricValue, formatReadingTime } from './temperature-chart'

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, Legend)

const props = withDefaults(defineProps<{
  readings: readonly HistoricalReading[]
  period: HistoryPeriod
  start: string
  end: string
  limit: number
  thresholds: Readonly<{ min_c: number; max_c: number }> | null
  metric?: SensorMetricKey
}>(), { metric: 'temperature_c' })

const chartElement = useTemplateRef<HTMLElement>('chartElement')
const colors = shallowRef<{ accent?: string; muted?: string; line?: string; threshold?: string }>({})
const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const orderedReadings = computed(() => [...props.readings].sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at)))
const sensor = computed(() => sensorMetricByKey[props.metric])
const metricLabel = computed(() => props.metric === 'temperature_c' ? 'Temperatura' : sensor.value.label)
const accessibleMetricLabel = computed(() => metricLabel.value.charAt(0).toLowerCase() + metricLabel.value.slice(1))
const temperatureThresholds = computed(() => props.metric === 'temperature_c' ? props.thresholds : null)
const series = computed(() => buildTemperatureChart(orderedReadings.value, props.metric))

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
        label: `${metricLabel.value} (${sensor.value.unit})`,
        data: [...series.value.points],
        borderColor: colors.value.accent,
        backgroundColor: colors.value.accent,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        spanGaps: false,
      },
      ...temperatureThresholds.value ? ([
        { label: `Mínimo atual: ${temperatureThresholds.value.min_c} °C`, data: [{ x: start, y: temperatureThresholds.value.min_c }, { x: end, y: temperatureThresholds.value.min_c }] },
        { label: `Máximo atual: ${temperatureThresholds.value.max_c} °C`, data: [{ x: start, y: temperatureThresholds.value.max_c }, { x: end, y: temperatureThresholds.value.max_c }] },
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
          const value = context.parsed.y
          return value === null
            ? `${metricLabel.value} indisponível`
            : `${metricLabel.value}: ${value.toLocaleString('pt-BR')} ${sensor.value.unit}`
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
      title: { display: true, text: `${metricLabel.value} (${sensor.value.unit})`, color: colors.value.muted },
      ticks: { color: colors.value.muted },
    },
  },
}))

const textualSummary = computed(() => describeTemperatureRange(orderedReadings.value, props.period, props.metric))
const coverage = computed(() => describeHistoryCoverage(orderedReadings.value, props.limit, timeZone))

function formatReadingValue(reading: HistoricalReading): string {
  const value = reading[props.metric]
  return value == null ? 'Indisponível' : `${formatMetricValue(value, props.metric)} ${sensor.value.unit}`
}
</script>

<template>
  <div ref="chartElement" class="mt-5 min-w-0">
    <p id="temperature-history-summary" class="text-sm leading-6 text-ink-muted">
      {{ textualSummary }}
      <template v-if="series.gaps"> {{ series.gaps }} {{ series.gaps === 1 ? 'lacuna' : 'lacunas' }} de mais de 30 s sem leitura; a linha é interrompida nesses trechos.</template>
      Horários no fuso deste navegador ({{ timeZone }}).
    </p>
    <p id="temperature-history-note" class="mt-2 text-sm leading-6 text-ink-muted">
      <template v-if="temperatureThresholds">Linhas tracejadas: limites atuais do ambiente, {{ temperatureThresholds.min_c }}–{{ temperatureThresholds.max_c }} °C. O histórico não informa quais limites valiam em cada leitura.</template>
      <template v-else-if="metric === 'temperature_c'">Limites atuais indisponíveis para este ambiente.</template>
      A consulta retorna até {{ limit }} leituras mais recentes do período.
    </p>
    <p id="temperature-history-coverage" class="mt-2 text-sm leading-6 text-ink-muted">{{ coverage }}</p>

    <div
      v-if="readings.length > 0"
      role="img"
      :aria-label="metric === 'temperature_c' ? 'Gráfico de linha da temperatura no período selecionado' : `Gráfico de linha de ${accessibleMetricLabel} no período selecionado`"
      aria-describedby="temperature-history-summary temperature-history-note temperature-history-coverage"
      class="mt-5 h-72"
    >
      <Line :data="chartData" :options="chartOptions" />
    </div>
    <details v-if="orderedReadings.length" class="mt-5 border-t border-line pt-4">
      <summary class="min-h-11 cursor-pointer py-2 font-medium text-accent">Ver {{ orderedReadings.length }} {{ orderedReadings.length === 1 ? 'leitura' : 'leituras' }} em tabela</summary>
      <div role="region" :aria-label="`Leituras individuais de ${accessibleMetricLabel}`" tabindex="0" class="mt-3 max-h-80 overflow-auto">
        <table class="w-full border-collapse text-left text-sm">
          <caption class="mb-2 text-left text-ink-muted">Leituras individuais do período selecionado, no fuso {{ timeZone }}</caption>
          <thead><tr class="border-b border-line"><th scope="col" class="py-2 pr-4">Horário</th><th scope="col" class="py-2">{{ metricLabel }}</th></tr></thead>
          <tbody>
            <tr v-for="(reading, index) in orderedReadings" :key="`${reading.received_at}-${index}`" class="border-b border-line">
              <td class="py-2 pr-4"><time :datetime="reading.received_at">{{ formatReadingTime(reading.received_at, timeZone) }}</time></td>
              <td class="py-2">{{ formatReadingValue(reading) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>
