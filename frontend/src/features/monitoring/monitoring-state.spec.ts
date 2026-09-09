import { describe, expect, it } from 'vitest'

import { resolveMonitoringState } from './monitoring-state'

describe('resolveMonitoringState', () => {
  it('mostra loading enquanto o resumo ainda não respondeu', () => {
    expect(
      resolveMonitoringState({
        summary: { phase: 'loading' },
        history: { phase: 'idle' },
      }),
    ).toEqual({ kind: 'loading' })
  })

  it('mostra erro de serviço quando o resumo atual não pode ser consultado', () => {
    expect(
      resolveMonitoringState({
        summary: { phase: 'error' },
        history: { phase: 'idle' },
      }),
    ).toEqual({ kind: 'service_error' })
  })

  it.each(['no_data', 'normal', 'attention', 'critical', 'stale'] as const)(
    'preserva o estado %s vindo do contrato de resumo',
    (status) => {
      expect(
        resolveMonitoringState({
          summary: { phase: 'ready', status },
          history: { phase: 'ready' },
        }),
      ).toEqual({ kind: status, history: 'ready' })
    },
  )

  it('preserva o diagnóstico atual quando apenas o histórico falha', () => {
    expect(
      resolveMonitoringState({
        summary: { phase: 'ready', status: 'attention' },
        history: { phase: 'error' },
      }),
    ).toEqual({ kind: 'attention', history: 'unavailable' })
  })
})
