// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { fetchMonitoringSummary } from './monitoring-summary'
import { useMonitoringSummary } from './use-monitoring-summary'

vi.mock('./monitoring-version', () => ({ aiotEnabled: true }))
vi.mock('./aiot-api', () => ({
  parseAiotEvent: (value: Record<string, unknown>, device: string, environment?: string) =>
    value.schema_version === 3 && value.device_id === device && (!environment || value.environment_id === environment) ? value : null,
}))
vi.mock('./monitoring-summary', () => ({ fetchMonitoringSummary: vi.fn() }))

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it('conecta no stream v3, deduplica reentregas e recupera REST sem aplicar comando antigo', async () => {
  const sockets: Array<{ url: URL; onopen?: () => void; onmessage?: (message: { data: string }) => void; onclose?: (event: { code: number }) => void; send: (data: string) => void }> = []
  class Socket {
    constructor(readonly url: URL) { sockets.push(this) }
    send = vi.fn()
    close() {}
  }
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200,
    json: async () => ({ success: true, data: { ticket: 'one-use', expires_at: '2099-01-01T00:00:00Z' } }),
  }))
  vi.mocked(fetchMonitoringSummary).mockResolvedValue({
    environment: { id: 'env', name: 'Câmara' }, device: { id: 'sim-1' },
    reading: null, status: 'no_data', freshness: null,
    thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
  })
  const callback = vi.fn()
  const wrapper = mount(defineComponent({
    setup: () => useMonitoringSummary(ref('private-jwt'), ref('sim-1'), callback),
    template: '<p>{{ connectionState }}</p>',
  }))
  await flushPromises()
  expect(sockets[0]?.url.pathname).toBe('/api/v3/events')
  expect(String(sockets[0]?.url)).not.toContain('private-jwt')
  sockets[0]?.onopen?.()
  await flushPromises()
  const event = { schema_version: 3, event_id: 'event-1', type: 'command_status',
    device_id: 'sim-1', environment_id: 'env', occurred_at: '2026-10-15T00:00:00Z', data: {} }
  const before = vi.mocked(fetchMonitoringSummary).mock.calls.length
  sockets[0]?.onmessage?.({ data: JSON.stringify(event) })
  sockets[0]?.onmessage?.({ data: JSON.stringify(event) })
  sockets[0]?.onmessage?.({ data: JSON.stringify({ ...event, event_id: 'other', environment_id: 'foreign' }) })
  await flushPromises()
  expect(callback).toHaveBeenCalledOnce()
  expect(vi.mocked(fetchMonitoringSummary).mock.calls.length).toBe(before + 1)
  wrapper.unmount()
})
