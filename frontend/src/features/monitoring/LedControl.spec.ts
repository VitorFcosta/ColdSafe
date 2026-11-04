// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, expect, it } from 'vitest'
import { sessionRole, sessionToken } from '../account/session'
import type { ActuatorCommand } from './actuators'
import LedControl from './LedControl.vue'

const command: ActuatorCommand = { schema_version: 2, command_id: 'command', device_id: 'device', actuator: 'led', desired_state: true, confirmed_state: null, status: 'pending' }
afterEach(() => { sessionRole.value = null; sessionToken.value = null })

it('separa envio, ACK e observação antiga, sem inferir observação a partir do comando', async () => {
  sessionToken.value = 'token'; sessionRole.value = 'operator'
  const wrapper = mount(LedControl, { props: { led: command, phase: 'ready', submitting: true, error: '',
    observation: { state: false, receivedAt: '2026-10-30T12:00:00Z', ageSeconds: 45 } } })
  expect(wrapper.get('[aria-label="Pedido do LED"]').text()).toContain('Enviando')
  expect(wrapper.get('[aria-label="Observação do LED"]').text()).toContain('Desligado')
  expect(wrapper.get('[aria-label="Observação do LED"]').text()).toContain('Há 45 s')
  expect(wrapper.get('[aria-label="Observação do LED"]').text()).toContain('atual não confirmado')
  await wrapper.setProps({ submitting: false, led: { ...command, status: 'confirmed', confirmed_state: true } })
  expect(wrapper.get('[aria-label="Pedido do LED"]').text()).toContain('Confirmado')
  expect(wrapper.get('[aria-label="Observação do LED"]').text()).toContain('Desligado')
  expect(wrapper.emitted('toggle')).toBeUndefined()
  await wrapper.setProps({ observation: undefined })
  expect(wrapper.get('[aria-label="Observação do LED"]').text()).toContain('Sem leitura observada')
  wrapper.unmount()
})

it('permite atualizar estado no modo visualizador, mas bloqueia envio e conserva ACK pendente', async () => {
  sessionToken.value = 'token'; sessionRole.value = 'viewer'
  const wrapper = mount(LedControl, { props: { led: command, phase: 'ready', submitting: false, error: '' } })
  expect(wrapper.text()).toContain('Modo visualizador')
  expect(wrapper.text()).toContain('Aguardando confirmação')
  expect(wrapper.get('.toggle').attributes('disabled')).toBeDefined()
  await wrapper.get('.toggle').trigger('click')
  expect(wrapper.emitted('toggle')).toBeUndefined()
  await wrapper.get('.refresh').trigger('click')
  expect(wrapper.emitted('refresh')).toHaveLength(1)
  wrapper.unmount()
})

it('operador vê falha, consulta e confirmação sem antecipar estado observado', async () => {
  sessionToken.value = 'token'; sessionRole.value = 'operator'
  const wrapper = mount(LedControl, { props: { led: null, phase: 'loading', submitting: false, error: '' } })
  expect(wrapper.text()).toContain('Consultando estado confirmado')
  expect(wrapper.get('.toggle').attributes('disabled')).toBeDefined()
  await wrapper.setProps({ phase: 'error', error: 'Falha de envio' })
  expect(wrapper.text()).toContain('Estado dos atuadores indisponível')
  expect(wrapper.text()).toContain('Falha de envio')
  await wrapper.setProps({ phase: 'ready', error: '', led: { ...command, status: 'confirmed', confirmed_state: true } })
  expect(wrapper.get('.toggle').text()).toBe('Desligar Luz')
  await wrapper.get('.toggle').trigger('click')
  expect(wrapper.emitted('toggle')).toHaveLength(1)
  await wrapper.setProps({ submitting: true })
  expect(wrapper.get('.toggle').attributes('disabled')).toBeDefined()
  sessionRole.value = null
  expect(wrapper.get('.toggle').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})
