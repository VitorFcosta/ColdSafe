// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import fixture from './training.fixture.json'
import type { TargetResult } from './training-api'
import TrainingTarget from './TrainingTarget.vue'
vi.mock('vue-chartjs', () => ({ Scatter: { template: '<canvas />' } }))
describe('resultados de regressão', () => {
  it('explica validação, mostra valores reais e tabela alternativa', () => {
    const wrapper = mount(TrainingTarget, { props: { result: fixture.health as TargetResult } })
    expect(wrapper.text()).toContain('Saúde'); expect(wrapper.text()).toContain('Apto pela validação')
    expect(wrapper.text()).toContain('2,46'); expect(wrapper.text()).toContain('-0,02')
    expect(wrapper.text()).toContain('não demonstra causalidade')
    expect(wrapper.get('details table').text()).toContain('32')
    expect(wrapper.get('[role="img"]').attributes('aria-label')).toContain('Previsto versus real')
    wrapper.unmount()
  })
  it('distingue validação e teste, candidato e baseline sem trocar os valores', () => {
    const result: TargetResult = { ...fixture.health as TargetResult, metrics: {
      validation: { baseline: { mae: 10, rmse: 11, r2: null }, candidate: { mae: 1, rmse: 2, r2: .9 } },
      test: { baseline: { mae: 20, rmse: 21, r2: -.5 }, candidate: { mae: 3, rmse: 4, r2: .8 } },
    } }
    const wrapper = mount(TrainingTarget, { props: { result } })
    try {
      const comparison = wrapper.get('.validation-summary')
      expect(comparison.text()).toMatch(/Candidato.*1 ponto de saúde.*Referência.*10 pontos de saúde/s)
      expect(comparison.text()).not.toContain('20')
      expect(wrapper.get('details').attributes('open')).toBeUndefined()
      const rows = wrapper.get('[aria-label="Métricas de Saúde"]').findAll('tbody tr')
        .map(row => row.findAll('th,td').map(cell => cell.text()))
      expect(rows).toEqual([
        ['Validação', 'Baseline', '10', '11', 'Indefinido (alvo constante)'],
        ['Validação', 'Candidato', '1', '2', '0,9'],
        ['Teste reservado', 'Baseline', '20', '21', '-0,5'],
        ['Teste reservado', 'Candidato', '3', '4', '0,8'],
      ])
    } finally { wrapper.unmount() }
  })
  it('mostra precisão suficiente quando arredondar faria os erros parecerem iguais', () => {
    const result = structuredClone(fixture.health) as TargetResult
    result.metrics.validation.candidate.mae = 0.12341
    result.metrics.validation.baseline.mae = 0.12342
    const wrapper = mount(TrainingTarget, { props: { result } })
    try {
      const errors = wrapper.get('.validation-summary').findAll('dd').map((error) => error.text())
      expect(errors).toEqual(['0,12341 pontos de saúde', '0,12342 pontos de saúde'])
    } finally { wrapper.unmount() }
  })
  it('preserva zero legítimo e explica recorte de RUL sem linhas sem fabricar métricas', () => {
    const result: TargetResult = { ...fixture.rul as TargetResult, near_failure: {
      threshold_hours: 24, validation: { row_count: 0, baseline: null, candidate: null },
      test: { row_count: 0, baseline: null, candidate: null },
    } }
    const wrapper = mount(TrainingTarget, { props: { result } })
    try {
      const rows = wrapper.get('[aria-label="Métricas perto da falha"]').findAll('tbody tr')
      expect(rows).toHaveLength(4)
      for (const row of rows) {
        expect(row.findAll('td')[0]!.text()).toBe('0')
        expect(row.findAll('td').slice(2).map(cell => cell.text())).toEqual(['Sem linhas', 'Sem linhas', 'Sem linhas'])
      }
      expect(wrapper.get('details table').text()).toContain('32')
    } finally { wrapper.unmount() }
  })
  it('rejeitado não é apto e R² negativo próximo da falha é explícito', () => {
    const wrapper = mount(TrainingTarget, { props: { result: fixture.rul as TargetResult } })
    expect(wrapper.text()).toContain('Rejeitado pela validação'); expect(wrapper.text()).toContain('horas')
    expect(wrapper.text()).toContain('R² negativo'); expect(wrapper.text()).toContain('-1,2')
    wrapper.unmount()
  })
})
