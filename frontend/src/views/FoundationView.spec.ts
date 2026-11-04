// @vitest-environment happy-dom

import { useRoute } from 'vue-router'
import { clearMonitoringSelection } from '../features/account/session'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listDevices, listEnvironments } from '../features/account/catalog'
import { sessionToken, sessionRole } from '../features/account/session'
import { fetchActuators, fetchCommand, requestLed, type ActuatorCommand } from '../features/monitoring/actuators'
import { fetchMonitoringHistory } from '../features/monitoring/monitoring-history'
import type { MonitoringSummary } from '../features/monitoring/monitoring-summary'
import { useMonitoringSummary, type MonitoringEvent } from '../features/monitoring/use-monitoring-summary'
import { monitoringPollingIntervalMs } from '../features/monitoring/monitoring-polling'
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
vi.mock('vue-router', async (original) => {
  const actual = await original<typeof import('vue-router')>()
  const { reactive } = await import('vue')
  const route = reactive({ path: '/dashboard', query: {}, hash: '' })
  const navigate = async (target: object) => { Object.assign(route, target) }
  return { ...actual, useRoute: () => route, useRouter: () => ({ push: vi.fn(navigate), replace: vi.fn(navigate) }) }
})

const summary: MonitoringSummary = {
  environment: { id: '00000000-0000-4000-8000-000000000001', name: 'Laboratório Refrigerado' },
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
  Object.assign(useRoute(), { path: '/dashboard', query: {}, hash: '' })
  clearMonitoringSelection()

    vi.clearAllMocks()
    vi.mocked(fetchActuators).mockReset()
    vi.mocked(fetchCommand).mockReset()
    vi.mocked(requestLed).mockReset()
    sessionToken.value = 'token'
    sessionRole.value = 'operator'
    vi.mocked(listEnvironments).mockResolvedValue([{ id: '00000000-0000-4000-8000-000000000001', name: 'Laboratório Refrigerado' }])
    vi.mocked(listDevices).mockResolvedValue([
      { id: '00000000-0000-4000-8000-000000000011', environment_id: '00000000-0000-4000-8000-000000000001', name: 'Um', mqtt_device_id: 'esp32-lab-01', is_active: true },
      { id: '00000000-0000-4000-8000-000000000012', environment_id: '00000000-0000-4000-8000-000000000001', name: 'Dois', mqtt_device_id: 'esp32-lab-02', is_active: true },
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

  it('mostra seis medições, persistência e estado observado sem inventar confirmação', async () => {
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    const state = vi.mocked(useMonitoringSummary).mock.results[0]!.value as ReturnType<typeof useMonitoringSummary>
    state.summary.value = {
      ...summary, persistence: 'pending',
      reading: { ...summary.reading!, vibration_rms_mm_s: 0.123, motor_current_a: 1.456, motor_temperature_c: 38 },
      equipment: { equipment_id: 'equipment', running: true,
        led: { actuator_id: 'led', actual_state: true }, buzzer: { actuator_id: 'buzzer', actual_state: false } },
    }
    await flushPromises()
    expect(wrapper.text()).toContain('Vibração RMS')
    expect(wrapper.text()).toContain('0,123 mm/s')
    expect(wrapper.text()).toContain('1,456 A')
    expect(wrapper.text()).toContain('38 °C')
    expect(wrapper.text()).toContain('Gravação em andamento')
    expect(wrapper.text()).toContain('Luz observada na última leitura: Ligado')
    expect(wrapper.text()).toContain('Sem confirmação registrada')
    const metric = wrapper.get('select[aria-label="Medição do gráfico"]')
    await metric.setValue('vibration_rms_mm_s')
    expect(wrapper.getComponent({ name: 'TemperatureHistoryChart' }).props('metric')).toBe('vibration_rms_mm_s')
    wrapper.unmount()
  })

  it('distingue zero e ausência nas seis grandezas e mantém o título ligado ao seletor', async () => {
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true } } })
    const state = vi.mocked(useMonitoringSummary).mock.results[0]!.value as ReturnType<typeof useMonitoringSummary>
    state.summary.value = { ...summary, reading: { ...summary.reading!, temperature_c: 0, humidity_percent: 0, light_percent: null, motor_current_a: 0 } }
    await flushPromises()
    const measurements = wrapper.findAll('[aria-label="Medições do ambiente"] article')
    expect(measurements).toHaveLength(6)
    expect(measurements[0]!.text()).toContain('0 °C')
    expect(measurements[1]!.text()).toContain('0 %')
    expect(measurements[2]!.text()).toContain('—Sem leitura')
    expect(measurements[4]!.text()).toContain('0 A')
    await wrapper.get('select[aria-label="Medição do gráfico"]').setValue('motor_current_a')
    expect(wrapper.get('#temperature-history-title').text()).toBe('Histórico · corrente do motor')
    expect(wrapper.getComponent({ name: 'TemperatureHistoryChart' }).props('metric')).toBe('motor_current_a')
    wrapper.unmount()
  })

  it('bloqueia reenvio enquanto o POST LED ainda aguarda resposta', async () => {
    let resolve: ((value: ActuatorCommand) => void) | undefined
    vi.mocked(requestLed).mockImplementation(() => new Promise((done) => { resolve = done }))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    const button = wrapper.findAll('button').find((element) => element.text() === 'Ligar Luz')!
    await button.trigger('click')
    await button.trigger('click')
    expect(requestLed).toHaveBeenCalledOnce()
    expect(button.attributes('disabled')).toBeDefined()
    resolve?.(pending)
    await flushPromises()
    expect(wrapper.text()).toContain('Aguardando confirmação')
    wrapper.unmount()
  })

  it('uma consulta durante o envio não apaga a nova pendência LED', async () => {
    let resolvePost: ((value: ActuatorCommand) => void) | undefined
    let resolveSnapshot: ((value: { led: null; buzzer: null }) => void) | undefined
    vi.mocked(requestLed).mockImplementation(() => new Promise((done) => { resolvePost = done }))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolveSnapshot = done }))
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')!.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === 'Atualizar estado')!.trigger('click')
    resolvePost?.(pending)
    await flushPromises()
    resolveSnapshot?.({ led: null, buzzer: null })
    await flushPromises()
    expect(wrapper.text()).toContain('Aguardando confirmação')
    expect(wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')!.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('resposta atrasada do polling não reverte ACK confirmado para pending', async () => {
    vi.useFakeTimers()
    const responses: Array<(value: ActuatorCommand) => void> = []
    vi.mocked(fetchActuators).mockResolvedValue({ led: pending, buzzer: null })
    vi.mocked(fetchCommand).mockImplementation(() => new Promise((resolve) => { responses.push(resolve) }))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    try {
      await flushPromises()
      vi.advanceTimersByTime(2000)
      responses[1]?.({ ...pending, status: 'confirmed', confirmed_state: true })
      await flushPromises()
      responses[0]?.(pending)
      await flushPromises()
      expect(wrapper.text()).not.toContain('Aguardando confirmação')
      expect(wrapper.text()).toContain('Desligar Luz')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it.each(['viewer', null] as const)('permite monitorar sem emitir comando para papel %s', async (role) => {
    sessionRole.value = role
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    expect(wrapper.text()).toContain('35 %')
    expect(wrapper.text()).toContain('Faixa térmica atual: 2–8 °C')
    expect(fetchMonitoringHistory).toHaveBeenCalledWith(expect.objectContaining({
      token: 'token', deviceId: 'esp32-lab-01', period: '1h',
    }))
    expect(fetchActuators).toHaveBeenCalledWith('token', '00000000-0000-4000-8000-000000000011')

    await wrapper.findAll('select')[1]?.setValue('00000000-0000-4000-8000-000000000012')
    await flushPromises()
    expect(fetchMonitoringHistory).toHaveBeenLastCalledWith(expect.objectContaining({ deviceId: 'esp32-lab-02' }))
    expect(fetchActuators).toHaveBeenLastCalledWith('token', '00000000-0000-4000-8000-000000000012')
    wrapper.unmount()
  })

  it('mantém o gráfico e agrupa atualizações sem sobrepor consultas lentas', async () => {
    vi.useFakeTimers()
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true } } })
    try {
      await flushPromises()
      const result = await vi.mocked(fetchMonitoringHistory).mock.results[0]!.value
      const chart = wrapper.getComponent({ name: 'TemperatureHistoryChart' }).element
      const state = vi.mocked(useMonitoringSummary).mock.results[0]!.value as ReturnType<typeof useMonitoringSummary>
      let complete: ((value: typeof result) => void) | undefined
      vi.mocked(fetchMonitoringHistory).mockImplementationOnce(() => new Promise((resolve) => { complete = resolve }))
      for (let index = 0; index < 5; index++) {
        state.refreshRevision.value++
        await flushPromises()
      }
      expect(fetchMonitoringHistory).toHaveBeenCalledTimes(1)
      expect(wrapper.getComponent({ name: 'TemperatureHistoryChart' }).element).toBe(chart)
      await vi.advanceTimersByTimeAsync(monitoringPollingIntervalMs)
      expect(fetchMonitoringHistory).toHaveBeenCalledTimes(2)
      state.refreshRevision.value++
      await flushPromises()
      await vi.advanceTimersByTimeAsync(monitoringPollingIntervalMs)
      expect(fetchMonitoringHistory).toHaveBeenCalledTimes(2)
      expect(wrapper.text()).not.toContain('Carregando histórico')
      complete?.(result)
      await flushPromises()
      expect(wrapper.getComponent({ name: 'TemperatureHistoryChart' }).element).toBe(chart)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('conserva o histórico após erro de atualização e permite repetir', async () => {
    vi.useFakeTimers()
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true } } })
    try {
      await flushPromises()
      const chart = wrapper.getComponent({ name: 'TemperatureHistoryChart' }).element
      const state = vi.mocked(useMonitoringSummary).mock.results[0]!.value as ReturnType<typeof useMonitoringSummary>
      vi.mocked(fetchMonitoringHistory).mockRejectedValueOnce(new Error('Falha de atualização'))
      state.refreshRevision.value++
      await flushPromises()
      await vi.advanceTimersByTimeAsync(monitoringPollingIntervalMs)
      await flushPromises()
      expect(wrapper.getComponent({ name: 'TemperatureHistoryChart' }).element).toBe(chart)
      expect(wrapper.text()).toContain('Não foi possível atualizar o histórico')
      await wrapper.get('section[aria-labelledby="temperature-history-title"] p[role="status"] button').trigger('click')
      await flushPromises()
      expect(wrapper.text()).not.toContain('Não foi possível atualizar o histórico')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('limpa o histórico na troca de conta e ignora uma resposta da conta anterior', async () => {
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true } } })
    await flushPromises()
    const result = await vi.mocked(fetchMonitoringHistory).mock.results[0]!.value
    let complete: ((value: typeof result) => void) | undefined
    vi.mocked(fetchMonitoringHistory).mockImplementationOnce(() => new Promise((resolve) => { complete = resolve }))
    sessionToken.value = 'outra-conta'
    await flushPromises()
    expect(fetchMonitoringHistory).toHaveBeenCalledTimes(2)
    expect(wrapper.findComponent({ name: 'TemperatureHistoryChart' }).exists()).toBe(false)
    sessionToken.value = null
    await flushPromises()
    complete?.(result)
    await flushPromises()
    expect(wrapper.findComponent({ name: 'TemperatureHistoryChart' }).exists()).toBe(false)
    wrapper.unmount()
  })

  it('mantém o diagnóstico atual e permite repetir apenas o histórico com falha', async () => {
    vi.mocked(fetchMonitoringHistory).mockRejectedValueOnce(new Error('Histórico indisponível'))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    expect(wrapper.text()).toContain('5,2 °C')
    expect(wrapper.text()).toContain('histórico não pôde ser carregado')
    await wrapper.get('section[aria-labelledby="temperature-history-title"] p[role="status"] button').trigger('click')
    await flushPromises()
    expect(fetchMonitoringHistory).toHaveBeenCalledTimes(2)
    expect(wrapper.findComponent({ name: 'TemperatureHistoryChart' }).exists()).toBe(true)
    wrapper.unmount()
  })

  it('não anuncia LED ligado antes da confirmação do comando', async () => {
    vi.mocked(requestLed).mockResolvedValue(pending)
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Aguardando confirmação')
    expect(wrapper.text()).not.toContain('Luz manual Ligado')
    expect(requestLed).toHaveBeenCalledWith('token', '00000000-0000-4000-8000-000000000011', true)

    const onEvent = vi.mocked(useMonitoringSummary).mock.calls[0]?.[2]
    const event: MonitoringEvent = {
      schema_version: 2, type: 'command_status', device_id: 'esp32-lab-01',
      environment_id: '00000000-0000-4000-8000-000000000001', occurred_at: '2026-09-09T18:00:01Z',
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    const details = wrapper.get('details[aria-label="Estado dos atuadores"]')
    expect(details.attributes('open')).toBeUndefined()
    expect(details.get('summary').text()).toContain(`Luz manual: ${label}`)
    expect(details.get('summary').text()).toContain('Som de aviso automático: Sem confirmação registrada')
    wrapper.unmount()
  })

  it('avisa no cabeçalho fechado quando o estado dos atuadores falha', async () => {
    vi.mocked(fetchActuators).mockRejectedValueOnce(new Error('API indisponível'))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    expect(wrapper.get('details summary').text()).toContain('Estado dos atuadores indisponível')
    wrapper.unmount()
  })

  it('mantém a falha de envio visível no cabeçalho fechado', async () => {
    vi.mocked(requestLed).mockRejectedValueOnce(new Error('API indisponível'))
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')?.trigger('click')
    await flushPromises()
    expect(wrapper.get('details summary').text()).toContain('Não foi possível enviar o comando')
    wrapper.unmount()
  })

  it('isola uma pendência ao trocar de dispositivo', async () => {
    vi.mocked(requestLed).mockResolvedValue(pending)
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Ligar Luz')?.trigger('click')
    await flushPromises()
    expect(wrapper.get('details summary').text()).toContain('Aguardando confirmação')
    await wrapper.findAll('select')[1]?.setValue('00000000-0000-4000-8000-000000000012')
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('Não foi possível carregar ambientes ou dispositivos')
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
      expect(listEnvironments).toHaveBeenCalledTimes(2)
      expect(fetchActuators).toHaveBeenCalledWith('token', '00000000-0000-4000-8000-000000000011')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('recupera dispositivos automaticamente quando a API volta', async () => {
    vi.mocked(listDevices).mockRejectedValueOnce(new Error('API indisponível'))
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('Não foi possível carregar ambientes ou dispositivos')
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
      expect(listDevices).toHaveBeenCalledTimes(2)
      expect(fetchActuators).toHaveBeenCalledWith('token', '00000000-0000-4000-8000-000000000011')
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
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
    const empty = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    expect(empty.text()).toContain('Nenhum ambiente cadastrado')
    expect(fetchActuators).not.toHaveBeenCalled()
    empty.unmount()

    vi.mocked(listDevices).mockResolvedValueOnce([
      { id: '00000000-0000-4000-8000-000000000011', environment_id: '00000000-0000-4000-8000-000000000001', name: 'Inativo', mqtt_device_id: 'esp32-lab-01', is_active: false },
    ])
    vi.mocked(useMonitoringSummary).mockReturnValueOnce({
      loadSummary: vi.fn(), monitoringState: computed(() => ({ kind: 'no_data', history: 'unavailable' } as const)),
      refreshRevision: ref(0), summary: ref(null), connectionState: ref('offline'), ageSeconds: computed(() => null),
    })
    const inactive = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
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
    const wrapper = shallowMount(FoundationView, { global: { stubs: { LiveDataRegion: false, RouterLink: true, LedControl: false } } })
    await flushPromises()
    expect(wrapper.get('[aria-label="Diagnóstico atual"] h3').text()).toBe(label)
    if (kind === 'no_data') {
      expect(wrapper.get('.measurement .metric-value').text()).toBe('—')
      expect(wrapper.text()).toContain('Verifique se ele está ativo e enviando dados')
    }
    if (kind === 'stale') {
      expect(wrapper.text()).toContain('situação atual não está confirmada')
      expect(wrapper.text()).toContain('aguarde uma leitura nova')
    }
    wrapper.unmount()
  })
})
