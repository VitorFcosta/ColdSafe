// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchMonitoringSummary, type MonitoringSummary } from './monitoring-summary'
import { useMonitoringSummary } from './use-monitoring-summary'

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
})
