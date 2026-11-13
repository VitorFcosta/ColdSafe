// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'

vi.stubEnv('VITE_API_BASE_URL', '')
vi.mock('./monitoring-summary', () => ({
  fetchMonitoringSummary: vi.fn().mockResolvedValue({
    device: { id: 'proxy-device' }, status: 'normal', freshness: { age_seconds: 0 },
  }),
}))
const { useMonitoringSummary } = await import('./use-monitoring-summary')

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs() })

it('usa a mesma origem no WebSocket com base REST relativa e ticket no frame', async () => {
  const created: Array<{ url: URL; onopen?: () => void; sent: string[] }> = []
  class Socket {
    sent: string[] = []
    constructor(readonly url: URL) { created.push(this) }
    send(value: string) { this.sent.push(value) }
    close() {}
  }
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200,
    json: async () => ({ success: true, data: { ticket: 'single-use-ticket', expires_at: '2099-01-01T00:00:00Z' } }),
  }))
  const wrapper = mount(defineComponent({
    setup() { return useMonitoringSummary(ref('private-jwt'), ref('proxy-device')) },
    template: '<p>{{ connectionState }}</p>',
  }))
  await flushPromises()
  expect(fetch).toHaveBeenCalledWith('/api/v1/auth/ws-ticket', expect.any(Object))
  expect(created).toHaveLength(1)
  expect(created[0]!.url.host).toBe(window.location.host)
  expect(created[0]!.url.pathname).toBe('/api/v1/events')
  expect(created[0]!.url.searchParams.get('device_id')).toBe('proxy-device')
  expect(String(created[0]!.url)).not.toContain('private-jwt')
  created[0]!.onopen?.()
  expect(created[0]!.sent).toEqual(['{"ticket":"single-use-ticket"}'])
  wrapper.unmount()
})
