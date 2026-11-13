// @vitest-environment happy-dom
import examples from '../../../../contracts/examples/aiot.valid.json'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { parseAiotSnapshot } from './aiot-api'
import { fetchMonitoringSummary } from './monitoring-summary'
import { useMonitoringSummary, type MonitoringEvent } from './use-monitoring-summary'

enableAutoUnmount(afterEach)

vi.mock('./monitoring-version', () => ({ aiotEnabled: true }))
vi.mock('./monitoring-summary', () => ({ fetchMonitoringSummary: vi.fn() }))
const example = (name: string) => structuredClone(examples.find((item) => item.name === name)!.payload) as Record<string, unknown>
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); vi.clearAllMocks() })

function snapshot() {
  return parseAiotSnapshot({
    environment: { id: '00000000-0000-4000-8000-000000000002', name: 'Laboratório' }, device: { id: 'esp32.lab-01' },
    thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 }, telemetry: example('telemetry_received'), prediction: example('prediction_available_zero_rul'),
    prediction_unavailable_reason: null, persistence: 'persisted',
    freshness: { last_event_id: '00000000-0000-4000-8000-000000000100', last_received_at: '2026-10-12T18:00:00.100Z', state: 'fresh', age_seconds: 4, stale_after_seconds: 30 },
    commands: { led: null, buzzer: null }, alerts: [],
  })!
}

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
  const initial = snapshot()
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
  expect(callback).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(31_000)
  expect(wrapper.get('span').text()).toBe('34')
  wrapper.unmount()
})


async function setupLive() {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-12T18:00:04.100Z'))
  const sockets: Array<{ onmessage?: (message: { data: string }) => void }> = []
  class Socket {
    onmessage?: (message: { data: string }) => void
    constructor() { sockets.push(this) }
    close() {}
  }
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200,
    json: async () => ({ success: true, data: { ticket: 'one-use', expires_at: '2099-01-01T00:00:00Z' } }),
  }))
  const initial = { ...snapshot(), prediction: null }
  vi.mocked(fetchMonitoringSummary).mockResolvedValue(initial)
  const token = ref<string | null>('private-token')
  const device = ref<string | null>('esp32.lab-01')
  const callback = vi.fn<(event: MonitoringEvent) => void>()
  let live!: ReturnType<typeof useMonitoringSummary>
  const wrapper = mount(defineComponent({
    setup() { live = useMonitoringSummary(token, device, callback); return () => null },
  }))
  await flushPromises()
  const send = async (event: unknown, socket = sockets[0]) => {
    socket?.onmessage?.({ data: JSON.stringify(event) })
    await flushPromises()
  }
  return { wrapper, initial, token, device, live, callback, sockets, send }
}

it('entrega previsão de N conhecida após a leitura N+1 sem mudar a leitura para sua fonte antiga', async () => {
  const { wrapper, initial, live, callback, send } = await setupLive()
  const next = example('telemetry_received')
  next.event_id = next.correlation_id = '00000000-0000-4000-8000-000000000998'
  next.received_at = '2026-10-12T18:00:01.100Z'
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
    reading: { ...initial.reading!, event_id: String(next.event_id), received_at: String(next.received_at) },
    freshness: { is_stale: false, age_seconds: 3 },
  })
  await send(next)
  callback.mockClear()
  await vi.advanceTimersByTimeAsync(2_000)
  const prediction = example('prediction_available_zero_rul')
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
    reading: { ...initial.reading!, event_id: String(next.event_id), received_at: String(next.received_at) },
    freshness: { is_stale: false, age_seconds: 5 },
  })
  await send(prediction)
  expect(callback).toHaveBeenCalledOnce()
  expect(callback.mock.calls[0]![0]).toMatchObject({ type: 'prediction', data: { source_event_id: initial.reading!.event_id } })
  expect(live.summary.value?.reading?.event_id).toBe(next.event_id)
  expect(live.summary.value?.prediction).toBeNull()
  expect(live.ageSeconds.value).toBe(5)
  await vi.advanceTimersByTimeAsync(1_000)
  expect(live.ageSeconds.value).toBe(6)
  await send(prediction)
  expect(callback).toHaveBeenCalledOnce()
  wrapper.unmount()
})

it('lembra telemetria validada mesmo quando o REST já saltou para uma leitura posterior', async () => {
  const { wrapper, initial, callback, send } = await setupLive()
  const middle = example('telemetry_received')
  middle.event_id = middle.correlation_id = '00000000-0000-4000-8000-000000000996'
  middle.received_at = '2026-10-12T18:00:01.100Z'
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
    reading: { ...initial.reading!, event_id: '00000000-0000-4000-8000-000000000998', received_at: '2026-10-12T18:00:02.100Z' },
  })
  await send(middle)
  callback.mockClear()
  const prediction = example('prediction_available_zero_rul')
  prediction.correlation_id = middle.event_id
  prediction.occurred_at = prediction.received_at = '2026-10-12T18:00:01.200Z'
  prediction.data = { ...(prediction.data as object), source_event_id: middle.event_id, input_received_at: middle.received_at }
  await send(prediction)
  expect(callback).toHaveBeenCalledOnce()
  expect(callback.mock.calls[0]![0]).toMatchObject({ type: 'prediction', data: { source_event_id: middle.event_id } })
  wrapper.unmount()
})

it.each(['timestamp', 'device_record', 'equipment', 'unknown_source'])('rejeita previsão antiga com fonte ou vínculo inválido: %s', async (mismatch) => {
  const { wrapper, initial, callback, live, send } = await setupLive()
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
    reading: { ...initial.reading!, event_id: '00000000-0000-4000-8000-000000000998', received_at: '2026-10-12T18:00:02.100Z' },
  })
  await live.loadSummary()
  const prediction = example('prediction_available_zero_rul')
  const wrong = '00000000-0000-4000-8000-000000000999'
  if (mismatch === 'device_record') prediction.device_record_id = wrong
  else if (mismatch === 'equipment') prediction.data = { ...(prediction.data as object), equipment_id: wrong }
  else if (mismatch === 'unknown_source') {
    prediction.correlation_id = wrong
    prediction.data = { ...(prediction.data as object), source_event_id: wrong }
  } else prediction.data = { ...(prediction.data as object), input_received_at: '2026-10-12T18:00:00.050Z' }
  await send(prediction)
  expect(callback).not.toHaveBeenCalled()
  wrapper.unmount()
})

it.each(['token', 'device'])('limpa fontes conhecidas ao trocar %s e bloqueia callbacks antigos', async (scope) => {
  const { wrapper, initial, token, device, callback, live, sockets, send } = await setupLive()
  const oldHandler = sockets[0]!.onmessage!
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
    device: { id: scope === 'device' ? 'esp32.lab-02' : initial.device.id },
    reading: { ...initial.reading!, event_id: '00000000-0000-4000-8000-000000000998', received_at: '2026-10-12T18:00:02.100Z' },
  })
  if (scope === 'token') token.value = 'new-token'
  else device.value = 'esp32.lab-02'
  const prediction = example('prediction_available_zero_rul')
  oldHandler({ data: JSON.stringify(prediction) })
  await flushPromises()
  prediction.device_id = device.value
  await send(prediction, sockets[1])
  expect(callback).not.toHaveBeenCalled()
  expect(live.summary.value?.prediction).toBeNull()
  wrapper.unmount()
})


it.each(['device_record_id', 'equipment_id', 'environment_id'])('não reutiliza fonte conhecida depois de mudar %s da seleção atual', async (field) => {
  const { wrapper, initial, live, callback, send } = await setupLive()
  const other = '00000000-0000-4000-8000-000000000999'
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
    environment: field === 'environment_id' ? { ...initial.environment, id: other } : initial.environment,
    reading: { ...initial.reading!, [field]: other,
      event_id: '00000000-0000-4000-8000-000000000998', received_at: '2026-10-12T18:00:02.100Z' },
  })
  await live.loadSummary()
  await send(example('prediction_available_zero_rul'))
  expect(callback).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('limita a memória de fontes a 256 e rejeita a previsão da fonte já removida', async () => {
  const { wrapper, initial, callback, send } = await setupLive()
  for (let index = 1; index <= 256; index++) {
    const telemetry = example('telemetry_received')
    const id = `00000000-0000-4000-8000-${String(1_000 + index).padStart(12, '0')}`
    const receivedAt = new Date(Date.parse(initial.reading!.received_at) + index * 1_000).toISOString()
    telemetry.event_id = telemetry.correlation_id = id
    telemetry.received_at = receivedAt
    vi.mocked(fetchMonitoringSummary).mockResolvedValue({ ...initial,
      reading: { ...initial.reading!, event_id: id, received_at: receivedAt },
    })
    await send(telemetry)
  }
  callback.mockClear()
  const requests = vi.mocked(fetchMonitoringSummary).mock.calls.length
  await send(example('prediction_available_zero_rul'))
  expect(callback).not.toHaveBeenCalled()
  expect(vi.mocked(fetchMonitoringSummary).mock.calls.length).toBe(requests)
  wrapper.unmount()
})
