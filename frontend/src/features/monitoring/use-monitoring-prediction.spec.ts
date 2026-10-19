// @vitest-environment happy-dom
import examples from '../../../../contracts/examples/aiot.valid.json'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { parseAiotSnapshot } from './aiot-api'
import { fetchMonitoringSummary } from './monitoring-summary'
import { useMonitoringSummary } from './use-monitoring-summary'

vi.mock('./monitoring-version', () => ({ aiotEnabled: true }))
vi.mock('./monitoring-summary', () => ({ fetchMonitoringSummary: vi.fn() }))
const example = (name: string) => structuredClone(examples.find((item) => item.name === name)!.payload) as Record<string, unknown>
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); vi.clearAllMocks() })

it('troca versão via WS e REST sem recarga e ignora previsão atrasada sem renovar a entrada', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-12T18:00:04.100Z'))
  const sockets: Array<{ onopen?: () => void; onmessage?: (message: { data: string }) => void }> = []
  class Socket {
    onopen?: () => void
    onmessage?: (message: { data: string }) => void
    constructor() { sockets.push(this) }
    send = vi.fn()
    close() {}
  }
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ success: true, data: { ticket: 'one-use', expires_at: '2099-01-01T00:00:00Z' } }) }))
  const initial = parseAiotSnapshot({
    environment: { id: '00000000-0000-4000-8000-000000000002', name: 'Laboratório' }, device: { id: 'esp32.lab-01' },
    thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 }, telemetry: example('telemetry_received'), prediction: example('prediction_available_zero_rul'),
    prediction_unavailable_reason: null, persistence: 'persisted',
    freshness: { last_event_id: '00000000-0000-4000-8000-000000000100', last_received_at: '2026-10-12T18:00:00.100Z', state: 'fresh', age_seconds: 4, stale_after_seconds: 30 },
    commands: { led: null, buzzer: null }, alerts: [],
  })!
  vi.mocked(fetchMonitoringSummary).mockResolvedValue(initial)
  const callback = vi.fn()
  const wrapper = mount(defineComponent({
    setup: () => useMonitoringSummary(ref('private-token'), ref('esp32.lab-01'), callback),
    template: '<p>{{ summary?.prediction?.data.model_version }}</p><time>{{ summary?.reading?.received_at }}</time><span>{{ ageSeconds }}</span>',
  }))
  await flushPromises()
  sockets[0]?.onopen?.()
  await flushPromises()
  expect(wrapper.get('p').text()).toBe('fan-model-1')
  const prediction = example('prediction_available_zero_rul')
  ;(prediction.data as Record<string, unknown>).model_version = 'fan-model-2'
  prediction.event_id = '00000000-0000-4000-8000-000000000900'
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial, prediction: { ...initial.prediction!, data: { ...initial.prediction!.data, model_version: 'fan-model-2' } } })
  sockets[0]?.onmessage?.({ data: JSON.stringify(prediction) })
  await flushPromises()
  expect(wrapper.get('p').text()).toBe('fan-model-2')
  expect(wrapper.get('time').text()).toBe('2026-10-12T18:00:00.100Z')
  expect(wrapper.get('span').text()).toBe('4')
  expect(callback).toHaveBeenCalledOnce()
  const requests = vi.mocked(fetchMonitoringSummary).mock.calls.length
  sockets[0]?.onmessage?.({ data: JSON.stringify(prediction) })
  sockets[0]?.onmessage?.({ data: JSON.stringify({ ...prediction, event_id: '00000000-0000-4000-8000-000000000901', device_record_id: '00000000-0000-4000-8000-000000000999' }) })
  const oldPrediction = { ...prediction, event_id: '00000000-0000-4000-8000-000000000902', correlation_id: '00000000-0000-4000-8000-000000000999', data: { ...(prediction.data as object), source_event_id: '00000000-0000-4000-8000-000000000999' } }
  sockets[0]?.onmessage?.({ data: JSON.stringify(oldPrediction) })
  await flushPromises()
  expect(vi.mocked(fetchMonitoringSummary).mock.calls.length).toBe(requests)
  expect(callback).toHaveBeenCalledOnce()
  // Prediction may beat the REST response invalidated by its newer telemetry event.
  const nextSource = '00000000-0000-4000-8000-000000000998'
  const nextInput = '2026-10-12T18:00:01.100Z'
  const nextPrediction = { ...prediction, event_id: '00000000-0000-4000-8000-000000000903', correlation_id: nextSource,
    occurred_at: '2026-10-12T18:00:01.200Z', received_at: '2026-10-12T18:00:01.200Z',
    data: { ...(prediction.data as object), source_event_id: nextSource, input_received_at: nextInput, model_version: 'fan-model-3' },
  }
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
    reading: { ...initial.reading!, event_id: nextSource, received_at: nextInput },
    prediction: { ...initial.prediction!, ...nextPrediction, data: { ...initial.prediction!.data, source_event_id: nextSource, input_received_at: nextInput, model_version: 'fan-model-3' } },
    freshness: { is_stale: false, age_seconds: 3 },
  })
  sockets[0]?.onmessage?.({ data: JSON.stringify(nextPrediction) })
  await flushPromises()
  expect(wrapper.get('p').text()).toBe('fan-model-3')
  expect(wrapper.get('time').text()).toBe(nextInput)
  expect(vi.mocked(fetchMonitoringSummary).mock.calls.length).toBe(requests + 1)
  await vi.advanceTimersByTimeAsync(31_000)
  expect(wrapper.get('span').text()).toBe('34')
  wrapper.unmount()
})
