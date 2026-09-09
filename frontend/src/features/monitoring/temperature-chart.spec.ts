import { describe, expect, it } from 'vitest'

import { buildTemperatureChart, describeTemperatureRange } from './temperature-chart'

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

describe('temperature chart', () => {
  it('transforma as leituras em uma série de temperatura cronológica', () => {
    expect(buildTemperatureChart(readings)).toEqual({
      labels: ['18:00', '18:05'],
      temperatures: [5.2, 5.6],
    })
  })

  it('produz um resumo textual que não depende somente do gráfico', () => {
    expect(describeTemperatureRange(readings, '1h')).toBe(
      'No período de 1 hora, foram recebidas 2 leituras: mínima de 5,2 °C e máxima de 5,6 °C.',
    )
  })

  it('explica quando ainda não existem leituras para o período', () => {
    expect(describeTemperatureRange([], '24h')).toBe(
      'Não há leituras de temperatura nas últimas 24 horas.',
    )
  })
})
