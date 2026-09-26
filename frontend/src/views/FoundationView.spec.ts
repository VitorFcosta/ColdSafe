// @vitest-environment happy-dom

import { flushPromises, shallowMount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listDevices, listEnvironments } from '../features/account/catalog'
import { sessionToken } from '../features/account/session'
import { fetchActuators, fetchCommand, requestLed, type ActuatorCommand } from '../features/monitoring/actuators'
import { fetchMonitoringHistory } from '../features/monitoring/monitoring-history'
import type { MonitoringSummary } from '../features/monitoring/monitoring-summary'
import { useMonitoringSummary, type MonitoringEvent } from '../features/monitoring/use-monitoring-summary'
import FoundationView from './FoundationView.vue'

vi.mock('../features/account/catalog', () => ({ listEnvironments: vi.fn(), listDevices: vi.fn() }))
vi.mock('../features/monitoring/actuators', async (importOriginal) => ({
  ...await importOriginal<typeof import('../features/monitoring/actuators')>(),
  fetchActuators: vi.fn(), requestLed: vi.fn(), fetchCommand: vi.fn(),
}))
vi.mock('../features/monitoring/monitoring-history', async (importOriginal) => ({
  ...await importOriginal<typeof import('../features/monitoring/monitoring-history')>(),
  fetchMonitoringHistory: vi.fn(),
}))
vi.mock('../features/monitoring/use-monitoring-summary', () => ({ useMonitoringSummary: vi.fn() }))
vi.mock('vue-router', async (importOriginal) => ({
  ...await importOriginal<typeof import('vue-router')>(),
  useRouter: () => ({ push: vi.fn() }),
}))

const summary: MonitoringSummary = {
  environment: { id: 'lab-01', name: 'Laboratório Refrigerado' },
  device: { id: 'esp32-lab-01' },
  reading: { temperature_c: 5.2, humidity_percent: 62.4, light_percent: 35, received_at: '2026-09-09T18:00:00Z' },
  status: 'normal', freshness: { is_stale: false, age_seconds: 4 },
  thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
}

const pending: ActuatorCommand = {
  schema_version: 2, command_id: 'command-01', device_id: 'esp32-lab-01', actuator: 'led',
  desired_state: true, confirmed_state: null, status: 'pending',
}

describe('FoundationView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionToken.value = 'token'
    vi.mocked(listEnvironments).mockResolvedValue([{ id: 'lab-01', name: 'Laboratório Refrigerado' }])
    vi.mocked(listDevices).mockResolvedValue([
      { id: 'uuid-01', environment_id: 'lab-01', name: 'Um', mqtt_device_id: 'esp32-lab-01', is_active: true },
      { id: 'uuid-02', environment_id: 'lab-01', name: 'Dois', mqtt_device_id: 'esp32-lab-02', is_active: true },
    ])
    vi.mocked(fetchMonitoringHistory).mockResolvedValue({
      deviceId: 'esp32-lab-01', start: '2026-09-09T17:00:00Z', end: '2026-09-09T18:00:00Z',
      limit: 300, readings: [],
    })
    vi.mocked(fetchActuators).mockResolvedValue({ led: null, buzzer: null })
    vi.mocked(useMonitoringSummary).mockReturnValue({
      loadSummary: vi.fn().mockResolvedValue(undefined),
      monitoringState: computed(() => ({ kind: 'normal', history: 'loading' } as const)),
      refreshRevision: ref(0), summary: ref(summary), connectionState: ref('connected'),
    })
  })

  it('seleciona dispositivo, mostra luminosidade e consulta o histórico autorizado', async () => {
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('35 %')
    expect(wrapper.text()).toContain('Faixa configurada: 2–8 °C')
    expect(fetchMonitoringHistory).toHaveBeenCalledWith(expect.objectContaining({
      token: 'token', deviceId: 'esp32-lab-01', period: '1h',
    }))
    expect(fetchActuators).toHaveBeenCalledWith('token', 'uuid-01')

    await wrapper.findAll('select')[1]?.setValue('uuid-02')
    await flushPromises()
    expect(fetchMonitoringHistory).toHaveBeenLastCalledWith(expect.objectContaining({ deviceId: 'esp32-lab-02' }))
    expect(fetchActuators).toHaveBeenLastCalledWith('token', 'uuid-02')
    wrapper.unmount()
  })

  it('não anuncia LED ligado antes da confirmação do comando', async () => {
    vi.mocked(requestLed).mockResolvedValue(pending)
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar LED')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Aguardando confirmação')
    expect(wrapper.text()).not.toContain('LED manual Ligado')
    expect(requestLed).toHaveBeenCalledWith('token', 'uuid-01', true)

    const onEvent = vi.mocked(useMonitoringSummary).mock.calls[0]?.[2]
    const event: MonitoringEvent = {
      schema_version: 2, type: 'command_status', device_id: 'esp32-lab-01',
      environment_id: 'lab-01', occurred_at: '2026-09-09T18:00:01Z',
      data: { ...pending, status: 'confirmed', confirmed_state: true },
    }
    onEvent?.(event)
    await flushPromises()
    expect(wrapper.text()).toContain('Desligar LED')
    wrapper.unmount()
  })

  it('continua consultando o comando após 15 segundos quando o simulador demora', async () => {
    vi.mocked(requestLed).mockResolvedValue(pending)
    vi.mocked(fetchCommand).mockImplementation(async () => {
      if (vi.mocked(fetchCommand).mock.calls.length < 16) return pending
      return { ...pending, status: 'confirmed', confirmed_state: true }
    })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      await wrapper.findAll('button').find((button) => button.text() === 'Ligar LED')?.trigger('click')
      await vi.advanceTimersByTimeAsync(16000)
      expect(fetchCommand).toHaveBeenCalledTimes(16)
      expect(wrapper.text()).toContain('Desligar LED')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('recupera ambientes automaticamente quando a API volta', async () => {
    vi.mocked(listEnvironments).mockRejectedValueOnce(new Error('API indisponível'))
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('Não foi possível carregar ambientes ou dispositivos')
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
      expect(listEnvironments).toHaveBeenCalledTimes(2)
      expect(fetchActuators).toHaveBeenCalledWith('token', 'uuid-01')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('recupera dispositivos automaticamente quando a API volta', async () => {
    vi.mocked(listDevices).mockRejectedValueOnce(new Error('API indisponível'))
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('Não foi possível carregar ambientes ou dispositivos')
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
      expect(listDevices).toHaveBeenCalledTimes(2)
      expect(fetchActuators).toHaveBeenCalledWith('token', 'uuid-01')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('não tenta recuperar o catálogo após sair do dashboard', async () => {
    let rejectRequest = (_error: Error) => {}
    vi.mocked(listEnvironments).mockImplementationOnce(() => new Promise((_, reject) => {
      rejectRequest = reject
    }))
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    wrapper.unmount()
    try {
      rejectRequest(new Error('API indisponível'))
      await flushPromises()
      await vi.advanceTimersByTimeAsync(2000)
      expect(listEnvironments).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
