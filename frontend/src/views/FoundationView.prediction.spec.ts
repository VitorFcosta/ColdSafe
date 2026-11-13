// @vitest-environment happy-dom
import { useRoute } from 'vue-router'
import { clearMonitoringSelection } from '../features/account/session'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { sessionToken } from '../features/account/session'
import type { Prediction } from '../features/monitoring/aiot-api'
import type { MonitoringSummary } from '../features/monitoring/monitoring-summary'
import { useMonitoringSummary } from '../features/monitoring/use-monitoring-summary'
import PredictionPanel from '../features/monitoring/PredictionPanel.vue'
import FoundationView from './FoundationView.vue'

vi.mock('../features/monitoring/monitoring-version', () => ({ aiotEnabled: true }))
vi.mock('../features/account/catalog', () => ({
  listEnvironments: vi.fn().mockResolvedValue([{ id: '00000000-0000-4000-8000-000000000001', name: 'Laboratório' }]),
  listDevices: vi.fn().mockResolvedValue([
    { id: '00000000-0000-4000-8000-000000000011', environment_id: '00000000-0000-4000-8000-000000000001', name: 'Simulador', mqtt_device_id: 'sim-1', is_active: true },
  ]),
}))
vi.mock('../features/monitoring/monitoring-history', async (original) => ({
  ...await original<typeof import('../features/monitoring/monitoring-history')>(),
  fetchMonitoringHistory: vi.fn().mockResolvedValue({ deviceId: 'sim-1', readings: [],
    start: '2026-10-25T03:00:00Z', end: '2026-10-25T04:00:00Z', limit: 300 }),
}))
vi.mock('../features/monitoring/use-actuators', () => ({
  actuatorLabel: () => 'Sem confirmação',
  useActuators: () => ({ led: ref(null), buzzer: ref(null), actuatorPhase: ref('ready'),
    commandError: ref(''), commandSubmitting: ref(false), loadActuators: vi.fn(), toggleLed: vi.fn() }),
}))
vi.mock('../features/monitoring/use-monitoring-summary', () => ({
  useMonitoringSummary: vi.fn(), formatFreshness: () => 'Agora mesmo',
}))
vi.mock('vue-router', async (original) => {
  const actual = await original<typeof import('vue-router')>()
  const { reactive } = await import('vue')
  const route = reactive({ path: '/dashboard', query: {}, hash: '' })
  const navigate = async (target: object) => { Object.assign(route, target) }
  return { ...actual, useRoute: () => route, useRouter: () => ({ push: vi.fn(navigate), replace: vi.fn(navigate) }) }
})

afterEach(() => { sessionToken.value = null })

it('preserva a previsão mais nova após evento atrasado, falha REST e recuperação', async () => {
  Object.assign(useRoute(), { path: '/dashboard', query: {}, hash: '' })
  clearMonitoringSelection()
  sessionToken.value = 'token'
  const snapshot: MonitoringSummary = {
    environment: { id: '00000000-0000-4000-8000-000000000001', name: 'Laboratório' }, device: { id: 'sim-1' },
    status: 'normal', freshness: { is_stale: false, age_seconds: 1 },
    thresholds: { min_c: 2, max_c: 8, attention_margin_c: 0.5 }, prediction: null,
    reading: { temperature_c: 5, humidity_percent: 60, received_at: '2026-10-25T04:00:02Z',
      device_record_id: '00000000-0000-4000-8000-000000000011', equipment_id: 'equipment' },
  }
  const summary = ref<MonitoringSummary | null>(snapshot)
  vi.mocked(useMonitoringSummary).mockReturnValue({ summary, refreshRevision: ref(0),
    loadSummary: vi.fn().mockResolvedValue(undefined), connectionState: ref('connected'),
    monitoringState: computed(() => ({ kind: 'normal', history: 'ready' } as const)),
    ageSeconds: computed(() => 1),
  })
  const wrapper = shallowMount(FoundationView, { global: { renderStubDefaultSlot: true, stubs: { LiveDataRegion: false, RouterLink: true, PredictionPanel: false } } })
  await flushPromises()
  const onEvent = vi.mocked(useMonitoringSummary).mock.calls[0]![2]!
  const newest: Prediction = {
    schema_version: 3, type: 'prediction', event_id: 'new', device_id: 'sim-1', device_record_id: '00000000-0000-4000-8000-000000000011',
    environment_id: '00000000-0000-4000-8000-000000000001', correlation_id: 'source', occurred_at: '2026-10-25T04:00:01.200Z',
    received_at: '2026-10-25T04:00:01.200Z',
    data: { equipment_id: 'equipment', source_event_id: 'source', input_received_at: '2026-10-25T04:00:01Z',
      features_version: 'features-1', model_id: 'model', model_version: 'latest-model',
      status: 'available', reason: null, health_score: 95, rul_hours: 100 },
  }
  onEvent(newest)
  await flushPromises()
  expect(wrapper.getComponent(PredictionPanel).text()).toContain('95 / 100')
  onEvent({ ...newest, event_id: 'old', occurred_at: '2026-10-25T04:00:00.200Z',
    data: { ...newest.data, input_received_at: '2026-10-25T04:00:00Z', model_version: 'old-model' } })
  summary.value = null
  await flushPromises()
  expect(wrapper.findComponent(PredictionPanel).exists()).toBe(false)
  summary.value = snapshot
  await flushPromises()
  expect(wrapper.getComponent(PredictionPanel).text()).toContain('latest-model')
  expect(wrapper.getComponent(PredictionPanel).text()).not.toContain('old-model')
  expect(wrapper.getComponent(PredictionPanel).text()).toContain('95 / 100')
  wrapper.unmount()
})
