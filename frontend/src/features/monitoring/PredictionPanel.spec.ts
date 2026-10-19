// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { MonitoringSummary } from './monitoring-summary'
import type { Prediction, PredictionUnavailableReason } from './aiot-api'
import PredictionPanel from './PredictionPanel.vue'

const prediction: Prediction = {
  schema_version: 3, type: 'prediction', event_id: 'prediction-id', device_id: 'sim-1', device_record_id: 'device-id',
  environment_id: 'env', correlation_id: 'reading-id', occurred_at: '2026-10-12T18:00:00.200Z', received_at: '2026-10-12T18:00:00.200Z',
  data: { equipment_id: 'equipment-id', source_event_id: 'reading-id', input_received_at: '2026-10-12T18:00:00.100Z', features_version: 'features-1+one', model_id: 'model-id', model_version: 'model-1', status: 'available', health_score: 0, rul_hours: 0, reason: null },
}
const summary: MonitoringSummary = {
  environment: { id: 'env', name: 'Câmara' }, device: { id: 'sim-1' }, reading: null,
  status: 'normal', freshness: { is_stale: false, age_seconds: 4 }, thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 },
  prediction, prediction_unavailable_reason: null,
}

describe('PredictionPanel', () => {
  it('mostra saúde e RUL zero com unidades, versões e horários acessíveis', () => {
    const wrapper = mount(PredictionPanel, { props: { summary, ageSeconds: 4 } })
    expect(wrapper.find('[aria-label="Previsão do equipamento"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('0 / 100')
    expect(wrapper.text()).toContain('0 h')
    expect(wrapper.text()).toContain('model-1')
    expect(wrapper.text()).toContain('features-1+one')
    expect(wrapper.findAll('time').map((item) => item.attributes('datetime'))).toEqual(['2026-10-12T18:00:00.100Z', '2026-10-12T18:00:00.200Z'])
  })

  it('atualiza a versão em execução e oculta números quando envelhecem', async () => {
    const wrapper = mount(PredictionPanel, { props: { summary, ageSeconds: 30 } })
    expect(wrapper.text()).toContain('0 / 100')
    await wrapper.setProps({ summary: { ...summary, prediction: { ...prediction, data: { ...prediction.data, model_version: 'model-2' } } } })
    expect(wrapper.text()).toContain('model-2')
    expect(wrapper.text()).not.toContain('model-1')
    await wrapper.setProps({ ageSeconds: 31 })
    expect(wrapper.get('[role="status"]').text()).toContain('Leitura desatualizada')
    expect(wrapper.text()).not.toContain('0 / 100')
    expect(wrapper.text()).not.toContain('0 h')
  })

  it.each([
    ['no_model', 'Nenhum modelo ativo'], ['insufficient_history', 'Histórico insuficiente'],
    ['invalid_features', 'Variáveis inválidas'], ['model_unavailable', 'Modelo indisponível'], ['stale_input', 'Leitura desatualizada'],
  ] as const)('distingue %s de resultado zero', (reason: PredictionUnavailableReason, label) => {
    const wrapper = mount(PredictionPanel, { props: { summary: { ...summary, prediction: null, prediction_unavailable_reason: reason }, ageSeconds: 4 } })
    expect(wrapper.get('[role="status"]').text()).toContain(label)
    expect(wrapper.text()).not.toContain('0 / 100')
    expect(wrapper.text()).not.toContain('0 h')
  })

  it('exibe aquecimento explícito e preserva versão em previsão indisponível', () => {
    const unavailable: Prediction = { ...prediction, data: { ...prediction.data, status: 'unavailable', health_score: null, rul_hours: null, reason: 'insufficient_history' } }
    const wrapper = mount(PredictionPanel, { props: { summary: { ...summary, prediction: unavailable }, ageSeconds: 4 } })
    expect(wrapper.text()).toContain('Histórico insuficiente')
    expect(wrapper.text()).toContain('model-1')
    expect(wrapper.text()).not.toContain('0 h')
  })

  it('aguarda inferência sem inventar métricas ou motivo sem evento', () => {
    const wrapper = mount(PredictionPanel, { props: { summary: { ...summary, prediction: null }, ageSeconds: 4 } })
    expect(wrapper.get('[role="status"]').text()).toContain('Aguardando previsão')
    expect(wrapper.text()).not.toContain('0 / 100')
    expect(wrapper.text()).not.toContain('Modelo:')
  })
})
