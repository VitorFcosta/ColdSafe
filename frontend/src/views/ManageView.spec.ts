// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { sessionToken, sessionRole } from '../features/account/session'
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
  sessionRole.value = 'operator'
  vi.mocked(listEnvironments).mockResolvedValue([{ id: 'env-1', name: 'Câmara 1' }])
  vi.mocked(listDevices).mockResolvedValue([{ id: 'dev-1', environment_id: 'env-1', name: 'ESP32', mqtt_device_id: 'esp32-1', is_active: true }])
  vi.mocked(getRules).mockResolvedValue({ min_c: 2, max_c: 8, attention_margin_c: 0.5 })
  vi.mocked(createDevice).mockResolvedValue({ id: 'dev-2', environment_id: 'env-1', name: 'Novo sensor', mqtt_device_id: 'esp32-2', is_active: true })
  vi.mocked(updateRules).mockResolvedValue({ min_c: 3, max_c: 9, attention_margin_c: 0.5 })
  vi.mocked(deactivateDevice).mockResolvedValue({ id: 'dev-1', environment_id: 'env-1', name: 'ESP32', mqtt_device_id: 'esp32-1', is_active: false })
})

it.each(['viewer', null] as const)('mantém catálogo legível sem permitir alterações para papel %s', async (role) => {
  sessionRole.value = role
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()
  expect(wrapper.text()).toContain(role === 'viewer' ? 'Modo visualizador' : 'Permissões ainda não confirmadas')
  expect(wrapper.get('[data-test="open-environment-form"]').attributes('disabled')).toBeDefined()
  expect(wrapper.get('[data-test="open-device-form"]').attributes('disabled')).toBeDefined()
  await wrapper.get('form.fields').trigger('submit')
  await flushPromises()
  expect(updateRules).not.toHaveBeenCalled()
  expect(createEnvironment).not.toHaveBeenCalled()
  expect(wrapper.get('.item-name').attributes('disabled')).toBeUndefined()
  wrapper.unmount()
})

it('carrega dados, cadastra dispositivo, altera limites e desativa com confirmação', async () => {
  vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()
  expect(wrapper.text()).toContain('Câmara 1')
  expect(wrapper.text()).toContain('esp32-1')

  await wrapper.get('[data-test="open-device-form"]').trigger('click')
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

it('mostra falha de carregamento e impede limites inválidos perto dos campos', async () => {
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
  expect(wrapper.get('#min-c-error').text()).toContain('menor que o máximo')
  expect(wrapper.get('#max-c-error').text()).toContain('maior que o mínimo')
  expect(wrapper.get('#min-c').attributes('aria-invalid')).toBe('true')
  expect((wrapper.get('#min-c').element as HTMLInputElement).value).toBe('10')
  expect(updateRules).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('explica a margem no campo, preserva rascunho e só confirma limites aceitos pela API', async () => {
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()

  await wrapper.get('#margin-c').setValue('4')
  await wrapper.get('#margin-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(wrapper.get('#margin-c-error').text()).toContain('menor que metade')
  expect(wrapper.get('#margin-c').attributes('aria-describedby')).toContain('margin-c-error')
  expect((wrapper.get('#margin-c').element as HTMLInputElement).value).toBe('4')
  expect(updateRules).not.toHaveBeenCalled()

  vi.mocked(updateRules).mockRejectedValueOnce(new Error('API indisponível.'))
  await wrapper.get('#margin-c').setValue('1')
  await wrapper.get('#margin-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(wrapper.get('#rules-save-error').text()).toContain('API indisponível.')
  expect(wrapper.text()).not.toContain('Alteração salva.')
  expect((wrapper.get('#margin-c').element as HTMLInputElement).value).toBe('1')

  await wrapper.get('#margin-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(updateRules).toHaveBeenCalledTimes(2)
  expect(wrapper.get('[role="status"]').text()).toContain('Limites')
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

  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue(' Câmara 2 ')
  await wrapper.get('.inline-form').trigger('submit')
  await flushPromises()
  expect(createEnvironment).toHaveBeenCalledWith('token-1', 'Câmara 2')
  expect(wrapper.findAll('.item-name')[1]?.attributes('aria-pressed')).toBe('true')

  await wrapper.findAll('.small-action')[1]?.trigger('click')
  await wrapper.get('input[aria-label="Nome do ambiente Câmara 2"]').setValue('Câmara de vacinas')
  await wrapper.get('.edit-form').trigger('submit')
  await flushPromises()
  expect(updateEnvironment).toHaveBeenCalledWith('token-1', 'env-2', 'Câmara de vacinas')

  await wrapper.get('.actions button').trigger('click')
  await wrapper.get('input[aria-label="Nome do dispositivo ESP32"]').setValue('Sensor reserva')
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

  await wrapper.get('[data-test="open-device-form"]').trigger('click')
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

it('prioriza listas e oferece inclusão no estado vazio sem alterar a API ao cancelar', async () => {
  vi.mocked(listEnvironments).mockResolvedValue([])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()

  expect(wrapper.text()).toContain('Nenhum ambiente cadastrado')
  expect(wrapper.find('#environment-name').exists()).toBe(false)
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue('Rascunho')
  await wrapper.get('[data-test="cancel-environment-form"]').trigger('click')
  expect(wrapper.find('#environment-name').exists()).toBe(false)
  expect(createEnvironment).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('identifica o ambiente e cada ação mesmo com nomes longos e dispositivos inativos', async () => {
  const longName = 'Câmara de conservação de vacinas do laboratório central'.repeat(2)
  vi.mocked(listEnvironments).mockResolvedValue([
    { id: 'env-1', name: longName }, { id: 'env-2', name: 'Estoque' },
  ])
  vi.mocked(listDevices).mockImplementation(async (_token, id) => id === 'env-1'
    ? [{ id: 'dev-1', environment_id: id, name: 'Sensor principal', mqtt_device_id: 'esp32-1', is_active: false }]
    : [])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()

  expect(wrapper.get('#devices-title').text()).toContain(longName)
  expect(wrapper.get('#rules-title').text()).toContain(longName)
  expect(wrapper.find('.danger').exists()).toBe(false)
  expect(wrapper.get('.small-action').attributes('aria-label')).toContain(longName)
  await wrapper.findAll('.item-name')[1]!.trigger('click')
  await flushPromises()
  expect(wrapper.get('#devices-title').text()).toContain('Estoque')
  expect(wrapper.text()).toContain('Nenhum dispositivo cadastrado')
  expect(wrapper.find('#device-name').exists()).toBe(false)
  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  expect(wrapper.text()).toContain('Adicionar dispositivo em Estoque')
  await wrapper.get('#device-name').setValue('Rascunho')
  await wrapper.get('[data-test="cancel-device-form"]').trigger('click')
  expect(createDevice).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('cancela edições de ambiente e dispositivo sem enviar alterações', async () => {
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()

  await wrapper.get('.small-action').trigger('click')
  await wrapper.get('input[aria-label="Nome do ambiente Câmara 1"]').setValue('Nome temporário')
  await wrapper.get('button[aria-label="Cancelar edição do ambiente Câmara 1"]').trigger('click')
  expect(wrapper.get('.item-name').text()).toBe('Câmara 1')
  expect(updateEnvironment).not.toHaveBeenCalled()

  await wrapper.get('button[aria-label="Editar dispositivo ESP32"]').trigger('click')
  await wrapper.get('input[aria-label="Nome do dispositivo ESP32"]').setValue('Nome temporário')
  await wrapper.get('button[aria-label="Cancelar edição do dispositivo ESP32"]').trigger('click')
  expect(wrapper.get('.device-info strong').text()).toBe('ESP32')
  expect(updateDevice).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('mantém rascunhos de ambiente e dispositivo independentes', async () => {
  vi.mocked(updateEnvironment).mockResolvedValue({ id: 'env-1', name: 'Câmara revisada' })
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink'] } })
  await flushPromises()

  await wrapper.get('.small-action').trigger('click')
  await wrapper.get('input[aria-label="Nome do ambiente Câmara 1"]').setValue('Câmara revisada')
  await wrapper.get('button[aria-label="Editar dispositivo ESP32"]').trigger('click')
  await wrapper.get('input[aria-label="Nome do dispositivo ESP32"]').setValue('Sensor revisado')
  expect((wrapper.get('input[aria-label="Nome do ambiente Câmara 1"]').element as HTMLInputElement).value).toBe('Câmara revisada')
  await wrapper.findAll('.edit-form')[0]!.trigger('submit')
  await flushPromises()
  expect(updateEnvironment).toHaveBeenCalledWith('token-1', 'env-1', 'Câmara revisada')
  expect(updateDevice).not.toHaveBeenCalled()
  wrapper.unmount()
})
