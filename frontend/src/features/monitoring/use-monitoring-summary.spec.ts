// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { startMonitoringPolling } from './monitoring-polling'
import { fetchMonitoringSummary, type MonitoringSummary } from './monitoring-summary'
import { useMonitoringSummary } from './use-monitoring-summary'

vi.mock('./monitoring-polling', () => ({
  startMonitoringPolling: vi.fn(),
}))

vi.mock('./monitoring-summary', async (importOriginal) => {
  const original = await importOriginal<typeof import('./monitoring-summary')>()

  return {
    ...original,
    fetchMonitoringSummary: vi.fn(),
  }
})

const summary: MonitoringSummary = {
  environment: { id: 'lab-01', name: 'Laboratório Refrigerado' },
  device: { id: 'esp32-lab-01' },
  reading: {
    temperature_c: 5.2,
    humidity_percent: 62.4,
    received_at: '2026-09-09T18:00:00Z',
  },
  status: 'normal',
  freshness: { is_stale: false, age_seconds: 4 },
  thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
}

const TestHost = defineComponent({
  setup: useMonitoringSummary,
  template: '<p>{{ monitoringState.kind }}:{{ refreshRevision }}:{{ summary?.device.id }}</p>',
})

describe('useMonitoringSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('carrega imediatamente, publica o resumo e interrompe o polling ao desmontar', async () => {
    const stopPolling = vi.fn()
    vi.mocked(fetchMonitoringSummary).mockResolvedValue(summary)
    vi.mocked(startMonitoringPolling).mockImplementation((refresh) => {
      void refresh()
      return stopPolling
    })

    const wrapper = mount(TestHost)
    await flushPromises()

    expect(wrapper.text()).toBe('normal:1:esp32-lab-01')
    expect(fetchMonitoringSummary).toHaveBeenCalledOnce()

    wrapper.unmount()

    expect(stopPolling).toHaveBeenCalledOnce()
  })

  it('expõe erro de serviço sem manter uma leitura anterior como atual', async () => {
    vi.mocked(fetchMonitoringSummary).mockRejectedValue(new Error('API indisponível'))
    vi.mocked(startMonitoringPolling).mockImplementation((refresh) => {
      void refresh()
      return vi.fn()
    })

    const wrapper = mount(TestHost)
    await flushPromises()

    expect(wrapper.text()).toBe('service_error:0:')
  })

  it('ignora uma resposta antiga que termina depois da atualização mais recente', async () => {
    let resolveOlderRequest: ((value: MonitoringSummary) => void) | undefined
    const olderRequest = new Promise<MonitoringSummary>((resolve) => {
      resolveOlderRequest = resolve
    })

    vi.mocked(startMonitoringPolling).mockReturnValue(vi.fn())
    vi.mocked(fetchMonitoringSummary)
      .mockReturnValueOnce(olderRequest)
      .mockResolvedValueOnce({ ...summary, status: 'attention' })

    const wrapper = mount(TestHost)
    const exposed = wrapper.vm as unknown as ReturnType<typeof useMonitoringSummary>

    const firstLoad = exposed.loadSummary()
    await exposed.loadSummary()
    resolveOlderRequest?.(summary)
    await firstLoad
    await flushPromises()

    expect(wrapper.text()).toBe('attention:1:esp32-lab-01')
  })
})
