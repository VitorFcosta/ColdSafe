// @vitest-environment happy-dom
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { sessionRole, sessionToken } from '../account/session'
import { parseAiotSnapshot } from '../monitoring/aiot-api'
import { fetchMonitoringHistory, type MonitoringHistory } from '../monitoring/monitoring-history'
import { buildTwinItems } from './twin-state'
import TwinItemPanel from './TwinItemPanel.vue'

vi.mock('../monitoring/monitoring-history', async (original) => ({ ...await original<typeof import('../monitoring/monitoring-history')>(), fetchMonitoringHistory: vi.fn() }))
vi.mock('../monitoring/actuators', async (original) => ({ ...await original<typeof import('../monitoring/actuators')>(), fetchActuators: vi.fn().mockResolvedValue({ led: null, buzzer: null }) }))
const examples = JSON.parse(readFileSync(resolve(fileURLToPath(import.meta.url), '../../../../../contracts/examples/aiot.valid.json'), 'utf8'))
const telemetry = examples.find((item: { name: string }) => item.name === 'telemetry_received').payload
const prediction = examples.find((item: { name: string }) => item.name === 'prediction_available_zero_rul').payload
const summary = parseAiotSnapshot({ environment: { id: telemetry.environment_id, name: 'Lab' }, device: { id: telemetry.device_id },
  telemetry, prediction, persistence: 'persisted', thresholds: { min_c: 2, max_c: 8, attention_margin_c: 1 },
  freshness: { state: 'fresh', age_seconds: 1, last_event_id: telemetry.event_id, last_received_at: telemetry.received_at, stale_after_seconds: 30 },
  commands: { led: null, buzzer: null } })!
const device = { id: telemetry.device_record_id, environment_id: telemetry.environment_id, name: 'Ventilador', mqtt_device_id: telemetry.device_id, is_active: true }
const items = buildTwinItems(summary, true, null)
const history: MonitoringHistory = { deviceId: telemetry.device_id, start: '2026-10-12T18:00:00Z', end: '2026-10-12T18:15:00Z', limit: 300,
  readings: [{ ...summary.reading!, status: 'normal', persistence: 'persisted' }] }
let wrapper: VueWrapper | undefined
function render(key = 'temperature_c') {
  wrapper = mount(TwinItemPanel, { props: { item: items.find((item) => item.key === key)!, summary, device, token: 'token', fresh: true, ageSeconds: 1, revision: 0, connectionState: 'connected' },
    global: { stubs: { TemperatureHistoryChart: { name: 'TemperatureHistoryChart', props: ['readings', 'metric'], template: '<div data-chart />' }, LedControl: { name: 'LedControl', props: ['led', 'phase', 'submitting', 'error'], template: '<div data-led-control />' } } } })
  return wrapper
}
beforeEach(() => {
  vi.useFakeTimers()
  sessionToken.value = 'token'; sessionRole.value = 'operator'
  vi.mocked(fetchMonitoringHistory).mockReset().mockResolvedValue(history)
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })

it('inspeciona sensores pelo ID e mantém previsão do equipamento separada de saúde própria não aplicável', async () => {
  const view = render(); await flushPromises()
  expect(view.text()).toContain(items[0]!.id)
  expect(view.text()).toContain('6,5 °C')
  expect(view.text()).toContain('Agora mesmo')
  expect(view.text()).toContain('Saúde/RUL deste item: não aplicável')
  expect(view.text()).toContain('equipamento associado')
  expect(view.text()).toContain(summary.equipment!.equipment_id)
  expect(view.getComponent({ name: 'PredictionPanel' }).props('summary')).toEqual(summary)
  expect(view.getComponent({ name: 'TemperatureHistoryChart' }).props('metric')).toBe('temperature_c')
  expect(fetchMonitoringHistory).toHaveBeenCalledWith(expect.objectContaining({ token: 'token', deviceId: device.mqtt_device_id, period: '15m' }))
  for (const item of items.filter((item) => item.kind === 'sensor')) {
    await view.setProps({ item })
    expect(view.getComponent({ name: 'TemperatureHistoryChart' }).props('metric')).toBe(item.key)
  }
})

it('exclui leituras de outro sensor, ambiente, registro ou equipamento mesmo sob mesmo MQTT', async () => {
  const reading = history.readings[0]!
  const wrongSensor = { ...reading, sensor_ids: { ...reading.sensor_ids, ambient_temperature: 'replaced-sensor' } }
  vi.mocked(fetchMonitoringHistory).mockResolvedValue({ ...history, readings: [wrongSensor,
    { ...reading, environment_id: 'foreign' }, { ...reading, device_record_id: 'foreign' }, { ...reading, equipment_id: 'foreign' }, reading] })
  const view = render(); await flushPromises()
  expect(view.getComponent({ name: 'TemperatureHistoryChart' }).props('readings')).toEqual([reading])
  await view.setProps({ item: { ...items[0]!, id: 'another-sensor' } })
  expect(view.find('[data-chart]').exists()).toBe(false)
  expect(view.text()).toContain('Sem leituras históricas para este ID')
})

it('equipamento usa sua previsão; atuadores explicam histórico associado e só LED oferece controle manual', async () => {
  const view = render('fan'); await flushPromises()
  expect(view.text()).not.toContain('Saúde/RUL deste item: não aplicável')
  expect(view.text()).toContain('Em operação')
  expect(view.text()).toContain('0 h')
  await view.setProps({ item: items.find((item) => item.key === 'led')! })
  expect(view.find('[data-led-control]').exists()).toBe(true)
  expect(view.text()).toContain('não possui histórico próprio')
  await view.setProps({ item: items.find((item) => item.key === 'buzzer')! })
  expect(view.find('[data-led-control]').exists()).toBe(false)
  expect(view.text()).toContain('Buzzer segue a regra térmica')
})

it('leitura vencida é histórica, idade continua explícita e saúde/RUL atuais são ocultadas', async () => {
  const view = render('fan'); await flushPromises()
  await view.setProps({ fresh: false, ageSeconds: 35, item: { ...items.find((item) => item.key === 'fan')!, status: 'no_data', value: 'Sem dados atuais' } })
  expect(view.text()).toContain('Leitura histórica; situação atual não confirmada')
  expect(view.text()).toContain('Há 35 s')
  expect(view.text()).toContain('Em operação')
  expect(view.text()).not.toContain('0 h')
})

it('consulta lenta não é cancelada por revisões 1Hz e expira em oito segundos com recuperação', async () => {
  let finish!: (value: MonitoringHistory) => void
  vi.mocked(fetchMonitoringHistory).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const view = render(); await flushPromises()
  for (let revision = 1; revision <= 7; revision++) {
    await vi.advanceTimersByTimeAsync(1000); await view.setProps({ revision })
    expect(fetchMonitoringHistory).toHaveBeenCalledTimes(1)
  }
  await vi.advanceTimersByTimeAsync(1000)
  expect(view.text()).toContain('Histórico indisponível')
  finish(history); await flushPromises()
  expect(view.find('[data-chart]').exists()).toBe(false)
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(view.find('[data-chart]').exists()).toBe(true)
})

it('troca de escopo limpa histórico, ignora resposta antiga e desmontagem encerra consultas', async () => {
  let finish!: (value: MonitoringHistory) => void
  vi.mocked(fetchMonitoringHistory).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const view = render(); await flushPromises()
  await view.setProps({ token: 'token-b' }); await flushPromises()
  expect(view.find('[data-chart]').exists()).toBe(true)
  finish({ ...history, readings: [{ ...history.readings[0]!, temperature_c: 123 }] }); await flushPromises()
  expect(view.getComponent({ name: 'TemperatureHistoryChart' }).props('readings')).toEqual(history.readings)
  view.unmount(); wrapper = undefined
  const calls = vi.mocked(fetchMonitoringHistory).mock.calls.length
  await vi.advanceTimersByTimeAsync(20_000)
  expect(fetchMonitoringHistory).toHaveBeenCalledTimes(calls)
})
