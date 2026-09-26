// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { sessionToken } from '../features/account/session'
import { createDevice, deactivateDevice, getRules, listDevices, listEnvironments, updateRules } from '../features/account/catalog'
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
