import { computed, onMounted, ref } from 'vue'

import { resolveMonitoringState, type SummaryState } from './monitoring-state'
import {
  fetchMonitoringSummary,
  type MonitoringSummary,
} from './monitoring-summary'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function useMonitoringSummary() {
  const summary = ref<MonitoringSummary | null>(null)
  const summaryState = ref<SummaryState>({ phase: 'loading' })

  const monitoringState = computed(() =>
    resolveMonitoringState({
      summary: summaryState.value,
      history: { phase: 'idle' },
    }),
  )

  async function loadSummary() {
    summaryState.value = { phase: 'loading' }

    try {
      summary.value = await fetchMonitoringSummary({
        baseUrl: apiBaseUrl,
        fetcher: fetch,
      })
      summaryState.value = { phase: 'ready', status: summary.value.status }
    } catch {
      summary.value = null
      summaryState.value = { phase: 'error' }
    }
  }

  onMounted(() => {
    void loadSummary()
  })

  return {
    loadSummary,
    monitoringState,
    summary,
  }
}
