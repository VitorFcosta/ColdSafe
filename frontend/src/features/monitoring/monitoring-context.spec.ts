// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { listDevices, listEnvironments } from '../account/catalog'
import { clearSession, monitoringSelection, saveMonitoringSelection, setSession, validatedMonitoringSelection, dashboardSelection, saveDashboardSelection } from '../account/session'
import { monitoringLocation, useMonitoringContext } from './use-monitoring-context'

vi.mock('../account/catalog', () => ({ listDevices: vi.fn(), listEnvironments: vi.fn() }))
const env = '00000000-0000-4000-8000-000000000001'
const otherEnv = '00000000-0000-4000-8000-000000000002'
const first = { id: '00000000-0000-4000-8000-000000000011', environment_id: env, mqtt_device_id: 'mqtt-first', name: 'Primeiro', is_active: true }
const second = { ...first, id: '00000000-0000-4000-8000-000000000012', mqtt_device_id: 'mqtt-second', name: 'Segundo' }
let wrapper: ReturnType<typeof mount> | undefined
beforeEach(() => {
  setSession('token', '2099-01-01T00:00:00Z')
  vi.mocked(listEnvironments).mockReset().mockResolvedValue([{ id: env, name: 'Laboratório' }, { id: otherEnv, name: 'Outro' }])
  vi.mocked(listDevices).mockReset().mockResolvedValue([first, second])
})
afterEach(() => { wrapper?.unmount(); clearSession() })

async function setup(url = '/dashboard') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push(url)
  let context!: ReturnType<typeof useMonitoringContext>
  wrapper = mount(defineComponent({ setup() { context = useMonitoringContext(); return () => null } }), { global: { plugins: [router] } })
  await flushPromises()
  return { context, router }
}

it('prioriza URL sobre preferência e primeira seleção; normaliza sem push e preserva query/hash', async () => {
  saveMonitoringSelection({ environmentId: env, deviceUuid: first.id })
  const { context, router } = await setup(`/dashboard?environment=${env}&device=${second.id}&extra=ok#history`)
  expect(context.selectedDevice.value).toEqual(second)
  expect(monitoringSelection.value).toEqual({ environmentId: env, deviceUuid: second.id })
  expect(router.currentRoute.value.query.extra).toBe('ok')
  expect(router.currentRoute.value.hash).toBe('#history')
})
it('restaura preferência da aba e escolhe primeiro somente quando não existe preferência', async () => {
  saveMonitoringSelection({ environmentId: env, deviceUuid: second.id })
  const { context, router } = await setup()
  expect(context.selectedDevice.value).toEqual(second)
  expect(router.currentRoute.value.query.device).toBe(second.id)
})
it('primeira entrada identifica o primeiro autorizado', async () => {
  const { context, router } = await setup()
  expect(context.selectedDevice.value).toEqual(first)
  expect(router.currentRoute.value.query.environment).toBe(env)
})
it.each([
  `environment=${env}`, `device=${first.id}`, 'environment=bad&device=bad',
  `environment=${env}&environment=${otherEnv}&device=${first.id}`,
  `environment=${otherEnv}&device=${first.id}`, `environment=${env}&device=${otherEnv}`,
])('não substitui um par inválido: %s', async (query) => {
  const { context } = await setup(`/dashboard?${query}`)
  expect(context.selectedDevice.value).toBeUndefined()
  expect(context.selectionNotice.value).toMatch(/Selecione/)
})
it.each(['inativo', 'inacessível', 'preferência removida'])('não troca silenciosamente: %s', async (kind) => {
  vi.mocked(listDevices).mockResolvedValue(kind === 'inativo' ? [{ ...second, is_active: false }] : [first])
  if (kind === 'preferência removida') saveMonitoringSelection({ environmentId: env, deviceUuid: second.id })
  const { context } = await setup(kind === 'preferência removida' ? '/dashboard' : `/dashboard?environment=${env}&device=${second.id}`)
  expect(context.selectedDevice.value).toBeUndefined()
  expect(context.selectionNotice.value).toMatch(/Selecione/)
})
it('recupera por escolha, mantém histórico e revalida voltar/avançar', async () => {
  const { context, router } = await setup()
  context.deviceUuid.value = second.id
  await flushPromises()
  expect(router.currentRoute.value.query.device).toBe(second.id)
  router.back(); await flushPromises()
  expect(context.selectedDevice.value).toEqual(first)
  router.forward(); await flushPromises()
  expect(context.selectedDevice.value).toEqual(second)
})
it('descarta catálogo fora de ordem e limpa seleção durante troca de ambiente', async () => {
  const { context } = await setup()
  let finish!: (devices: typeof first[]) => void
  vi.mocked(listDevices).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  context.environmentId.value = otherEnv
  await flushPromises()
  expect(context.selectedDevice.value).toBeUndefined()
  context.environmentId.value = env
  await flushPromises()
  finish([{ ...second, environment_id: otherEnv }]); await flushPromises()
  expect(context.selectedDevice.value).toEqual(first)
})
it('limpa contexto e ignora catálogo antigo após troca de conta/logout', async () => {
  let finish!: (devices: typeof first[]) => void
  vi.mocked(listDevices).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const { context } = await setup()
  setSession('other', '2099-01-01T00:00:00Z'); await flushPromises()
  finish([second]); await flushPromises()
  expect(context.selectedDevice.value).toEqual(first)
  expect(monitoringSelection.value?.deviceUuid).toBe(first.id)
  clearSession(); await flushPromises()
  expect(context.selectedDevice.value).toBeUndefined()
  expect(monitoringSelection.value).toBeNull()
})
it('falha de catálogo permite retry e vazio não fabrica seleção', async () => {
  vi.mocked(listEnvironments).mockRejectedValueOnce(new Error('offline'))
  const { context } = await setup()
  expect(context.catalogPhase.value).toBe('error')
  vi.mocked(listEnvironments).mockResolvedValue([])
  await context.loadEnvironments(); await flushPromises()
  expect(context.catalogPhase.value).toBe('ready')
  expect(context.selectedDevice.value).toBeUndefined()
})

it('ambiente escolhido vazio substitui o par antigo no endereço e no histórico', async () => {
  const { context, router } = await setup()
  vi.mocked(listDevices).mockResolvedValueOnce([])
  context.environmentId.value = otherEnv
  await flushPromises()
  expect(context.environmentId.value).toBe(otherEnv)
  expect(context.selectedDevice.value).toBeUndefined()
  expect(router.currentRoute.value.query).toEqual({ environment: otherEnv })
  expect(monitoringSelection.value).toBeNull()
  router.back(); await flushPromises()
  expect(context.selectedDevice.value).toEqual(first)
})

it('revogação limpa dados selecionados, links e preferência persistida sem apagar período próprio', async () => {
  saveDashboardSelection({ environmentId: env, deviceUuid: first.id, period: '24h' })
  const { context, router } = await setup()
  expect(JSON.parse(sessionStorage.getItem('coldsafe-session')!).monitoring_selection.deviceUuid).toBe(first.id)
  expect(monitoringLocation('/insights')).toEqual({ path: '/insights', query: { environment: env, device: first.id } })
  expect(monitoringLocation('/manage')).toEqual({ path: '/manage' })
  await context.revokeSelection(); await flushPromises()
  expect(context.selectedDevice.value).toBeUndefined()
  expect(monitoringSelection.value).toBeNull()
  expect(validatedMonitoringSelection.value).toBeNull()
  expect(JSON.parse(sessionStorage.getItem('coldsafe-session')!).monitoring_selection).toBeNull()
  expect(dashboardSelection.value?.period).toBe('24h')
  expect(monitoringLocation('/insights')).toEqual({ path: '/insights' })
  expect(router.currentRoute.value.query).toEqual({ environment: env })
})
