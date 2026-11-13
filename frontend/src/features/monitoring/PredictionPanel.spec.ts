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
    expect(wrapper.text()).toContain('equipment-id')
    expect(wrapper.text()).toContain('dados gerados para teste')
    expect(wrapper.text()).toContain('Idade da leitura')
    expect(wrapper.text()).toContain('Agora mesmo')
    expect(wrapper.text()).toContain(Intl.DateTimeFormat().resolvedOptions().timeZone)
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
    ['invalid_features', 'Não foi possível calcular a previsão com estas leituras'], ['model_unavailable', 'Modelo indisponível'], ['stale_input', 'Leitura desatualizada'],
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

  it('conserva a última previsão identificada durante a espera da próxima leitura', async () => {
    const wrapper = mount(PredictionPanel, { props: { summary, ageSeconds: 4 } })
    const values = wrapper.get('.prediction-values').element
    const metadata = wrapper.get('.prediction-meta').element
    const message = wrapper.get('[role="status"]').text()
    await wrapper.setProps({ summary: { ...summary, prediction: null } })
    expect(wrapper.get('.prediction-values').element).toBe(values)
    expect(wrapper.get('.prediction-meta').element).toBe(metadata)
    expect(wrapper.text()).toContain('0 / 100')
    expect(wrapper.text()).toContain('model-1')
    expect(wrapper.text()).toContain('Previsão disponível')
    expect(wrapper.get('[role="status"]').text()).toBe(message)
    expect(wrapper.findAll('time')[0]!.attributes('datetime')).toBe(prediction.data.input_received_at)
    wrapper.unmount()
  })

  it('não alterna ausência de modelo com espera entre eventos do mesmo equipamento', async () => {
    const noModel: Prediction = { ...prediction, data: { ...prediction.data, status: 'unavailable', model_id: null,
      model_version: null, health_score: null, rul_hours: null, reason: 'no_model' } }
    const wrapper = mount(PredictionPanel, { props: { summary: { ...summary, prediction: noModel }, ageSeconds: 4 } })
    const before = wrapper.text()
    await wrapper.setProps({ summary: { ...summary, prediction: null } })
    expect(wrapper.text()).toBe(before)
    expect(wrapper.get('[role="status"]').text()).toContain('Nenhum modelo ativo')
    expect(wrapper.text()).not.toContain('0 / 100')
    wrapper.unmount()
  })

  it.each(['dispositivo', 'ambiente', 'equipamento'] as const)('descarta a previsão ao trocar %s', async (selection) => {
    const equipment = { equipment_id: 'equipment-id', running: true,
      led: { actuator_id: 'led', actual_state: false }, buzzer: { actuator_id: 'buzzer', actual_state: false } }
    const wrapper = mount(PredictionPanel, { props: { summary: { ...summary, equipment }, ageSeconds: 4 } })
    await wrapper.setProps({ summary: { ...summary, prediction: null, equipment,
      ...(selection === 'dispositivo' ? { device: { id: 'outro' } } : {}),
      ...(selection === 'ambiente' ? { environment: { id: 'outro', name: 'Outro' } } : {}),
      ...(selection === 'equipamento' ? { equipment: { ...equipment, equipment_id: 'outro' } } : {}),
    } })
    expect(wrapper.text()).not.toContain('model-1')
    expect(wrapper.text()).not.toContain('0 / 100')
    expect(wrapper.findAll('time')).toHaveLength(0)
    wrapper.unmount()
  })

  it('expira a previsão antiga mesmo com sensores enviando leituras novas', async () => {
    const wrapper = mount(PredictionPanel, { props: { summary, ageSeconds: 1 } })
    await wrapper.setProps({ summary: { ...summary, prediction: null,
      reading: { temperature_c: 5, humidity_percent: 60, received_at: '2026-10-12T18:00:31.100Z' } } })
    expect(wrapper.get('[role="status"]').text()).toContain('Previsão desatualizada')
    expect(wrapper.text()).not.toContain('0 / 100')
    expect(wrapper.text()).not.toContain('0 h')
    expect(wrapper.findAll('time')[0]!.attributes('datetime')).toBe(prediction.data.input_received_at)
    wrapper.unmount()
  })

  it('um motivo explícito novo prevalece sobre a previsão guardada', async () => {
    const wrapper = mount(PredictionPanel, { props: { summary, ageSeconds: 1 } })
    await wrapper.setProps({ summary: { ...summary, prediction: null, prediction_unavailable_reason: 'model_unavailable' } })
    expect(wrapper.get('[role="status"]').text()).toContain('Modelo indisponível')
    expect(wrapper.text()).not.toContain('model-1')
    expect(wrapper.text()).not.toContain('0 / 100')
    wrapper.unmount()
  })

  it('atualiza pelo evento validado mesmo quando o resumo da leitura mais nova não tem previsão', async () => {
    if (prediction.data.status !== 'available') throw new Error('Fixture deve conter uma previsão disponível')
    const wrapper = mount(PredictionPanel, { props: { summary: { ...summary, prediction: null,
      reading: { temperature_c: 5, humidity_percent: 60, equipment_id: 'equipment-id',
        device_record_id: 'device-id', received_at: '2026-10-12T18:00:01.100Z' } }, ageSeconds: 1 } })
    await wrapper.setProps({ streamedPrediction: prediction })
    expect(wrapper.text()).toContain('model-1')
    expect(wrapper.text()).toContain('0 / 100')
    await wrapper.setProps({ summary: { ...summary, prediction: null,
      reading: { temperature_c: 5, humidity_percent: 60, equipment_id: 'equipment-id',
        device_record_id: 'device-id', received_at: '2026-10-12T18:00:02.100Z' } } })
    expect(wrapper.text()).toContain('0 / 100')
    await wrapper.setProps({ streamedPrediction: { ...prediction, event_id: 'new-prediction',
      occurred_at: '2026-10-12T18:00:01.200Z', data: { ...prediction.data,
        input_received_at: '2026-10-12T18:00:01.100Z', health_score: 95 } } })
    expect(wrapper.text()).toContain('95 / 100')
    await wrapper.setProps({ streamedPrediction: prediction })
    expect(wrapper.text()).toContain('95 / 100')
    expect(wrapper.text()).not.toContain('0 / 100')
    wrapper.unmount()
  })

  it.each(['device_id', 'environment_id', 'device_record_id', 'equipment_id'] as const)(
    'não aceita evento do stream com %s diferente do selecionado', async (key) => {
      const wrapper = mount(PredictionPanel, { props: { summary: { ...summary, prediction: null,
        reading: { temperature_c: 5, humidity_percent: 60, equipment_id: 'equipment-id',
          device_record_id: 'device-id', received_at: '2026-10-12T18:00:01.100Z' } }, ageSeconds: 1 } })
      const foreign = key === 'equipment_id' ? { ...prediction, data: { ...prediction.data, equipment_id: 'foreign' } }
        : { ...prediction, [key]: 'foreign' }
      await wrapper.setProps({ streamedPrediction: foreign })
      expect(wrapper.text()).not.toContain('model-1')
      expect(wrapper.text()).not.toContain('0 / 100')
      wrapper.unmount()
    })
})
