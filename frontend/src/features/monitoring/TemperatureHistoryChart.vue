<script setup lang="ts">
import {
  CategoryScale,
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
import { buildTemperatureChart, describeTemperatureRange } from './temperature-chart'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const props = defineProps<{
  readings: readonly HistoricalReading[]
  period: HistoryPeriod
}>()

const chartElement = useTemplateRef<HTMLElement>('chartElement')
const colors = shallowRef<{ accent?: string; muted?: string; line?: string }>({})

onMounted(() => {
  const style = getComputedStyle(chartElement.value!)
  colors.value = {
    accent: style.getPropertyValue('--cs-color-accent').trim(),
    muted: style.getPropertyValue('--cs-color-ink-muted').trim(),
    line: style.getPropertyValue('--cs-color-line').trim(),
  }
})

const chartData = computed<ChartData<'line'>>(() => {
  const series = buildTemperatureChart(props.readings, props.period)

  return {
    labels: [...series.labels],
    datasets: [
      {
        label: 'Temperatura (°C)',
        data: [...series.temperatures],
        borderColor: colors.value.accent,
        backgroundColor: colors.value.accent,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.2,
      },
    ],
  }
})

const chartOptions = computed<ChartOptions<'line'>>(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
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
    x: { ticks: { color: colors.value.muted, maxRotation: 0 }, grid: { display: false } },
    y: {
      grid: { color: colors.value.line },
      title: { display: true, text: 'Temperatura (°C)', color: colors.value.muted },
      ticks: { color: colors.value.muted },
    },
  },
}))

const textualSummary = computed(() => describeTemperatureRange(props.readings, props.period))
</script>

<template>
  <div ref="chartElement" class="mt-5 min-w-0">
    <p id="temperature-history-summary" class="text-sm leading-6 text-ink-muted">
      {{ textualSummary }} Horários exibidos em UTC.
    </p>

    <div
      v-if="readings.length > 0"
      role="img"
      aria-label="Gráfico de linha da temperatura no período selecionado"
      aria-describedby="temperature-history-summary"
      class="mt-5 h-72"
    >
      <Line :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
