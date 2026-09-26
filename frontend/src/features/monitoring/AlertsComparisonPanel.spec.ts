// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AlertsComparisonPanel from './AlertsComparisonPanel.vue'

vi.mock('vue-chartjs', async () => {
  const { defineComponent } = await import('vue')
  return { Line: defineComponent({ name: 'Line', props: ['data', 'options'], template: '<div />' }) }
})

const end = Date.parse('2026-09-24T12:00:00Z')
const reading = {
  temperature_c: 5, humidity_percent: 60,
  received_at: '2026-09-24T11:30:00Z', status: 'normal',
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function installFetch(empty = false) {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input))
    const start = url.searchParams.get('start')!
    const isPrevious = start === '2026-09-24T10:00:00.000Z'
    const readings = empty ? [] : [{ ...reading,
      received_at: isPrevious ? '2026-09-24T10:30:00Z' : reading.received_at,
      temperature_c: isPrevious ? 4 : 5,
    }]
    const body = url.pathname.endsWith('/alerts')
      ? { success: true, data: { alerts: empty ? [] : [{
          alert_id: 'alert-1', device_id: 'esp32-1', kind: 'temperature_high',
          opened_at: '2026-09-24T11:20:00Z', closed_at: null, status: 'open',
        }] }, meta: { device_id: 'esp32-1', count: empty ? 0 : 1 } }
      : { success: true, data: { readings }, meta: {
          device_id: 'esp32-1', start, end: url.searchParams.get('end'),
          count: readings.length, limit: 300,
        } }
    return new Response(JSON.stringify(body))
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

describe('AlertsComparisonPanel', () => {
  it('filtra alertas e alinha duas janelas contíguas de mesma duração', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(end)
    const fetcher = installFetch()
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h' },
    })
    await flushPromises()

    const urls = fetcher.mock.calls.map(([input]) => new URL(String(input)))
    expect(urls).toHaveLength(3)
    expect(urls.map((url) => [url.searchParams.get('start'), url.searchParams.get('end')])).toEqual([
      ['2026-09-24T11:00:00.000Z', '2026-09-24T12:00:00.000Z'],
      ['2026-09-24T11:00:00.000Z', '2026-09-24T12:00:00.000Z'],
      ['2026-09-24T10:00:00.000Z', '2026-09-24T11:00:00.000Z'],
    ])
    expect(wrapper.text()).toContain('Temperatura acima do limite')
    expect(wrapper.text()).toContain('média de 5 °C')
    expect(wrapper.text()).toContain('média de 4 °C')
    expect(wrapper.getComponent({ name: 'Line' }).props('data').datasets.map(
      (dataset: { data: unknown }) => dataset.data,
    )).toEqual([[{ x: 30, y: 5 }], [{ x: 30, y: 4 }]])
    await wrapper.setProps({ period: '15m' })
    await flushPromises()
    const shorterWindow = new URL(String(fetcher.mock.calls[3]![0]))
    expect(shorterWindow.searchParams.get('start')).toBe('2026-09-24T11:45:00.000Z')
    expect(shorterWindow.searchParams.get('end')).toBe('2026-09-24T12:00:00.000Z')
    wrapper.unmount()
  })

  it('mostra estados vazios sem renderizar gráfico', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(end)
    installFetch(true)
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Nenhum alerta neste período')
    expect(wrapper.text()).toContain('Não há leituras em nenhum dos dois períodos')
    expect(wrapper.find('[role="img"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('preserva a comparação se a consulta de alertas falhar e recarrega ao mudar a revisão', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(end)
    const successfulFetch = installFetch()
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
      String(input).includes('/alerts?')
        ? Promise.resolve(new Response('{}', { status: 503 }))
        : successfulFetch(input),
    )
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h', revision: 0 },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Não foi possível carregar os alertas')
    expect(wrapper.findComponent({ name: 'Line' }).exists()).toBe(true)
    await wrapper.setProps({ revision: 1 })
    await flushPromises()
    expect(fetcher).toHaveBeenCalledTimes(6)
    wrapper.unmount()
  })
})
