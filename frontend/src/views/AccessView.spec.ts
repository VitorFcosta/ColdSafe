// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { login, register } from '../features/account/session'
import AccessView from './AccessView.vue'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ query: {} }) }))
vi.mock('../features/account/session', () => ({ login: vi.fn(), register: vi.fn() }))

beforeEach(() => { vi.clearAllMocks() })

it('cadastra e entra, exibindo erro de senha curta antes de enviar', async () => {
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('.mode-switch').trigger('click')
  await wrapper.get('#email').setValue('user@example.com')
  await wrapper.get('#password').setValue('short')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('[role="alert"]').text()).toContain('8 caracteres')
  expect(register).not.toHaveBeenCalled()
  await wrapper.get('#password').setValue('validpassword')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(register).toHaveBeenCalledWith('user@example.com', 'validpassword')
  expect(login).toHaveBeenCalledWith('user@example.com', 'validpassword')
  expect(push).toHaveBeenCalledWith('/dashboard')
})
