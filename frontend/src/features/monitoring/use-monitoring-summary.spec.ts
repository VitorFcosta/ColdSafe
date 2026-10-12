// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchMonitoringSummary, type MonitoringSummary } from './monitoring-summary'
import { formatFreshness, useMonitoringSummary } from './use-monitoring-summary'

vi.mock('./monitoring-summary', async (importOriginal) => ({
  ...await importOriginal<typeof import('./monitoring-summary')>(),
  fetchMonitoringSummary: vi.fn(),
}))

const summary: MonitoringSummary = {
  environment: { id: 'lab-01', name: 'Laboratório' },
  device: { id: 'esp32-lab-01' },
  reading: { temperature_c: 5, humidity_percent: 60, light_percent: 42, received_at: '2026-09-09T18:00:00Z' },
  status: 'normal',
  freshness: { is_stale: false, age_seconds: 1 },
  thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
}

class FakeSocket {
  static instances: FakeSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((message: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []
  closed = false
  constructor(readonly url: URL) { FakeSocket.instances.push(this) }
  send(message: string) { this.sent.push(message) }
  close() { this.closed = true }
  open() { this.onopen?.() }
  message(deviceId: string) {
    this.onmessage?.({ data: JSON.stringify({
      schema_version: 2, type: 'reading', device_id: deviceId, environment_id: 'lab-01',
      occurred_at: '2026-09-09T18:00:00Z', data: { temperature_c: 5 },
    }) })
  }
}

it.each([
  [undefined, 'Sem leitura recebida'],
  [4.9, 'Agora mesmo'],
  [59.9, 'Há 59 s'],
  [60, 'Há 1 min'],
  [3599, 'Há 59 min'],
  [3600, 'Há 1 h'],
  [86399, 'Há 23 h'],
  [86400, 'Há 1 dia'],
  [172800, 'Há 2 dias'],
])('formata a idade %s como %s', (age, label) => {
  expect(formatFreshness(age)).toBe(label)
})

describe('useMonitoringSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    FakeSocket.instances = []
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.mocked(fetchMonitoringSummary).mockResolvedValue(summary)
  })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it('autentica o canal sem colocar token na URL e atualiza pelo evento do dispositivo selecionado', async () => {
    const token = ref<string | null>('private-token')
    const deviceId = ref<string | null>('esp32-lab-01')
    const onEvent = vi.fn()
    const Host = defineComponent({
      setup() { return useMonitoringSummary(token, deviceId, onEvent) },
      template: '<p>{{ monitoringState.kind }}:{{ refreshRevision }}</p>',
    })
    const wrapper = mount(Host)
    await flushPromises()

    expect(wrapper.text()).toBe('normal:1')
    expect(String(FakeSocket.instances[0]?.url)).toContain('device_id=esp32-lab-01')
    expect(String(FakeSocket.instances[0]?.url)).not.toContain('private-token')
    FakeSocket.instances[0]?.open()
    expect(FakeSocket.instances[0]?.sent).toEqual(['{"token":"private-token"}'])
    FakeSocket.instances[0]?.message('esp32-lab-02')
    expect(onEvent).not.toHaveBeenCalled()
    FakeSocket.instances[0]?.message('esp32-lab-01')
    await flushPromises()
    expect(onEvent).toHaveBeenCalledOnce()

    deviceId.value = 'esp32-lab-02'
    await flushPromises()
    expect(FakeSocket.instances[0]?.closed).toBe(true)
    expect(FakeSocket.instances).toHaveLength(2)
    wrapper.unmount()
    expect(FakeSocket.instances[1]?.closed).toBe(true)
  })

  it('descarta resposta REST atrasada da seleção anterior', async () => {
    let resolveFirst: ((value: MonitoringSummary) => void) | undefined
    vi.mocked(fetchMonitoringSummary)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ ...summary, device: { id: 'esp32-lab-02' }, status: 'attention' })
    const token = ref<string | null>('token')
    const deviceId = ref<string | null>('esp32-lab-01')
    const Host = defineComponent({
      setup() { return useMonitoringSummary(token, deviceId) },
      template: '<p>{{ monitoringState.kind }}:{{ summary?.device.id }}</p>',
    })
    const wrapper = mount(Host)
    deviceId.value = 'esp32-lab-02'
    await flushPromises()
    resolveFirst?.(summary)
    await flushPromises()
    expect(wrapper.text()).toBe('attention:esp32-lab-02')
    wrapper.unmount()
  })

  it('reconecta e recupera o estado REST após a queda do WebSocket', async () => {
    vi.useFakeTimers()
    const token = ref<string | null>('token')
    const deviceId = ref<string | null>('esp32-lab-01')
    const Host = defineComponent({
      setup() { return useMonitoringSummary(token, deviceId) },
      template: '<p>{{ connectionState }}</p>',
    })
    const wrapper = mount(Host)
    await flushPromises()
    FakeSocket.instances[0]?.open()
    await flushPromises()
    const beforeReconnect = vi.mocked(fetchMonitoringSummary).mock.calls.length
    FakeSocket.instances[0]?.onclose?.({ code: 1006 })
    await nextTick()
    expect(wrapper.text()).toBe('offline')
    vi.advanceTimersByTime(2000)
    expect(FakeSocket.instances).toHaveLength(2)
    FakeSocket.instances[1]?.open()
    await flushPromises()
    expect(wrapper.text()).toBe('connected')
    expect(vi.mocked(fetchMonitoringSummary).mock.calls.length).toBeGreaterThan(beforeReconnect)
    wrapper.unmount()
  })

  it('envelhece a leitura sem eventos e dá prioridade a stale após 30 segundos', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-09T18:00:00Z'))
    vi.mocked(fetchMonitoringSummary).mockResolvedValue({
      ...summary, freshness: { is_stale: false, age_seconds: 29 },
    })
    const Host = defineComponent({
      setup() { return useMonitoringSummary(ref('token'), ref('esp32-lab-01')) },
      template: '<p>{{ monitoringState.kind }}:{{ Math.floor(ageSeconds ?? -1) }}</p>',
    })
    const wrapper = mount(Host)
    await flushPromises()
    expect(wrapper.text()).toBe('normal:29')

    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(wrapper.text()).toBe('normal:30')

    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(wrapper.text()).toBe('stale:31')
    wrapper.unmount()
  })

  it('conta também o tempo gasto esperando a resposta REST', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-09T18:00:00Z'))
    let release: ((value: MonitoringSummary) => void) | undefined
    vi.mocked(fetchMonitoringSummary).mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))
    const Host = defineComponent({
      setup() { return useMonitoringSummary(ref('token'), ref('esp32-lab-01')) },
      template: '<p>{{ monitoringState.kind }}</p>',
    })
    const wrapper = mount(Host)
    vi.advanceTimersByTime(2000)
    release?.({ ...summary, freshness: { is_stale: false, age_seconds: 29 } })
    await flushPromises()
    expect(wrapper.text()).toBe('stale')
    wrapper.unmount()
  })

  it('não cria idade para ausência de leitura nem zera a idade ao reconectar', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-09T18:00:00Z'))
    vi.mocked(fetchMonitoringSummary)
      .mockResolvedValueOnce({ ...summary, reading: null, status: 'no_data', freshness: null })
      .mockResolvedValueOnce({ ...summary, freshness: { is_stale: false, age_seconds: 29 } })
      .mockResolvedValueOnce({ ...summary, status: 'stale', freshness: { is_stale: true, age_seconds: 35 } })
    const Host = defineComponent({
      setup() { return useMonitoringSummary(ref('token'), ref('esp32-lab-01')) },
      template: '<p>{{ monitoringState.kind }}:{{ ageSeconds ?? "sem idade" }}</p>',
    })
    const wrapper = mount(Host)
    await flushPromises()
    expect(wrapper.text()).toBe('no_data:sem idade')

    FakeSocket.instances[0]?.open()
    await flushPromises()
    expect(wrapper.text()).toBe('normal:29')
    FakeSocket.instances[0]?.onclose?.({ code: 1006 })
    vi.advanceTimersByTime(2000)
    await nextTick()
    expect(wrapper.text()).toBe('stale:31')

    FakeSocket.instances[1]?.open()
    await flushPromises()
    expect(wrapper.text()).toBe('stale:35')
    wrapper.unmount()
  })
})
