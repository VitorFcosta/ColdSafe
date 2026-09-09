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
import { computed } from 'vue'
import { Line } from 'vue-chartjs'

import type { HistoricalReading, HistoryPeriod } from './monitoring-history'
import { buildTemperatureChart, describeTemperatureRange } from './temperature-chart'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const props = defineProps<{
  readings: readonly HistoricalReading[]
  period: HistoryPeriod
}>()

const chartData = computed<ChartData<'line'>>(() => {
  const series = buildTemperatureChart(props.readings, props.period)

  return {
    labels: [...series.labels],
    datasets: [
      {
        label: 'Temperatura (°C)',
        data: [...series.temperatures],
        borderColor: '#1c6470',
        backgroundColor: '#1c6470',
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.2,
      },
    ],
  }
})

const chartOptions: ChartOptions<'line'> = {
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
    x: { ticks: { color: '#52636a', maxRotation: 0 } },
    y: {
      title: { display: true, text: 'Temperatura (°C)', color: '#52636a' },
      ticks: { color: '#52636a' },
    },
  },
}

const textualSummary = computed(() => describeTemperatureRange(props.readings, props.period))
</script>

<template>
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
</template>
