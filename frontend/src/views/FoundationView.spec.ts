// @vitest-environment happy-dom

import { flushPromises, shallowMount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listDevices, listEnvironments } from '../features/account/catalog'
import { sessionToken, sessionRole } from '../features/account/session'
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
vi.mock('../features/monitoring/use-monitoring-summary', async (importOriginal) => ({
  ...await importOriginal<typeof import('../features/monitoring/use-monitoring-summary')>(),
  useMonitoringSummary: vi.fn(),
}))
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
    sessionRole.value = 'operator'
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
      ageSeconds: computed(() => summary.freshness?.age_seconds ?? null),
    })
  })

  it.each(['viewer', null] as const)('permite monitorar sem emitir comando para papel %s', async (role) => {
    sessionRole.value = role
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain(role === 'viewer' ? 'Modo visualizador' : 'Permissões ainda não confirmadas')
    const control = wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')!
    expect(control.attributes('disabled')).toBeDefined()
    await control.trigger('click')
    expect(requestLed).not.toHaveBeenCalled()
    expect(fetchActuators).toHaveBeenCalled()
    wrapper.unmount()
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

  it('mantém o diagnóstico atual e permite repetir apenas o histórico com falha', async () => {
    vi.mocked(fetchMonitoringHistory).mockRejectedValueOnce(new Error('Histórico indisponível'))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('5,2 °C')
    expect(wrapper.text()).toContain('histórico de temperatura não pôde ser carregado')
    await wrapper.get('section[aria-labelledby="temperature-history-title"] p[role="status"] button').trigger('click')
    await flushPromises()
    expect(fetchMonitoringHistory).toHaveBeenCalledTimes(2)
    expect(wrapper.findComponent({ name: 'TemperatureHistoryChart' }).exists()).toBe(true)
    wrapper.unmount()
  })

  it('não anuncia LED ligado antes da confirmação do comando', async () => {
    vi.mocked(requestLed).mockResolvedValue(pending)
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Aguardando confirmação')
    expect(wrapper.text()).not.toContain('Luz manual Ligado')
    expect(requestLed).toHaveBeenCalledWith('token', 'uuid-01', true)

    const onEvent = vi.mocked(useMonitoringSummary).mock.calls[0]?.[2]
    const event: MonitoringEvent = {
      schema_version: 2, type: 'command_status', device_id: 'esp32-lab-01',
      environment_id: 'lab-01', occurred_at: '2026-09-09T18:00:01Z',
      data: { ...pending, status: 'confirmed', confirmed_state: true },
    }
    onEvent?.(event)
    await flushPromises()
    expect(wrapper.text()).toContain('Desligar Luz')
    wrapper.unmount()
  })

  it.each([
    ['pending', 'Aguardando confirmação'],
    ['rejected', 'Comando rejeitado'],
    ['unconfirmed', 'Sem confirmação'],
  ] as const)('mantém %s visível no cabeçalho fechado dos atuadores', async (status, label) => {
    vi.mocked(fetchActuators).mockResolvedValueOnce({
      led: { ...pending, status }, buzzer: null,
    })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    const details = wrapper.get('details[aria-label="Estado dos atuadores"]')
    expect(details.attributes('open')).toBeUndefined()
    expect(details.get('summary').text()).toContain(`Luz manual: ${label}`)
    expect(details.get('summary').text()).toContain('Som de aviso automático: Sem confirmação registrada')
    wrapper.unmount()
  })

  it('avisa no cabeçalho fechado quando o estado dos atuadores falha', async () => {
    vi.mocked(fetchActuators).mockRejectedValueOnce(new Error('API indisponível'))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.get('details summary').text()).toContain('Estado dos atuadores indisponível')
    wrapper.unmount()
  })

  it('mantém a falha de envio visível no cabeçalho fechado', async () => {
    vi.mocked(requestLed).mockRejectedValueOnce(new Error('API indisponível'))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')?.trigger('click')
    await flushPromises()
    expect(wrapper.get('details summary').text()).toContain('Não foi possível enviar o comando')
    wrapper.unmount()
  })

  it('isola uma pendência ao trocar de dispositivo', async () => {
    vi.mocked(requestLed).mockResolvedValue(pending)
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')?.trigger('click')
    await flushPromises()
    expect(wrapper.get('details summary').text()).toContain('Aguardando confirmação')
    await wrapper.findAll('select')[1]?.setValue('uuid-02')
    await flushPromises()
    expect(wrapper.get('details summary').text()).not.toContain('Aguardando confirmação')
    expect(requestLed).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('reconsulta após reconectar sem reenviar comando', async () => {
    const connectionState = ref<'offline' | 'connected'>('offline')
    vi.mocked(useMonitoringSummary).mockReturnValue({
      loadSummary: vi.fn(), monitoringState: computed(() => ({ kind: 'normal', history: 'ready' } as const)),
      refreshRevision: ref(0), summary: ref(summary), connectionState,
      ageSeconds: computed(() => summary.freshness?.age_seconds ?? null),
    })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    const initialLoads = vi.mocked(fetchActuators).mock.calls.length
    connectionState.value = 'connected'
    await flushPromises()
    expect(fetchActuators).toHaveBeenCalledTimes(initialLoads + 1)
    expect(requestLed).not.toHaveBeenCalled()
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
      await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')?.trigger('click')
      await vi.advanceTimersByTimeAsync(16000)
      expect(fetchCommand).toHaveBeenCalledTimes(16)
      expect(wrapper.text()).toContain('Desligar Luz')
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

  it('orienta o usuário quando não há ambiente ou dispositivo ativo', async () => {
    vi.mocked(listEnvironments).mockResolvedValueOnce([])
    vi.mocked(useMonitoringSummary).mockReturnValueOnce({
      loadSummary: vi.fn(), monitoringState: computed(() => ({ kind: 'no_data', history: 'unavailable' } as const)),
      refreshRevision: ref(0), summary: ref(null), connectionState: ref('offline'), ageSeconds: computed(() => null),
    })
    const empty = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(empty.text()).toContain('Nenhum ambiente cadastrado')
    expect(fetchActuators).not.toHaveBeenCalled()
    empty.unmount()

    vi.mocked(listDevices).mockResolvedValueOnce([
      { id: 'uuid-01', environment_id: 'lab-01', name: 'Inativo', mqtt_device_id: 'esp32-lab-01', is_active: false },
    ])
    vi.mocked(useMonitoringSummary).mockReturnValueOnce({
      loadSummary: vi.fn(), monitoringState: computed(() => ({ kind: 'no_data', history: 'unavailable' } as const)),
      refreshRevision: ref(0), summary: ref(null), connectionState: ref('offline'), ageSeconds: computed(() => null),
    })
    const inactive = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(inactive.text()).toContain('Nenhum dispositivo ativo neste ambiente')
    expect(fetchActuators).not.toHaveBeenCalled()
    inactive.unmount()
  })

  it('não exibe uma leitura antiga como atual durante erro da API', async () => {
    const loadSummary = vi.fn()
    vi.mocked(useMonitoringSummary).mockReturnValue({
      loadSummary, monitoringState: computed(() => ({ kind: 'service_error', history: 'error' } as const)),
      refreshRevision: ref(0), summary: ref(summary), connectionState: ref('offline'),
      ageSeconds: computed(() => summary.freshness?.age_seconds ?? null),
    })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('Diagnóstico indisponível')
    expect(wrapper.find('.metrics-grid').exists()).toBe(false)
    await wrapper.findAll('button').find((button) => button.text() === 'Tentar novamente')?.trigger('click')
    expect(loadSummary).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('não exibe diagnóstico de outro ambiente mesmo quando o ID MQTT coincide', async () => {
    const loadSummary = vi.fn()
    vi.mocked(useMonitoringSummary).mockReturnValue({
      loadSummary, monitoringState: computed(() => ({ kind: 'normal', history: 'ready' } as const)),
      refreshRevision: ref(0), summary: ref({ ...summary, environment: { id: 'outro-ambiente', name: 'Outro ambiente' } }),
      connectionState: ref('connected'), ageSeconds: computed(() => 4),
    })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('A API retornou dados de outro ambiente')
    expect(wrapper.find('.status-panel').exists()).toBe(false)
    expect(wrapper.find('.metrics-grid').exists()).toBe(false)
    await wrapper.findAll('button').find((button) => button.text() === 'Tentar novamente')?.trigger('click')
    expect(loadSummary).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it.each([
    ['attention', 'Atenção'],
    ['critical', 'Crítico'],
    ['stale', 'Leitura desatualizada'],
    ['no_data', 'Sem dados'],
  ] as const)('mostra o estado %s com seu rótulo correto', async (kind, label) => {
    const currentSummary: MonitoringSummary = kind === 'no_data'
      ? { ...summary, status: kind, reading: null, freshness: null }
      : { ...summary, status: kind, freshness: { is_stale: kind === 'stale', age_seconds: kind === 'stale' ? 90 : 4 } }
    vi.mocked(useMonitoringSummary).mockReturnValue({
      loadSummary: vi.fn(), monitoringState: computed(() => ({ kind, history: 'ready' } as const)),
      refreshRevision: ref(0), summary: ref(currentSummary), connectionState: ref('connected'),
      ageSeconds: computed(() => currentSummary.freshness?.age_seconds ?? null),
    })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.get('.status-panel h2').text()).toBe(label)
    if (kind === 'no_data') {
      expect(wrapper.get('.temperature').text()).toBe('—')
      expect(wrapper.text()).toContain('Verifique se ele está ativo e enviando dados')
    }
    if (kind === 'stale') {
      expect(wrapper.text()).toContain('situação atual não está confirmada')
      expect(wrapper.text()).toContain('aguarde uma leitura nova')
    }
    wrapper.unmount()
  })
})
