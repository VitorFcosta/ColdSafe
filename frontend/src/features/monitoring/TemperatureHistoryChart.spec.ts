// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import TemperatureHistoryChart from './TemperatureHistoryChart.vue'

vi.mock('vue-chartjs', async () => {
  const { defineComponent } = await import('vue')

  return {
    Line: defineComponent({
      name: 'Line',
      props: ['data', 'options'],
      template: '<div data-test="line" />',
    }),
  }
})

const readings = [
  {
    temperature_c: 5.2,
    humidity_percent: 62.4,
    received_at: '2026-09-09T18:00:00Z',
    status: 'normal' as const,
  },
  {
    temperature_c: 5.6,
    humidity_percent: 61.9,
    received_at: '2026-09-09T18:05:00Z',
    status: 'attention' as const,
  },
] as const

const chartProps = {
  period: '1h' as const, readings,
  start: '2026-09-09T17:00:00Z', end: '2026-09-09T18:10:00Z', limit: 300,
  thresholds: { min_c: 2, max_c: 8 },
}

describe('TemperatureHistoryChart', () => {
  it('oferece resumo textual junto do gráfico correspondente', () => {
    const wrapper = mount(TemperatureHistoryChart, {
      props: chartProps,
    })

    expect(wrapper.text()).toContain('mínima de 5,2 °C e máxima de 5,6 °C')
    expect(wrapper.find('[role="img"]').attributes('aria-describedby')).toBe(
      'temperature-history-summary temperature-history-note temperature-history-coverage',
    )

    const chart = wrapper.getComponent({ name: 'Line' })
    expect(chart.props('data')).toMatchObject({
      datasets: [
        { label: 'Temperatura (°C)', data: [
          { x: Date.parse('2026-09-09T18:00:00Z'), y: 5.2 },
          { x: Date.parse('2026-09-09T18:02:30Z'), y: null },
          { x: Date.parse('2026-09-09T18:05:00Z'), y: 5.6 },
        ] },
        { label: 'Mínimo atual: 2 °C' },
        { label: 'Máximo atual: 8 °C' },
      ],
    })
    expect(wrapper.text()).toContain('1 lacuna de mais de 30 s sem leitura')
    expect(wrapper.text()).toContain('O histórico não informa quais limites valiam em cada leitura')
    const table = wrapper.get('table')
    expect(table.get('caption').text()).toContain('Leituras individuais')
    expect(table.findAll('tbody tr')).toHaveLength(2)
    expect(table.findAll('tbody tr')[0]?.get('time').attributes('datetime')).toBe(readings[0].received_at)
    expect(table.findAll('tbody tr')[1]?.findAll('td')[1]?.text()).toBe('5,6 °C')
    expect(table.findAll('thead th').map((header) => header.attributes('scope'))).toEqual(['col', 'col'])
    expect(wrapper.get('details summary').text()).toContain('Ver 2 leituras')

    const options = chart.props('options') as {
      plugins: {
        tooltip: {
          callbacks: {
            label: (context: { parsed: { y: number | null } }) => string
          }
        }
      }
    }
    const formatTooltip = options.plugins.tooltip.callbacks.label

    expect(formatTooltip({ parsed: { y: 5.2 } })).toBe('Temperatura: 5,2 °C')
    expect(formatTooltip({ parsed: { y: null } })).toBe('Temperatura indisponível')
  })

  it('usa os tokens herdados pelo gráfico e mantém animações desativadas', async () => {
    const computedStyle = vi.spyOn(window, 'getComputedStyle').mockReturnValue({
      getPropertyValue: (name: string) => ({
        '--cs-color-accent': 'rgb(12, 109, 101)',
        '--cs-color-ink-muted': 'rgb(82, 108, 112)',
        '--cs-color-line': 'rgb(203, 216, 214)',
        '--cs-color-status-attention': 'rgb(139, 76, 12)',
      } as Record<string, string>)[name] ?? '',
    } as CSSStyleDeclaration)
    const wrapper = mount(TemperatureHistoryChart, { props: chartProps })
    await flushPromises()
    const chart = wrapper.getComponent({ name: 'Line' })
    expect(computedStyle).toHaveBeenCalledWith(wrapper.element)
    expect(chart.props('data').datasets[0].borderColor).toBe('rgb(12, 109, 101)')
    expect(chart.props('options')).toMatchObject({
      animation: false,
      scales: { x: { ticks: { color: 'rgb(82, 108, 112)' } }, y: { grid: { color: 'rgb(203, 216, 214)' } } },
    })
    wrapper.unmount()
    computedStyle.mockRestore()
  })

  it('não renderiza um gráfico vazio e explica a ausência de leituras', () => {
    const wrapper = mount(TemperatureHistoryChart, {
      props: { ...chartProps, period: '24h', readings: [] },
    })

    expect(wrapper.text()).toContain('Não há leituras de temperatura nas últimas 24 horas')
    expect(wrapper.find('[role="img"]').exists()).toBe(false)
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('atualiza os limites ao trocar ambiente e os remove quando indisponíveis', async () => {
    const wrapper = mount(TemperatureHistoryChart, { props: chartProps })
    await wrapper.setProps({ thresholds: { min_c: -2, max_c: 4 } })
    expect(wrapper.text()).toContain('limites atuais do ambiente, -2–4 °C')
    expect(wrapper.getComponent({ name: 'Line' }).props('data').datasets[1].data[0].y).toBe(-2)
    await wrapper.setProps({ thresholds: null })
    expect(wrapper.getComponent({ name: 'Line' }).props('data').datasets).toHaveLength(1)
    expect(wrapper.text()).toContain('Limites atuais indisponíveis')
  })

  it('troca a grandeza no mesmo gráfico, tabela e recursos acessíveis sem aplicar limites ambientais', async () => {
    const wrapper = mount(TemperatureHistoryChart, {
      props: { ...chartProps, readings: [
        { ...readings[0], vibration_rms_mm_s: 1.25, motor_current_a: 0.123 },
        { ...readings[1], vibration_rms_mm_s: null, motor_current_a: 0 },
      ] },
    })
    await wrapper.setProps({ metric: 'vibration_rms_mm_s' })
    const chart = wrapper.getComponent({ name: 'Line' })
    expect(chart.props('data').datasets).toHaveLength(1)
    expect(chart.props('data').datasets[0].label).toBe('Vibração RMS (mm/s)')
    expect(chart.props('options').scales.y.title.text).toBe('Vibração RMS (mm/s)')
    expect(wrapper.get('[role="img"]').attributes('aria-label')).toContain('vibração RMS')
    expect(wrapper.get('[role="region"]').attributes('aria-label')).toContain('vibração RMS')
    expect(wrapper.get('thead').text()).toContain('Vibração RMS')
    expect(wrapper.findAll('tbody tr')[0]?.findAll('td')[1]?.text()).toBe('1,25 mm/s')
    expect(wrapper.findAll('tbody tr')[1]?.findAll('td')[1]?.text()).toBe('Indisponível')
    expect(wrapper.text()).not.toContain('Linhas tracejadas')
    expect(chart.props('options').plugins.tooltip.callbacks.label({ parsed: { y: 1.25 } })).toBe('Vibração RMS: 1,25 mm/s')
    await wrapper.setProps({ metric: 'motor_current_a' })
    expect(wrapper.findAll('tbody tr')[0]?.findAll('td')[1]?.text()).toBe('0,123 A')
    expect(wrapper.findAll('tbody tr')[1]?.findAll('td')[1]?.text()).toBe('0 A')
    await wrapper.setProps({ metric: 'temperature_c' })
    expect(chart.props('data').datasets).toHaveLength(3)
  })

  it('explica o histórico legado sem desenhar uma linha artificial em zero', () => {
    const wrapper = mount(TemperatureHistoryChart, { props: { ...chartProps, metric: 'motor_temperature_c' } })
    expect(wrapper.text()).toContain('Temperatura do motor indisponível')
    expect(wrapper.text()).toContain('histórico legado')
    expect(wrapper.getComponent({ name: 'Line' }).props('data').datasets[0].data.every((point: { y: number | null }) => point.y === null)).toBe(true)
    expect(wrapper.findAll('tbody tr').every((row) => row.findAll('td')[1]?.text() === 'Indisponível')).toBe(true)
  })
})
