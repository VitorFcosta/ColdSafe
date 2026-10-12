import { describe, expect, it } from 'vitest'

import { buildTemperatureChart, describeHistoryCoverage, describeTemperatureRange, formatHistoryTick } from './temperature-chart'

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
  it('usa distância temporal real e interrompe a linha após 30 segundos sem leitura', () => {
    expect(buildTemperatureChart([
      readings[0]!, { ...readings[0]!, received_at: '2026-09-09T18:00:20Z' }, readings[1]!,
    ])).toEqual({
      points: [
        { x: Date.parse('2026-09-09T18:00:00Z'), y: 5.2 },
        { x: Date.parse('2026-09-09T18:00:20Z'), y: 5.2 },
        { x: Date.parse('2026-09-09T18:02:40Z'), y: null },
        { x: Date.parse('2026-09-09T18:05:00Z'), y: 5.6 },
      ],
      gaps: 1,
    })
  })

  it('mantém pontos próximos conectados e aceita 0 ou 1 leitura com luminosidade nula', () => {
    expect(buildTemperatureChart([]).points).toEqual([])
    expect(buildTemperatureChart([{ ...readings[0]!, light_percent: null }]).points).toEqual([
      { x: Date.parse('2026-09-09T18:00:00Z'), y: 5.2 },
    ])
    expect(buildTemperatureChart([
      readings[0]!, { ...readings[1]!, received_at: '2026-09-09T18:00:30Z' },
    ]).points).toHaveLength(2)
  })

  it('identifica a data local ao atravessar a meia-noite', () => {
    expect(formatHistoryTick(Date.parse('2026-09-10T02:59:00Z'), 'America/Sao_Paulo')).toBe('09/09 23:59')
    expect(formatHistoryTick(Date.parse('2026-09-10T03:01:00Z'), 'America/Sao_Paulo')).toBe('10/09 00:01')
  })

  it('produz um resumo textual que não depende somente do gráfico', () => {
    expect(describeTemperatureRange(readings, '1h')).toBe(
      'No período de 1 hora, foram retornadas 2 leituras: mínima de 5,2 °C e máxima de 5,6 °C.',
    )
  })

  it('explica quando ainda não existem leituras para o período', () => {
    expect(describeTemperatureRange([], '24h')).toBe(
      'Não há leituras de temperatura nas últimas 24 horas.',
    )
  })

  it('descreve somente o intervalo observado e avisa quando a consulta atinge o limite', () => {
    const partial = Array.from({ length: 55 }, (_, index) => ({
      ...readings[0]!, received_at: new Date(Date.parse(readings[0]!.received_at) + index * 5_000).toISOString(),
    }))
    expect(describeHistoryCoverage(partial, 300, 'America/Sao_Paulo')).toContain('55 leituras retornadas')
    expect(describeHistoryCoverage(partial, 300, 'America/Sao_Paulo')).toContain('15:00:00')
    expect(describeHistoryCoverage(partial, 300, 'America/Sao_Paulo')).not.toContain('cobertura completa')
    expect(describeHistoryCoverage([...partial, ...Array.from({ length: 245 }, (_, index) => ({
      ...readings[0]!, received_at: new Date(Date.parse(readings[0]!.received_at) + (index + 55) * 5_000).toISOString(),
    }))], 300, 'America/Sao_Paulo')).toContain('Limite de 300 atingido')
    expect(describeHistoryCoverage([], 300)).toContain('Nenhuma leitura retornada')
  })
})
