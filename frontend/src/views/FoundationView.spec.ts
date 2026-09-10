// @vitest-environment happy-dom

import { flushPromises, shallowMount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchMonitoringHistory, type MonitoringHistory } from '../features/monitoring/monitoring-history'
import type { MonitoringState } from '../features/monitoring/monitoring-state'
import type { MonitoringSummary } from '../features/monitoring/monitoring-summary'
import { useMonitoringSummary } from '../features/monitoring/use-monitoring-summary'
import FoundationView from './FoundationView.vue'

vi.mock('../features/monitoring/monitoring-history', async (importOriginal) => {
  const original = await importOriginal<typeof import('../features/monitoring/monitoring-history')>()

  return {
    ...original,
    fetchMonitoringHistory: vi.fn(),
  }
})

vi.mock('../features/monitoring/use-monitoring-summary', () => ({
  useMonitoringSummary: vi.fn(),
}))

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

const history: MonitoringHistory = {
  deviceId: 'esp32-lab-01',
  start: '2026-09-09T17:00:00Z',
  end: '2026-09-09T18:00:00Z',
  limit: 300,
  readings: [
    {
      temperature_c: 5.2,
      humidity_percent: 62.4,
      received_at: '2026-09-09T18:00:00Z',
      status: 'normal',
    },
  ],
}

function arrangeSummary(state: MonitoringState, value: MonitoringSummary | null = summary) {
  const loadSummary = vi.fn()
  const refreshRevision = ref(0)

  vi.mocked(useMonitoringSummary).mockReturnValue({
    loadSummary,
    monitoringState: computed(() => state),
    refreshRevision,
    summary: ref(value),
  })

  return { loadSummary, refreshRevision }
}

describe('FoundationView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mostra o carregamento sem consultar histórico antes de conhecer o dispositivo', () => {
    arrangeSummary({ kind: 'loading' }, null)

    const wrapper = shallowMount(FoundationView)

    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    expect(fetchMonitoringHistory).not.toHaveBeenCalled()
  })

  it('mostra erro do serviço e permite tentar novamente', async () => {
    const { loadSummary } = arrangeSummary({ kind: 'service_error' }, null)

    const wrapper = shallowMount(FoundationView)
    await wrapper.get('button').trigger('click')

    expect(wrapper.get('[role="alert"]').text()).toContain('Diagnóstico indisponível')
    expect(loadSummary).toHaveBeenCalledOnce()
  })

  it('renderiza o diagnóstico e recarrega o histórico ao trocar o período', async () => {
    const { refreshRevision } = arrangeSummary({ kind: 'normal', history: 'loading' })
    vi.mocked(fetchMonitoringHistory).mockResolvedValue(history)

    const wrapper = shallowMount(FoundationView)
    refreshRevision.value += 1
    await flushPromises()

    expect(wrapper.text()).toContain('Normal')
    expect(wrapper.text()).toContain('5,2 °C')
    expect(wrapper.text()).toContain('62,4 %')
    expect(wrapper.text()).toContain('Agora mesmo')
    expect(fetchMonitoringHistory).toHaveBeenCalledWith(
      expect.objectContaining({ deviceId: 'esp32-lab-01', period: '1h' }),
    )

    const periodButton = wrapper.findAll('button').find((button) => button.text() === '24h')
    await periodButton?.trigger('click')
    await flushPromises()

    expect(fetchMonitoringHistory).toHaveBeenLastCalledWith(
      expect.objectContaining({ deviceId: 'esp32-lab-01', period: '24h' }),
    )
  })

  it('preserva o diagnóstico atual quando somente o histórico falha', async () => {
    const { refreshRevision } = arrangeSummary({ kind: 'attention', history: 'unavailable' }, {
      ...summary,
      status: 'attention',
      freshness: { is_stale: false, age_seconds: 32 },
    })
    vi.mocked(fetchMonitoringHistory).mockRejectedValue(new Error('histórico indisponível'))

    const wrapper = shallowMount(FoundationView)
    refreshRevision.value += 1
    await flushPromises()

    expect(wrapper.text()).toContain('Atenção')
    expect(wrapper.text()).toContain('Há 32 s')
    expect(wrapper.get('[role="status"]').text()).toContain('histórico de temperatura não pôde ser carregado')
  })

  it.each([
    ['critical', 'Crítico'],
    ['stale', 'Leitura desatualizada'],
    ['no_data', 'Sem dados'],
  ] as const)('traduz o estado %s para uma mensagem operacional', (kind, label) => {
    arrangeSummary({ kind, history: 'loading' }, {
      ...summary,
      reading: kind === 'no_data' ? null : summary.reading,
      freshness: kind === 'no_data' ? null : { is_stale: true, age_seconds: 60 },
      status: kind,
    })

    const wrapper = shallowMount(FoundationView)

    expect(wrapper.text()).toContain(label)
    if (kind === 'no_data') {
      expect(wrapper.text()).toContain('Sem leitura recebida')
    } else {
      expect(wrapper.text()).toContain('Há 1 min')
    }
  })
})
