// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AlertsComparisonPanel from './AlertsComparisonPanel.vue'
import { monitoringPollingIntervalMs } from './monitoring-polling'

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
  vi.useRealTimers()
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
  it('interrompe lacunas sem suavizar e oferece os valores de ambos os períodos em tabela', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(end)
    const original = installFetch()
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      const response = await original(input)
      if (String(input).includes('/alerts?')) return response
      const body = await response.json()
      const first = body.data.readings[0]
      body.data.readings = [{ ...first, received_at: new Date(Date.parse(first.received_at) + 60_000).toISOString(), temperature_c: 0 }, first]
      body.meta.count = 2
      return new Response(JSON.stringify(body))
    })
    const wrapper = mount(AlertsComparisonPanel, { props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h' } })
    await flushPromises()
    const datasets = wrapper.getComponent({ name: 'Line' }).props('data').datasets
    expect(datasets[0]).toMatchObject({ tension: 0, spanGaps: false, data: [{ x: 30, y: 5 }, { x: 30.5, y: null }, { x: 31, y: 0 }] })
    expect(datasets[1]).toMatchObject({ tension: 0, spanGaps: false, borderDash: [6, 4] })
    expect(wrapper.text()).toContain('1 lacuna')
    expect(wrapper.findAll('table')).toHaveLength(2)
    expect(wrapper.findAll('tbody tr')).toHaveLength(4)
    expect(wrapper.findAll('tbody tr').filter((row) => row.text().includes('0 °C'))).toHaveLength(2)
    wrapper.unmount()
  })
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
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    vi.setSystemTime(end)
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
    await vi.advanceTimersByTimeAsync(monitoringPollingIntervalMs)
    await flushPromises()
    expect(fetcher).toHaveBeenCalledTimes(6)
    wrapper.unmount()
  })

  it('distingue 55 leituras de uma consulta que chegou ao limite de 300', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(end)
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname.endsWith('/alerts')) {
        return new Response(JSON.stringify({ success: true, data: { alerts: [] }, meta: { device_id: 'esp32-1', count: 0 } }))
      }
      const start = url.searchParams.get('start')!
      const count = start === '2026-09-24T10:00:00.000Z' ? 300 : 55
      const readings = Array.from({ length: count }, (_, index) => ({
        ...reading, received_at: new Date(Date.parse(start) + index * 5_000).toISOString(),
      }))
      return new Response(JSON.stringify({ success: true, data: { readings }, meta: {
        device_id: 'esp32-1', start, end: url.searchParams.get('end'), count, limit: 300,
      } }))
    }))
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('55 leituras retornadas')
    expect(wrapper.text()).toContain('300 leituras retornadas')
    expect(wrapper.text()).toContain('Limite de 300 atingido')
    expect(wrapper.text()).not.toContain('cobertura completa')
    wrapper.unmount()
  })

  it('permite repetir a comparação após uma falha sem esconder os alertas válidos', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(end)
    const successfulFetch = installFetch()
    let failPrevious = true
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (failPrevious && url.searchParams.get('start') === '2026-09-24T10:00:00.000Z') {
        return Promise.resolve(new Response('{}', { status: 503 }))
      }
      return successfulFetch(input)
    }))
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Temperatura acima do limite')
    expect(wrapper.text()).toContain('Não foi possível comparar as leituras')
    failPrevious = false
    await wrapper.get('article:nth-child(2) button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('média de 4 °C')
    wrapper.unmount()
  })

  it('agrupa revisões, mantém o gráfico durante consulta lenta e não sobrepõe pedidos', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    vi.setSystemTime(end)
    const successfulFetch = installFetch()
    const waiting: (() => void)[] = []
    const fetcher = vi.fn((input: RequestInfo | URL): Promise<Response> => fetcher.mock.calls.length <= 3
      ? successfulFetch(input)
      : new Promise<Response>((resolve) => waiting.push(() => { void successfulFetch(input).then(resolve) })))
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h', revision: 0 },
    })
    await flushPromises()
    const chart = wrapper.getComponent({ name: 'Line' }).vm
    const oldData = wrapper.getComponent({ name: 'Line' }).props('data')
    for (let revision = 1; revision <= 4; revision++) {
      await wrapper.setProps({ revision })
      await vi.advanceTimersByTimeAsync(1_000)
    }
    expect(fetcher).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(1_000)
    expect(fetcher).toHaveBeenCalledTimes(6)
    for (let revision = 5; revision <= 10; revision++) {
      await wrapper.setProps({ revision })
      await vi.advanceTimersByTimeAsync(1_000)
    }
    expect(fetcher).toHaveBeenCalledTimes(6)
    expect(wrapper.getComponent({ name: 'Line' }).vm).toBe(chart)
    expect(wrapper.getComponent({ name: 'Line' }).props('data')).toEqual(oldData)
    expect(wrapper.text()).toContain('Temperatura acima do limite')
    expect(wrapper.text()).not.toContain('Carregando')
    waiting.splice(0).forEach((resolve) => resolve())
    await flushPromises()
    await vi.advanceTimersByTimeAsync(0)
    expect(fetcher).toHaveBeenCalledTimes(9)
    expect(wrapper.getComponent({ name: 'Line' }).vm).toBe(chart)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(monitoringPollingIntervalMs * 2)
    expect(fetcher).toHaveBeenCalledTimes(9)
  })

  it('mantém dados ao falhar a atualização e permite tentar novamente imediatamente', async () => {
    const successfulFetch = installFetch()
    let failing = false
    const fetcher = vi.fn((input: RequestInfo | URL): Promise<Response> => failing
      ? Promise.resolve(new Response('{}', { status: 503 })) : successfulFetch(input))
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h' },
    })
    await flushPromises()
    const chart = wrapper.getComponent({ name: 'Line' }).vm
    const oldData = wrapper.getComponent({ name: 'Line' }).props('data')
    failing = true
    await wrapper.get('article button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Não foi possível atualizar os alertas')
    expect(wrapper.text()).toContain('Não foi possível atualizar a comparação')
    expect(wrapper.text()).toContain('Temperatura acima do limite')
    expect(wrapper.getComponent({ name: 'Line' }).vm).toBe(chart)
    expect(wrapper.getComponent({ name: 'Line' }).props('data')).toEqual(oldData)
    failing = false
    await wrapper.get('article:nth-child(2) button').trigger('click')
    await flushPromises()
    expect(fetcher).toHaveBeenCalledTimes(9)
    expect(wrapper.text()).not.toContain('Não foi possível atualizar')
    wrapper.unmount()
  })

  it.each([{ auth: 'other-session' }, { deviceId: 'esp32-2' }, { period: '15m' as const }])(
    'limpa os resultados e cancela a consulta ao trocar a seleção %o', async (selection) => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
      vi.setSystemTime(end)
      const successfulFetch = installFetch()
      const signals: AbortSignal[] = []
      const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        signals.push(init!.signal as AbortSignal)
        return fetcher.mock.calls.length <= 3 ? successfulFetch(input) : new Promise<Response>(() => {})
      })
      vi.stubGlobal('fetch', fetcher)
      const wrapper = mount(AlertsComparisonPanel, {
        props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h', revision: 0 },
      })
      await flushPromises()
      await wrapper.get('article button').trigger('click')
      await wrapper.setProps({ revision: 1 })
      await wrapper.setProps(selection)
      expect(signals[3]!.aborted).toBe(true)
      expect(wrapper.text()).not.toContain('Temperatura acima do limite')
      expect(wrapper.findComponent({ name: 'Line' }).exists()).toBe(false)
      expect(wrapper.text()).toContain('Carregando comparação')
      await vi.advanceTimersByTimeAsync(monitoringPollingIntervalMs * 2)
      expect(fetcher).toHaveBeenCalledTimes(9)
      wrapper.unmount()
      expect(signals[6]!.aborted).toBe(true)
    },
  )


  it('descarta respostas da conta anterior após sair e cancela atualização agendada ao desmontar', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    vi.setSystemTime(end)
    const successfulFetch = installFetch()
    const waiting: (() => void)[] = []
    const fetcher = vi.fn((input: RequestInfo | URL): Promise<Response> => fetcher.mock.calls.length <= 3
      ? successfulFetch(input)
      : new Promise<Response>((resolve) => waiting.push(() => { void successfulFetch(input).then(resolve) })))
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(AlertsComparisonPanel, {
      props: { auth: 'test-session', deviceId: 'esp32-1', period: '1h', revision: 0 },
    })
    await flushPromises()
    await wrapper.get('article button').trigger('click')
    await wrapper.setProps({ auth: null })
    waiting.forEach((resolve) => resolve())
    await flushPromises()
    expect(wrapper.text()).not.toContain('Temperatura acima do limite')
    expect(wrapper.findComponent({ name: 'Line' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('entre na conta')
    wrapper.unmount()

    vi.stubGlobal('fetch', successfulFetch)
    const next = mount(AlertsComparisonPanel, {
      props: { auth: 'new-session', deviceId: 'esp32-1', period: '1h', revision: 0 },
    })
    await flushPromises()
    await next.setProps({ revision: 1 })
    const calls = successfulFetch.mock.calls.length
    next.unmount()
    await vi.advanceTimersByTimeAsync(monitoringPollingIntervalMs * 2)
    expect(successfulFetch).toHaveBeenCalledTimes(calls)
  })

})
