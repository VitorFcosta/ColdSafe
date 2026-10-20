// @vitest-environment happy-dom
import { ref, type Ref } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { listDevices, listEnvironments } from '../features/account/catalog'
import { refreshSessionIdentity, sessionToken } from '../features/account/session'
import { fetchInsights, InsightsAccessError, type InsightsSnapshot } from '../features/insights/insights-api'
import type { MonitoringSummary } from '../features/monitoring/monitoring-summary'
import DigitalTwinView from './DigitalTwinView.vue'

const live = vi.hoisted(() => ({ enabled: true, insightsInput: null as unknown, state: null as unknown, summary: null as unknown, revision: null as unknown, connection: null as unknown, mqtt: null as unknown }))
vi.mock('../features/account/catalog', () => ({ listDevices: vi.fn(), listEnvironments: vi.fn() }))
vi.mock('../features/account/session', async (original) => ({ ...await original<typeof import('../features/account/session')>(), logout: vi.fn(), refreshSessionIdentity: vi.fn() }))
vi.mock('../features/insights/insights-api', async (original) => ({ ...await original<typeof import('../features/insights/insights-api')>(), fetchInsights: vi.fn() }))
vi.mock('../features/monitoring/monitoring-version', () => ({ get aiotEnabled() { return live.enabled } }))
vi.mock('../features/monitoring/use-monitoring-summary', () => ({ useMonitoringSummary: (_token: unknown, mqtt: unknown) => {
  live.mqtt = mqtt
  return { summary: live.summary, monitoringState: live.state, refreshRevision: live.revision, connectionState: live.connection }
} }))
vi.mock('../features/digital-twin/DigitalTwinScene.vue', () => ({ default: { name: 'DigitalTwinScene', props: ['items', 'selectedId', 'visual'], emits: ['select'], template: '<div data-scene />' } }))
vi.mock('../features/digital-twin/twin-state', async (original) => ({ ...await original<typeof import('../features/digital-twin/twin-state')>(), twinStatusLabels: { normal: 'Normal', attention: 'Atenção', critical: 'Crítico', no_data: 'Sem dados' }, twinColors: { normal: 0x197854, attention: 0xa96409, critical: 0xc3353c, no_data: 0x667681 }, buildTwinItems: (summary: MonitoringSummary | null, fresh: boolean, insights: InsightsSnapshot | null) => { live.insightsInput = insights; return [{ id: summary ? 'real-sensor-id' : null, key: 'temperature', label: 'Temperatura ambiente', kind: 'sensor', value: fresh ? '4 °C' : '—', status: fresh ? 'normal' : 'no_data', position: [0, 0, 0] }] } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
const device = { id: 'record-a', environment_id: 'env-a', mqtt_device_id: 'mqtt-a', name: 'Motor autorizado', is_active: true }
const other = { ...device, id: 'record-b', mqtt_device_id: 'mqtt-b', name: 'Motor B' }
const summary: MonitoringSummary = { environment: { id: 'env-a', name: 'A' }, device: { id: 'mqtt-a' }, reading: { temperature_c: 4, humidity_percent: 40, received_at: new Date().toISOString(), device_record_id: 'record-a', environment_id: 'env-a', equipment_id: 'equipment-a' }, status: 'normal', freshness: { age_seconds: 0, is_stale: false }, thresholds: { min_c: 0, max_c: 8, attention_margin_c: 1 } }
const snapshot: InsightsSnapshot = { device_id: 'mqtt-a', equipment_id: 'equipment-a', rules: { health_critical: 30, health_recovery: 40, rul_critical_hours: 24, rul_recovery_hours: 48, open_count: 3, close_count: 10 }, prediction: null, availability: 'no_data', age_seconds: null, trend: 'unknown', active_alerts: [] }
const mount = () => shallowMount(DigitalTwinView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
const state = () => live.state as Ref<{ kind: string }>
const data = () => live.summary as Ref<MonitoringSummary | null>
const revision = () => live.revision as Ref<number>
beforeEach(() => {
  vi.useFakeTimers()
  live.enabled = true
  live.state = ref({ kind: 'normal' }); live.summary = ref(structuredClone(summary)); live.revision = ref(0); live.connection = ref('connected')
  vi.mocked(listEnvironments).mockReset().mockResolvedValue([{ id: 'env-a', name: 'A' }, { id: 'env-b', name: 'B' }])
  vi.mocked(listDevices).mockReset().mockResolvedValue([device, other])
  vi.mocked(fetchInsights).mockReset().mockResolvedValue(snapshot)
  vi.mocked(refreshSessionIdentity).mockReset().mockResolvedValue(undefined)
  sessionToken.value = 'token-a'
})
afterEach(() => { vi.useRealTimers() })

describe('DigitalTwinView', () => {
  it('anima só com telemetria atual do escopo selecionado, sem exigir previsão', async () => {
    const equipment = { equipment_id: 'equipment-a', running: true,
      led: { actuator_id: 'led-a', actual_state: false }, buzzer: { actuator_id: 'buzzer-a', actual_state: true } }
    data().value = { ...summary, equipment }
    const wrapper = mount(); await flushPromises()
    const scene = () => wrapper.findComponent({ name: 'DigitalTwinScene' })
    expect(scene().props('visual')).toMatchObject({ running: true, temperature: 4, led: false, buzzer: true })
    state().value = { kind: 'stale' }; await flushPromises()
    expect(scene().props('visual')).toBeNull()
    state().value = { kind: 'normal' }; await flushPromises()
    expect(scene().props('visual')).toMatchObject({ running: true })
    data().value = { ...summary, equipment, environment: { id: 'foreign', name: 'Foreign' } }; await flushPromises()
    expect(scene().props('visual')).toBeNull()
    wrapper.unmount()
  })
  it('telemetria 1Hz não renova deadline nem cancela consulta em andamento', async () => {
    const alert = { alert_id: 'alert-a', kind: 'predictive_failure' as const, opened_at: '2026-10-19T12:00:00Z', source_event_id: 'reading-a', prediction_event_id: 'prediction-a' }
    vi.mocked(fetchInsights).mockResolvedValueOnce({ ...snapshot, active_alerts: [alert] })
    const wrapper = mount(); await flushPromises()
    let finish!: (value: InsightsSnapshot) => void
    vi.mocked(fetchInsights).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    revision().value++; await flushPromises()
    const signal = vi.mocked(fetchInsights).mock.calls[1]![2]!
    for (let second = 1; second <= 7; second++) {
      await vi.advanceTimersByTimeAsync(1000); revision().value++; await flushPromises()
      expect(signal.aborted).toBe(false); expect(fetchInsights).toHaveBeenCalledTimes(2)
    }
    await vi.advanceTimersByTimeAsync(1000)
    expect(signal.aborted).toBe(true)
    expect(wrapper.text()).toContain('Não foi possível atualizar os Insights')
    expect(wrapper.text()).toContain('Alerta preditivo persistente na última consulta confirmada')
    expect(live.insightsInput).toBeNull()
    await vi.advanceTimersByTimeAsync(1000)
    finish(snapshot); await flushPromises()
    expect(wrapper.text()).toContain('Não foi possível atualizar os Insights')
    expect(fetchInsights).toHaveBeenCalledTimes(2)
    revision().value++; await flushPromises()
    expect(fetchInsights).toHaveBeenCalledTimes(3)
    expect(wrapper.text()).not.toContain('Não foi possível atualizar os Insights'); wrapper.unmount()
  })
  it('GET de 1,5s completa com telemetria 1Hz e consolida uma atualização pendente', async () => {
    const wrapper = mount(); await flushPromises()
    const alert = { alert_id: 'alert-a', kind: 'predictive_failure' as const, opened_at: '2026-10-19T12:00:00Z', source_event_id: 'reading-a', prediction_event_id: 'prediction-a' }
    const updated = { ...snapshot, active_alerts: [alert] }
    vi.mocked(fetchInsights).mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve(updated), 1500)))
    revision().value++; await flushPromises()
    const signal = vi.mocked(fetchInsights).mock.calls[1]![2]!
    await vi.advanceTimersByTimeAsync(1000); revision().value++; await flushPromises()
    expect(signal.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(500); await flushPromises()
    expect(wrapper.text()).toContain('Alerta preditivo persistente na última consulta confirmada')
    expect(live.insightsInput).toEqual(updated)
    expect(fetchInsights).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })
  it('modo legado explica requisito AIoT sem consultar identificadores inventados', async () => {
    live.enabled = false
    const wrapper = mount(); await flushPromises()
    expect(wrapper.text()).toContain('requer AIoT v3')
    expect(listEnvironments).not.toHaveBeenCalled(); expect(fetchInsights).not.toHaveBeenCalled()
    expect(wrapper.find('[data-scene]').exists()).toBe(false); wrapper.unmount()
  })
  it('equivale cena e lista acessível, seleciona apenas IDs reais e permite teclado nativo', async () => {
    const wrapper = mount(); await flushPromises()
    expect(wrapper.get('h1').attributes('tabindex')).toBe('-1')
    const button = wrapper.get('[aria-label="Componentes do gêmeo digital"] button')
    expect(button.text()).toContain('real-sensor-id'); expect(button.text()).toContain('4 °C')
    expect(button.attributes('type')).toBe('button')
    wrapper.findComponent({ name: 'DigitalTwinScene' }).vm.$emit('select', 'real-sensor-id')
    await flushPromises()
    expect(button.attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[aria-label="Detalhes do componente"]').text()).toContain('real-sensor-id')
    wrapper.findComponent({ name: 'DigitalTwinScene' }).vm.$emit('select', 'invented-id')
    await flushPromises(); expect(button.attributes('aria-pressed')).toBe('true')
    await button.trigger('click'); expect(button.attributes('aria-pressed')).toBe('true')
    expect(wrapper.text()).toContain('faixas'); wrapper.unmount()
  })
  it.each(['stale', 'service_error', 'no_data'])('estado %s não mostra valores antigos', async (kind) => {
    const wrapper = mount(); await flushPromises(); state().value = { kind }; await flushPromises()
    expect(wrapper.get('[aria-label="Componentes do gêmeo digital"]').text()).not.toContain('4 °C')
    expect(wrapper.text()).toContain('Sem dados'); wrapper.unmount()
  })
  it('não apresenta resumo de outro ambiente, MQTT ou registro', async () => {
    const wrapper = mount(); await flushPromises()
    for (const invalid of [{ ...summary, environment: { id: 'env-b', name: 'B' } }, { ...summary, device: { id: 'mqtt-b' } }, { ...summary, reading: { ...summary.reading!, device_record_id: 'record-b' } }]) {
      data().value = invalid; await flushPromises()
      expect(wrapper.get('[aria-label="Componentes do gêmeo digital"]').text()).not.toContain('real-sensor-id')
    }
    wrapper.unmount()
  })
  it('erro de Insights fica explícito e nova revisão REST/WS recupera sem polling próprio', async () => {
    vi.mocked(fetchInsights).mockRejectedValueOnce(new Error('private'))
    const wrapper = mount(); await flushPromises()
    expect(wrapper.text()).toContain('Não foi possível atualizar os Insights'); expect(wrapper.text()).not.toContain('private')
    await vi.advanceTimersByTimeAsync(4000); expect(fetchInsights).toHaveBeenCalledOnce()
    revision().value++; await flushPromises(); expect(fetchInsights).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('Não foi possível atualizar os Insights'); wrapper.unmount()
  })
  it.each([401, 403, 404])('revogação %s limpa cena e dados privados sem refazer consulta bloqueada', async (status) => {
    vi.mocked(fetchInsights).mockRejectedValueOnce(new InsightsAccessError(status))
    const wrapper = mount(); await flushPromises()
    expect(wrapper.find('[data-scene]').exists()).toBe(false)
    expect((live.mqtt as Ref<string | null>).value).toBeNull()
    revision().value++; await flushPromises(); expect(fetchInsights).toHaveBeenCalledOnce()
    if (status === 401) expect(sessionToken.value).toBeNull()
    else expect(refreshSessionIdentity).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
  it.each(['device', 'environment', 'token'])('troca %s cancela e descarta consulta antiga', async (change) => {
    let reject!: (error: Error) => void
    vi.mocked(fetchInsights).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    const wrapper = mount(); await flushPromises()
    const signal = vi.mocked(fetchInsights).mock.calls[0]![2]!
    if (change === 'device') await wrapper.get('select[name="device"]').setValue(other.id)
    if (change === 'environment') { vi.mocked(listDevices).mockResolvedValueOnce([]); await wrapper.get('select[name="environment"]').setValue('env-b') }
    if (change === 'token') sessionToken.value = 'token-b'
    await flushPromises(); expect(signal.aborted).toBe(true)
    reject(new InsightsAccessError(401)); await flushPromises(); expect(sessionToken.value).not.toBeNull()
    expect(wrapper.find('[aria-label="Detalhes do componente"]').exists()).toBe(false); wrapper.unmount()
  })
  it('cancela deadline e desmontagem, ignora catálogo antigo', async () => {
    vi.mocked(fetchInsights).mockImplementationOnce((_token, _device, signal) => new Promise((_, reject) => signal!.addEventListener('abort', () => reject(new Error('deadline')))))
    const wrapper = mount(); await flushPromises(); await vi.advanceTimersByTimeAsync(8000)
    expect(wrapper.text()).toContain('Não foi possível atualizar os Insights')
    revision().value++; await flushPromises(); const signal = vi.mocked(fetchInsights).mock.calls[1]![2]!
    wrapper.unmount(); expect(signal.aborted).toBe(true)
    let finish!: (value: typeof device[]) => void
    vi.mocked(listDevices).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const leaving = mount(); await flushPromises(); leaving.unmount(); finish([device]); await flushPromises()
    expect(fetchInsights).toHaveBeenCalledTimes(2)
  })
  it('ignora sucesso depois do prazo mesmo quando o cliente não respeita abort', async () => {
    let finish!: (value: InsightsSnapshot) => void
    vi.mocked(fetchInsights).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = mount(); await flushPromises(); await vi.advanceTimersByTimeAsync(8000)
    finish(snapshot); await flushPromises()
    expect(wrapper.text()).toContain('Não foi possível atualizar os Insights'); wrapper.unmount()
  })
  it('não consulta inventários sem catálogo ou após catálogo antigo de outra sessão', async () => {
    let finish!: (value: typeof device[]) => void
    vi.mocked(listDevices).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = mount(); await flushPromises(); vi.mocked(listEnvironments).mockResolvedValueOnce([])
    sessionToken.value = 'token-b'; await flushPromises(); finish([device]); await flushPromises()
    expect(fetchInsights).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('Nenhum ambiente autorizado'); wrapper.unmount()
  })
})
