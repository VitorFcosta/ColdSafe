// @vitest-environment happy-dom
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { sessionToken, sessionRole, refreshSessionIdentity } from '../features/account/session'
import { draftPrompt, resolveDraftPrompt } from '../features/editing/draft-protection'
import {
  CatalogAccessError, createDevice, createEnvironment, deactivateDevice, getRules, listDevices, listEnvironments,
  updateDevice, updateEnvironment, updateRules,
} from '../features/account/catalog'
import ManageView from './ManageView.vue'
enableAutoUnmount(afterEach)

vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
vi.mock('../features/account/session', async (original) => ({
  ...await original<typeof import('../features/account/session')>(), refreshSessionIdentity: vi.fn(),
}))
vi.mock('../features/account/catalog', async (original) => ({
  ...await original<typeof import('../features/account/catalog')>(),
  createDevice: vi.fn(), createEnvironment: vi.fn(), deactivateDevice: vi.fn(), getRules: vi.fn(),
  listDevices: vi.fn(), listEnvironments: vi.fn(), updateDevice: vi.fn(), updateEnvironment: vi.fn(), updateRules: vi.fn(),
}))

beforeEach(() => {
  resolveDraftPrompt(false)
  vi.clearAllMocks()
  vi.mocked(refreshSessionIdentity).mockResolvedValue(undefined)
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
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  expect(wrapper.text()).toContain(role === 'viewer' ? 'Modo visualizador' : 'Permissões ainda não confirmadas')
  expect(wrapper.find('[data-test="open-environment-form"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="open-device-form"]').exists()).toBe(false)
  expect(wrapper.find('form').exists()).toBe(false)
  await flushPromises()
  expect(updateRules).not.toHaveBeenCalled()
  expect(createEnvironment).not.toHaveBeenCalled()
  expect(wrapper.get('.item-name').attributes('disabled')).toBeUndefined()
  wrapper.unmount()
})

it('carrega dados, cadastra dispositivo, altera limites e desativa com confirmação', async () => {
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  expect(wrapper.text()).toContain('Câmara 1')
  expect(wrapper.text()).toContain('esp32-1')

  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  await wrapper.get('#device-name').setValue('Novo sensor')
  expect(wrapper.get('#mqtt-id').attributes('aria-describedby')).toBe('mqtt-id-hint')
  expect(wrapper.get('#mqtt-id-hint').text()).toContain('ESP32')
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
  expect(wrapper.get('dialog').text()).toContain('ESP32')
  expect(deactivateDevice).not.toHaveBeenCalled()
  vi.mocked(listDevices).mockResolvedValueOnce([{ id: 'dev-1', environment_id: 'env-1', name: 'ESP32', mqtt_device_id: 'esp32-1', is_active: false }])
  await wrapper.get('[data-test="confirm-deactivation"]').trigger('click'); await flushPromises()
  expect(deactivateDevice).toHaveBeenCalledWith('token-1', 'dev-1')
  expect(wrapper.find('.danger').exists()).toBe(false)
  wrapper.unmount()
})

it('mostra falha de carregamento e impede limites inválidos perto dos campos', async () => {
  vi.mocked(listDevices).mockRejectedValueOnce(new Error('Serviço indisponível.'))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
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
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
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
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
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

it('recusa identificador MQTT inválido e cancelar desativação não envia alterações', async () => {
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()

  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  await wrapper.get('#device-name').setValue('Sensor')
  await wrapper.get('#mqtt-id').setValue('id inválido')
  await wrapper.get('#device-name').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('ID MQTT')
  expect(createDevice).not.toHaveBeenCalled()

  await wrapper.get('.danger').trigger('click')
  await flushPromises()
  await wrapper.get('[data-test="cancel-deactivation"]').trigger('click')
  expect(deactivateDevice).not.toHaveBeenCalled()
  wrapper.unmount()
})

it.each(['devices', 'rules'])('falha de %s não vira vazio nem confirma metade da carga; retry consulta ambos', async (failed) => {
  if (failed === 'devices') vi.mocked(listDevices).mockRejectedValueOnce(new Error('offline'))
  else vi.mocked(getRules).mockRejectedValueOnce(new Error('offline'))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } }); await flushPromises()
  expect(wrapper.text()).not.toContain('Nenhum dispositivo cadastrado')
  expect(wrapper.find('#min-c').exists()).toBe(false)
  await wrapper.get('[data-test="retry-selection"]').trigger('click'); await flushPromises()
  expect(listDevices).toHaveBeenCalledTimes(2); expect(getRules).toHaveBeenCalledTimes(2)
  expect(wrapper.text()).toContain('esp32-1')
})

it.each([true, false])('vazio do viewer não oferece cadastro (sem ambientes: %s)', async (noEnvironments) => {
  sessionRole.value = 'viewer'
  if (noEnvironments) vi.mocked(listEnvironments).mockResolvedValue([])
  else vi.mocked(listDevices).mockResolvedValue([])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } }); await flushPromises()
  expect(wrapper.text()).toContain(noEnvironments ? 'Nenhum ambiente cadastrado' : 'Nenhum dispositivo cadastrado')
  expect(wrapper.text()).not.toContain('Adicione')
  expect(wrapper.text()).not.toContain('Adicionar')
  expect(wrapper.find('form').exists()).toBe(false)
})

it('desativação pendente é invalidada na troca de conta e Escape não envia DELETE', async () => {
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } }); await flushPromises()
  await wrapper.get('.danger').trigger('click'); await flushPromises()
  expect(wrapper.get('dialog').attributes('open')).toBeDefined()
  await wrapper.get('dialog').trigger('cancel'); await flushPromises()
  expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
  expect(deactivateDevice).not.toHaveBeenCalled()
  await wrapper.get('.danger').trigger('click'); await flushPromises()
  sessionToken.value = 'token-2'; await flushPromises()
  expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
  expect(deactivateDevice).not.toHaveBeenCalled()
})

it('nome de 120 caracteres e MQTT de 64 são válidos; limites maiores e nome em branco orientam erro no campo', async () => {
  vi.mocked(createEnvironment).mockResolvedValue({ id:'env-1', name:'a'.repeat(120) })
  const wrapper=mount(ManageView,{attachTo:document.body,global:{stubs:['RouterLink','Teleport']}});await flushPromises()
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue('a'.repeat(120));await wrapper.get('.inline-form').trigger('submit');await flushPromises()
  expect(createEnvironment).toHaveBeenCalledWith('token-1','a'.repeat(120))
  expect(document.activeElement).toBe(wrapper.get('[data-test="open-environment-form"]').element)
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  for(const name of ['a'.repeat(121),'   ']){
    await wrapper.get('#environment-name').setValue(name);await wrapper.get('.inline-form').trigger('submit');await flushPromises()
    expect(wrapper.get('#environment-name').attributes('aria-invalid')).toBe('true')
    expect(document.activeElement).toBe(wrapper.get('#environment-name').element)
  }
  expect(createEnvironment).toHaveBeenCalledTimes(1)
  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  await wrapper.get('#device-name').setValue('Sensor');await wrapper.get('#mqtt-id').setValue('a'.repeat(65))
  await wrapper.get('#device-name').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  expect(wrapper.get('#mqtt-id').attributes('aria-invalid')).toBe('true');expect(createDevice).not.toHaveBeenCalled()
  expect(document.activeElement).toBe(wrapper.get('#mqtt-id').element)
  await wrapper.get('#mqtt-id').setValue('a'.repeat(64));await wrapper.get('#device-name').setValue('   ')
  await wrapper.get('#device-name').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('#device-name').element);expect(createDevice).not.toHaveBeenCalled()
  await wrapper.get('#device-name').setValue('Sensor');await wrapper.get('#device-name').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  expect(createDevice).toHaveBeenCalledWith('token-1','env-1','Sensor','a'.repeat(64))
  expect(document.activeElement).toBe(wrapper.get('[data-test="open-device-form"]').element)
})

it.each([0, 3, -1])('margem %s respeita zero e a metade estrita da faixa', async (margin) => {
  const wrapper=mount(ManageView,{global:{stubs:['RouterLink','Teleport']}});await flushPromises()
  await wrapper.get('#margin-c').setValue(String(margin));await wrapper.get('#margin-c').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  if(margin===0) expect(updateRules).toHaveBeenCalledWith('token-1','env-1',{min_c:2,max_c:8,attention_margin_c:0})
  else {expect(updateRules).not.toHaveBeenCalled();expect(wrapper.find('#margin-c-error').exists()).toBe(true)}
})

it('retry conjunto falho preserva e identifica o rascunho autorizado dos limites', async () => {
  const wrapper=mount(ManageView,{global:{stubs:['RouterLink','Teleport']}});await flushPromises()
  await wrapper.get('#min-c').setValue('3')
  vi.mocked(getRules).mockRejectedValueOnce(new Error('offline'))
  await wrapper.get('.item-name').trigger('click');await flushPromises()
  expect(wrapper.text()).toContain('Rascunho dos limites preservado')
  expect((wrapper.get('#min-c').element as HTMLInputElement).value).toBe('3')
  await wrapper.get('[data-test="retry-selection"]').trigger('click');await flushPromises()
  expect((wrapper.get('#min-c').element as HTMLInputElement).value).toBe('3')
  expect(updateRules).not.toHaveBeenCalled()
})

it('cadastro confirmado seguido de falha na consulta foca recuperação e não repete POST', async () => {
  const wrapper=mount(ManageView,{attachTo:document.body,global:{stubs:['RouterLink','Teleport']}});await flushPromises()
  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  await wrapper.get('#device-name').setValue('Sensor');await wrapper.get('#mqtt-id').setValue('sensor-2')
  vi.mocked(listDevices).mockRejectedValueOnce(new Error('offline'))
  await wrapper.get('#device-name').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  expect(createDevice).toHaveBeenCalledOnce()
  expect(document.activeElement).toBe(wrapper.get('[data-test="retry-selection"]').element)
  await wrapper.get('[data-test="retry-selection"]').trigger('click');await flushPromises()
  expect(createDevice).toHaveBeenCalledOnce()
})

it('prioriza listas e oferece inclusão no estado vazio sem alterar a API ao cancelar', async () => {
  vi.mocked(listEnvironments).mockResolvedValue([])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()

  expect(wrapper.text()).toContain('Nenhum ambiente cadastrado')
  expect(wrapper.find('#environment-name').exists()).toBe(false)
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue('Rascunho')
  await wrapper.get('[data-test="cancel-environment-form"]').trigger('click')
  resolveDraftPrompt(true); await flushPromises()
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
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()

  expect(wrapper.get('#devices-title').text()).toContain(longName)
  expect(wrapper.get('#rules-title').text()).toContain(longName)
  expect(wrapper.find('.danger').exists()).toBe(false)
  expect(wrapper.get('.small-action').attributes('aria-label')).toBe(`Renomear ambiente ${longName}`)
  await wrapper.findAll('.item-name')[1]!.trigger('click')
  await flushPromises()
  expect(wrapper.get('#devices-title').text()).toContain('Estoque')
  expect(wrapper.text()).toContain('Nenhum dispositivo cadastrado')
  expect(wrapper.find('#device-name').exists()).toBe(false)
  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  expect(wrapper.text()).toContain('Adicionar dispositivo em Estoque')
  await wrapper.get('#device-name').setValue('Rascunho')
  await wrapper.get('[data-test="cancel-device-form"]').trigger('click')
  resolveDraftPrompt(true); await flushPromises()
  expect(createDevice).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('cancela edições de ambiente e dispositivo sem enviar alterações', async () => {
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()

  await wrapper.get('.small-action').trigger('click')
  await wrapper.get('input[aria-label="Nome do ambiente Câmara 1"]').setValue('Nome temporário')
  await wrapper.get('button[aria-label="Cancelar edição do ambiente Câmara 1"]').trigger('click')
  resolveDraftPrompt(true); await flushPromises()
  expect(wrapper.get('.item-name').text()).toBe('Câmara 1')
  expect(updateEnvironment).not.toHaveBeenCalled()

  await wrapper.get('button[aria-label="Editar dispositivo ESP32"]').trigger('click')
  await wrapper.get('input[aria-label="Nome do dispositivo ESP32"]').setValue('Nome temporário')
  await wrapper.get('button[aria-label="Cancelar edição do dispositivo ESP32"]').trigger('click')
  resolveDraftPrompt(true); await flushPromises()
  expect(wrapper.get('.device-info strong').text()).toBe('ESP32')
  expect(updateDevice).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('mantém rascunhos de ambiente e dispositivo independentes', async () => {
  vi.mocked(updateEnvironment).mockResolvedValue({ id: 'env-1', name: 'Câmara revisada' })
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
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


it('identifica limites sendo salvos e não duplica a atualização', async () => {
  let finish!: (value: { min_c: number; max_c: number; attention_margin_c: number }) => void
  vi.mocked(updateRules).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  const form = wrapper.get('#min-c').element.closest('form')!
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(form.getAttribute('aria-busy')).toBe('true')
  expect(form.querySelector('button[type="submit"]')?.textContent).toBe('Salvando…')
  expect(wrapper.get('#min-c').attributes('disabled')).toBeDefined()
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  expect(updateRules).toHaveBeenCalledOnce()
  finish({ min_c: 2, max_c: 8, attention_margin_c: 0.5 })
  await flushPromises()
  expect(form.getAttribute('aria-busy')).toBe('false')
  wrapper.unmount()
})

it('resolve permanecer ou descartar limites antes de trocar o ambiente', async () => {
  vi.mocked(listEnvironments).mockResolvedValue([{ id: 'env-1', name: 'Câmara 1' }, { id: 'env-2', name: 'Câmara 2' }])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('#min-c').setValue('3')
  await wrapper.findAll('.item-name')[1]!.trigger('click')
  await flushPromises()
  expect(draftPrompt.value).not.toBeNull()
  expect(wrapper.findAll('.item-name')[0]!.attributes('aria-pressed')).toBe('true')
  resolveDraftPrompt(false); await flushPromises()
  expect((wrapper.get('#min-c').element as HTMLInputElement).value).toBe('3')
  await wrapper.findAll('.item-name')[1]!.trigger('click')
  resolveDraftPrompt(true); await flushPromises()
  expect(wrapper.findAll('.item-name')[1]!.attributes('aria-pressed')).toBe('true')
  expect((wrapper.get('#min-c').element as HTMLInputElement).value).toBe('2')
  expect(listDevices).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

it('voltar ao valor original não exige confirmação e selecionar não é editar', async () => {
  vi.mocked(listEnvironments).mockResolvedValue([{ id: 'env-1', name: 'Câmara 1' }, { id: 'env-2', name: 'Câmara 2' }])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('#min-c').setValue('3')
  await wrapper.get('#min-c').setValue('2')
  await wrapper.findAll('.item-name')[1]!.trigger('click'); await flushPromises()
  expect(draftPrompt.value).toBeNull()
  expect(wrapper.findAll('.item-name')[1]!.attributes('aria-pressed')).toBe('true')
  wrapper.unmount()
})

it('cancelar inclusão descarta apenas o rascunho escolhido', async () => {
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue('Novo ambiente')
  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  await wrapper.get('#device-name').setValue('Novo sensor')
  await wrapper.get('[data-test="cancel-environment-form"]').trigger('click')
  expect(draftPrompt.value).not.toBeNull()
  resolveDraftPrompt(false); await flushPromises()
  expect((wrapper.get('#environment-name').element as HTMLInputElement).value).toBe('Novo ambiente')
  await wrapper.get('[data-test="cancel-environment-form"]').trigger('click')
  resolveDraftPrompt(true); await flushPromises()
  expect(wrapper.find('#environment-name').exists()).toBe(false)
  expect((wrapper.get('#device-name').element as HTMLInputElement).value).toBe('Novo sensor')
  wrapper.unmount()
})

it('salvar nome mantém rascunhos independentes de limites e dispositivo', async () => {
  vi.mocked(updateEnvironment).mockResolvedValue({ id: 'env-1', name: 'Câmara revisada' })
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('#min-c').setValue('3')
  await wrapper.get('.small-action').trigger('click')
  await wrapper.get('input[aria-label="Nome do ambiente Câmara 1"]').setValue('Câmara revisada')
  await wrapper.get('button[aria-label="Editar dispositivo ESP32"]').trigger('click')
  await wrapper.get('input[aria-label="Nome do dispositivo ESP32"]').setValue('Sensor revisado')
  await wrapper.findAll('.edit-form')[0]!.trigger('submit'); await flushPromises()
  expect((wrapper.get('#min-c').element as HTMLInputElement).value).toBe('3')
  expect((wrapper.get('input[aria-label="Nome do dispositivo ESP32"]').element as HTMLInputElement).value).toBe('Sensor revisado')
  expect(draftPrompt.value).toBeNull()
  wrapper.unmount()
})

it('salvamento confirmado atualiza baseline; erro mantém proteção do rascunho', async () => {
  vi.mocked(listEnvironments).mockResolvedValue([{ id: 'env-1', name: 'Câmara 1' }, { id: 'env-2', name: 'Câmara 2' }])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('#min-c').setValue('3')
  vi.mocked(updateRules).mockRejectedValueOnce(new Error('offline'))
  await wrapper.get('#min-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  await wrapper.findAll('.item-name')[1]!.trigger('click')
  expect(draftPrompt.value).not.toBeNull()
  resolveDraftPrompt(false); await flushPromises()
  await wrapper.get('#min-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  await wrapper.findAll('.item-name')[1]!.trigger('click'); await flushPromises()
  expect(draftPrompt.value).toBeNull()
  expect(wrapper.findAll('.item-name')[1]!.attributes('aria-pressed')).toBe('true')
  wrapper.unmount()
})

it('salvamento atrasado não muda limites nem confirma sucesso em outra conta', async () => {
  let finish!: (value: { min_c: number; max_c: number; attention_margin_c: number }) => void
  vi.mocked(updateRules).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('#min-c').setValue('3')
  await wrapper.get('#min-c').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  sessionToken.value = 'token-2'; await flushPromises()
  finish({ min_c: 5, max_c: 9, attention_margin_c: 1 }); await flushPromises()
  expect((wrapper.get('#min-c').element as HTMLInputElement).value).toBe('2')
  expect(wrapper.text()).not.toContain('salvos.')
  wrapper.unmount()
})

it('perda de escrita limpa rascunho sem aguardar aviso e montagem antiga ignora POST tardio', async () => {
  let finish!: (value: { id: string; name: string }) => void
  vi.mocked(createEnvironment).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue('Privado')
  sessionRole.value = 'viewer'; await flushPromises()
  expect(wrapper.find('#environment-name').exists()).toBe(false)
  expect(draftPrompt.value).toBeNull()
  sessionRole.value = 'operator'; await flushPromises()
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue('Novo')
  await wrapper.get('.inline-form').trigger('submit'); await flushPromises()
  const loads = vi.mocked(listEnvironments).mock.calls.length
  wrapper.unmount()
  finish({ id: 'env-2', name: 'Novo' }); await flushPromises()
  expect(listEnvironments).toHaveBeenCalledTimes(loads)
})

it('trocar ambiente descarta dispositivo mas conserva inclusão global de ambiente', async () => {
  vi.mocked(listEnvironments).mockResolvedValue([{ id: 'env-1', name: 'Câmara 1' }, { id: 'env-2', name: 'Câmara 2' }])
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('[data-test="open-environment-form"]').trigger('click')
  await wrapper.get('#environment-name').setValue('Ambiente independente')
  await wrapper.get('[data-test="open-device-form"]').trigger('click')
  await wrapper.get('#device-name').setValue('Sensor da Câmara 1')
  await wrapper.findAll('.item-name')[1]!.trigger('click')
  expect(draftPrompt.value?.labels).toEqual(['Novo dispositivo em Câmara 1'])
  resolveDraftPrompt(true); await flushPromises()
  expect(wrapper.find('#device-name').exists()).toBe(false)
  expect((wrapper.get('#environment-name').element as HTMLInputElement).value).toBe('Ambiente independente')
  expect(wrapper.findAll('.item-name')[1]!.attributes('aria-pressed')).toBe('true')
  wrapper.unmount()
})

it.each([403, 404])('revogação %s limpa dados e fecha aviso sem aguardar descarte', async (status) => {
  vi.mocked(listEnvironments).mockResolvedValue([{ id: 'env-1', name: 'Câmara 1' }, { id: 'env-2', name: 'Câmara 2' }])
  let reject!: (error: Error) => void
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  await wrapper.get('#min-c').setValue('3')
  vi.mocked(getRules).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
  await wrapper.findAll('.item-name')[0]!.trigger('click'); await flushPromises()
  await wrapper.findAll('.item-name')[1]!.trigger('click')
  expect(draftPrompt.value).not.toBeNull()
  reject(new CatalogAccessError(status)); await flushPromises()
  expect(draftPrompt.value).toBeNull()
  expect(wrapper.find('#min-c').exists()).toBe(false)
  expect(wrapper.findAll('.item-name')).toHaveLength(2)
  expect(wrapper.findAll('.item-name').every((item) => item.attributes('aria-pressed') === 'false')).toBe(true)
  expect(wrapper.text()).not.toContain('esp32-1')
  expect(wrapper.text()).toContain('Acesso ao ambiente indisponível')
  expect(refreshSessionIdentity).not.toHaveBeenCalled()
  const deniedCalls = vi.mocked(getRules).mock.calls.length
  await flushPromises()
  expect(getRules).toHaveBeenCalledTimes(deniedCalls)
  await wrapper.findAll('.item-name')[1]!.trigger('click'); await flushPromises()
  expect(wrapper.findAll('.item-name')[1]!.attributes('aria-pressed')).toBe('true')
  expect(wrapper.find('#min-c').exists()).toBe(true)
  expect(refreshSessionIdentity).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('lista de ambientes negada oferece somente retry GET explícito', async () => {
  vi.mocked(listEnvironments).mockRejectedValueOnce(new CatalogAccessError(403))
  const wrapper = mount(ManageView, { global: { stubs: ['RouterLink', 'Teleport'] } })
  await flushPromises()
  expect(wrapper.find('.item-name').exists()).toBe(false)
  expect(listEnvironments).toHaveBeenCalledOnce()
  expect(refreshSessionIdentity).not.toHaveBeenCalled()
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(listEnvironments).toHaveBeenCalledTimes(2)
  expect(wrapper.get('.item-name').text()).toBe('Câmara 1')
  expect(createEnvironment).not.toHaveBeenCalled()
  wrapper.unmount()
})
