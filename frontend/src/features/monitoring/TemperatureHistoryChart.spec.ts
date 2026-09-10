// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
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

describe('TemperatureHistoryChart', () => {
  it('oferece resumo textual junto do gráfico correspondente', () => {
    const wrapper = mount(TemperatureHistoryChart, {
      props: { period: '1h', readings },
    })

    expect(wrapper.text()).toContain('mínima de 5,2 °C e máxima de 5,6 °C')
    expect(wrapper.find('[role="img"]').attributes('aria-describedby')).toBe(
      'temperature-history-summary',
    )

    const chart = wrapper.getComponent({ name: 'Line' })
    expect(chart.props('data')).toMatchObject({
      labels: ['18:00', '18:05'],
      datasets: [{ data: [5.2, 5.6], label: 'Temperatura (°C)' }],
    })

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

  it('não renderiza um gráfico vazio e explica a ausência de leituras', () => {
    const wrapper = mount(TemperatureHistoryChart, {
      props: { period: '24h', readings: [] },
    })

    expect(wrapper.text()).toContain('Não há leituras de temperatura nas últimas 24 horas')
    expect(wrapper.find('[role="img"]').exists()).toBe(false)
  })
})
