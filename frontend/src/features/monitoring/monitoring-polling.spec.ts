import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  monitoringPollingIntervalMs,
  startMonitoringPolling,
} from './monitoring-polling'

describe('startMonitoringPolling', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('executa a atualização imediatamente e depois a cada cinco segundos', () => {
    vi.useFakeTimers()
    const refresh = vi.fn()

    const stop = startMonitoringPolling(refresh)

    expect(refresh).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(monitoringPollingIntervalMs)

    expect(refresh).toHaveBeenCalledTimes(2)

    stop()
  })

  it('interrompe atualizações ao desmontar o dashboard', () => {
    vi.useFakeTimers()
    const refresh = vi.fn()
    const stop = startMonitoringPolling(refresh)

    stop()
    vi.advanceTimersByTime(monitoringPollingIntervalMs * 2)

    expect(refresh).toHaveBeenCalledTimes(1)
  })
})
