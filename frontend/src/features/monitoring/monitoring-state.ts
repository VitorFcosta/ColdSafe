/** Estados publicados pelo contrato HTTP de monitoramento. */
export type ReadingStatus =
  | 'normal'
  | 'attention'
  | 'critical'
  | 'no_data'
  | 'stale'

export type SummaryState =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'ready'; status: ReadingStatus }

export type HistoryState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'ready' }
  | { phase: 'error' }

export type MonitoringStateInput = Readonly<{
  summary: SummaryState
  history: HistoryState
}>

export type MonitoringState =
  | Readonly<{ kind: 'loading' }>
  | Readonly<{ kind: 'service_error' }>
  | Readonly<{
      kind: ReadingStatus
      history: 'loading' | 'ready' | 'unavailable'
    }>

/**
 * Traduz o estado de rede e a classificação da API para o estado visual.
 * Uma falha no histórico é parcial: não apaga um diagnóstico atual já válido.
 */
export function resolveMonitoringState(
  input: MonitoringStateInput,
): MonitoringState {
  if (input.summary.phase === 'loading') {
    return { kind: 'loading' }
  }

  if (input.summary.phase === 'error') {
    return { kind: 'service_error' }
  }

  return {
    kind: input.summary.status,
    history: resolveHistoryState(input.history),
  }
}

function resolveHistoryState(
  history: HistoryState,
): 'loading' | 'ready' | 'unavailable' {
  if (history.phase === 'ready') {
    return 'ready'
  }

  if (history.phase === 'error') {
    return 'unavailable'
  }

  return 'loading'
}
