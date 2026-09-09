import { computed, onMounted, onUnmounted, ref } from 'vue'

import { resolveMonitoringState, type SummaryState } from './monitoring-state'
import { startMonitoringPolling } from './monitoring-polling'
import {
  fetchMonitoringSummary,
  type MonitoringSummary,
} from './monitoring-summary'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function useMonitoringSummary() {
  const summary = ref<MonitoringSummary | null>(null)
  const summaryState = ref<SummaryState>({ phase: 'loading' })
  const refreshRevision = ref(0)
  let stopPolling: (() => void) | undefined
  let latestSummaryRequest = 0

  const monitoringState = computed(() =>
    resolveMonitoringState({
      summary: summaryState.value,
      history: { phase: 'idle' },
    }),
  )

  async function loadSummary() {
    const requestId = ++latestSummaryRequest

    if (summary.value === null) {
      summaryState.value = { phase: 'loading' }
    }

    try {
      const result = await fetchMonitoringSummary({
        baseUrl: apiBaseUrl,
        fetcher: fetch,
      })

      if (requestId !== latestSummaryRequest) return

      summary.value = result
      summaryState.value = { phase: 'ready', status: result.status }
      refreshRevision.value += 1
    } catch {
      if (requestId !== latestSummaryRequest) return

      summary.value = null
      summaryState.value = { phase: 'error' }
    }
  }

  onMounted(() => {
    stopPolling = startMonitoringPolling(loadSummary)
  })

  onUnmounted(() => {
    stopPolling?.()
  })

  return {
    loadSummary,
    monitoringState,
    refreshRevision,
    summary,
  }
}
