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
  it('rejeitado não é apto e R² negativo próximo da falha é explícito', () => {
    const wrapper = mount(TrainingTarget, { props: { result: fixture.rul as TargetResult } })
    expect(wrapper.text()).toContain('Rejeitado pela validação'); expect(wrapper.text()).toContain('horas')
    expect(wrapper.text()).toContain('R² negativo'); expect(wrapper.text()).toContain('-1,2')
    wrapper.unmount()
  })
})
