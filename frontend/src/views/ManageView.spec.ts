// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { sessionToken } from '../features/account/session'
import {
  createDevice, createEnvironment, deactivateDevice, getRules, listDevices, listEnvironments,
  updateDevice, updateEnvironment, updateRules,
} from '../features/account/catalog'
import ManageView from './ManageView.vue'

vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
vi.mock('../features/account/catalog', () => ({
  createDevice: vi.fn(), createEnvironment: vi.fn(), deactivateDevice: vi.fn(), getRules: vi.fn(),
  listDevices: vi.fn(), listEnvironments: vi.fn(), updateDevice: vi.fn(), updateEnvironment: vi.fn(), updateRules: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  sessionToken.value = 'token-1'
  vi.mocked(listEnvironments).mockResolvedValue([{ id: 'env-1', name: 'Câmara 1' }])
  vi.mocked(listDevices).mockResolvedValue([{ id: 'dev-1', environment_id: 'env-1', name: 'ESP32', mqtt_device_id: 'esp32-1', is_active: true }])
  vi.mocked(getRules).mockResolvedValue({ min_c: 2, max_c: 8, attention_margin_c: 0.5 })
  vi.mocked(createDevice).mockResolvedValue({ id: 'dev-2', environment_id: 'env-1', name: 'Novo sensor', mqtt_device_id: 'esp32-2', is_active: true })
  vi.mocked(updateRules).mockResolvedValue({ min_c: 3, max_c: 9, attention_margin_c: 0.5 })
  vi.mocked(deactivateDevice).mockResolvedValue({ id: 'dev-1', environment_id: 'env-1', name: 'ESP32', mqtt_device_id: 'esp32-1', is_active: false })
})

it('carrega dados, cadastra dispositivo, altera limites e desativa com confirmação', async () => {
  vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()
  expect(wrapper.text()).toContain('Câmara 1')
  expect(wrapper.text()).toContain('esp32-1')

  await wrapper.get('#device-name').setValue('Novo sensor')
  await wrapper.get('#mqtt-id').setValue('esp32-2')
  await wrapper.get('#device-name').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(createDevice).toHaveBeenCalledWith('token-1', 'env-1', 'Novo sensor', 'esp32-2')

  await wrapper.get('#min-c').setValue('3')
  await wrapper.get('#max-c').setValue('9')
  await wrapper.get('#min-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(updateRules).toHaveBeenCalledWith('token-1', 'env-1', { min_c: 3, max_c: 9, attention_margin_c: 0.5 })

  await wrapper.get('.danger').trigger('click')
  await flushPromises()
  expect(deactivateDevice).toHaveBeenCalledWith('token-1', 'dev-1')
  wrapper.unmount()
})

it('mostra falha de carregamento e impede limites inválidos', async () => {
  vi.mocked(listDevices).mockRejectedValueOnce(new Error('Serviço indisponível.'))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('Serviço indisponível.')

  await wrapper.get('.item-name').trigger('click')
  await flushPromises()
  await wrapper.get('#min-c').setValue('10')
  await wrapper.get('#max-c').setValue('9')
  await wrapper.get('#min-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('mínimo menor que máximo')
  expect(updateRules).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('cadastra e renomeia ambientes e dispositivos mantendo a seleção', async () => {
  vi.mocked(listEnvironments).mockResolvedValue([
    { id: 'env-1', name: 'Câmara 1' }, { id: 'env-2', name: 'Câmara 2' },
  ])
  vi.mocked(createEnvironment).mockResolvedValue({ id: 'env-2', name: 'Câmara 2' })
  vi.mocked(updateEnvironment).mockResolvedValue({ id: 'env-2', name: 'Câmara de vacinas' })
  vi.mocked(listDevices).mockImplementation(async (_token, environmentId) => [
    { id: 'dev-1', environment_id: environmentId, name: 'ESP32', mqtt_device_id: 'esp32-1', is_active: true },
  ])
  vi.mocked(updateDevice).mockResolvedValue({ id: 'dev-1', environment_id: 'env-2', name: 'Sensor reserva', mqtt_device_id: 'esp32-1', is_active: true })
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()

  await wrapper.get('#environment-name').setValue(' Câmara 2 ')
  await wrapper.get('.inline-form').trigger('submit')
  await flushPromises()
  expect(createEnvironment).toHaveBeenCalledWith('token-1', 'Câmara 2')
  expect(wrapper.findAll('.item-name')[1]?.attributes('aria-pressed')).toBe('true')

  await wrapper.findAll('.small-action')[1]?.trigger('click')
  await wrapper.get('input[aria-label="Nome do ambiente"]').setValue('Câmara de vacinas')
  await wrapper.get('.edit-form').trigger('submit')
  await flushPromises()
  expect(updateEnvironment).toHaveBeenCalledWith('token-1', 'env-2', 'Câmara de vacinas')

  await wrapper.get('.actions button').trigger('click')
  await wrapper.get('input[aria-label="Nome do dispositivo"]').setValue('Sensor reserva')
  await wrapper.get('.edit-form').trigger('submit')
  await flushPromises()
  expect(updateDevice).toHaveBeenCalledWith('token-1', 'dev-1', 'Sensor reserva')
  wrapper.unmount()
})

it('recusa identificador MQTT inválido e só desativa após confirmação', async () => {
  const confirm = vi.fn().mockReturnValue(false)
  vi.stubGlobal('confirm', confirm)
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()

  await wrapper.get('#device-name').setValue('Sensor')
  await wrapper.get('#mqtt-id').setValue('id inválido')
  await wrapper.get('#device-name').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('ID MQTT')
  expect(createDevice).not.toHaveBeenCalled()

  await wrapper.get('.danger').trigger('click')
  expect(confirm).toHaveBeenCalledOnce()
  expect(deactivateDevice).not.toHaveBeenCalled()
  wrapper.unmount()
})
