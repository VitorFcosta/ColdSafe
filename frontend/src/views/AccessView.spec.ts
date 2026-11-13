// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { login, register } from '../features/account/session'
import AccessView from './AccessView.vue'

const push = vi.fn()
const query = vi.hoisted(() => ({ redirect: undefined as string | undefined }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ query }) }))
vi.mock('../features/account/session', () => ({ login: vi.fn(), register: vi.fn() }))

beforeEach(() => { vi.clearAllMocks(); query.redirect = undefined })

it('cadastra e entra, exibindo erro de senha curta antes de enviar', async () => {
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('.mode-switch').trigger('click')
  await wrapper.get('#email').setValue('user@example.com')
  await wrapper.get('#password').setValue('short')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('[role="alert"]').text()).toContain('8 caracteres')
  expect(wrapper.get('#password').attributes('aria-describedby')).toBe('access-error')
  expect(wrapper.get('#password').attributes('aria-invalid')).toBe('true')
  expect(wrapper.get('form').attributes('aria-describedby')).toBe('access-error')
  expect(wrapper.get('[role="alert"]').attributes('id')).toBe('access-error')
  expect(register).not.toHaveBeenCalled()
  await wrapper.get('#password').setValue('validpassword')
  expect(wrapper.get('#password').attributes('aria-invalid')).toBeUndefined()
  expect(wrapper.get('#password').attributes('aria-describedby')).toBe('password-hint')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(register).toHaveBeenCalledWith('user@example.com', 'validpassword')
  expect(login).toHaveBeenCalledWith('user@example.com', 'validpassword')
  expect(push).toHaveBeenCalledWith('/dashboard')
})


it('identifica envio ocupado e impede pedidos duplicados', async () => {
  let finish!: () => void
  vi.mocked(login).mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve }))
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('#email').setValue('user@example.com')
  await wrapper.get('#password').setValue('validpassword')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('form').attributes('aria-busy')).toBe('true')
  expect(wrapper.get('button[type="submit"]').text()).toBe('Entrando…')
  expect(wrapper.get('#email').attributes('disabled')).toBeDefined()
  expect(wrapper.get('.mode-switch').attributes('disabled')).toBeDefined()
  await wrapper.get('form').trigger('submit')
  expect(login).toHaveBeenCalledOnce()
  finish()
  await flushPromises()
  expect(wrapper.get('form').attributes('aria-busy')).toBe('false')
  wrapper.unmount()
})


it('preserva destino e parâmetros quando o App muda a rota durante a confirmação do login', async () => {
  query.redirect = '/training?job=job-1&dataset=dataset-1'
  vi.mocked(login).mockImplementationOnce(async () => { query.redirect = undefined })
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('#email').setValue('user@example.com')
  await wrapper.get('#password').setValue('validpassword')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(push).toHaveBeenCalledWith('/training?job=job-1&dataset=dataset-1')
  wrapper.unmount()
})

it('mantém somente as credenciais, autocomplete por modo e retorno explícito', async () => {
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  expect(wrapper.findAll('input')).toHaveLength(2)
  expect(wrapper.get('#email').attributes()).toMatchObject({ maxlength: '254', autocomplete: 'username', name: 'email' })
  expect(wrapper.get('#password').attributes()).toMatchObject({ maxlength: '128', autocomplete: 'current-password', name: 'password' })
  expect(wrapper.get('router-link-stub').attributes('to')).toBe('/')
  await wrapper.get('.mode-switch').trigger('click')
  expect(wrapper.get('#password').attributes()).toMatchObject({ minlength: '8', autocomplete: 'new-password' })
  expect(wrapper.get('#password-hint').text()).toBe('Use ao menos 8 caracteres.')
  expect(wrapper.get('summary').text()).toBe('Sobre o limite da senha')
  expect(wrapper.get('details').text()).toContain('72 bytes')
  wrapper.unmount()
})

it.each(['https://evil.invalid', '//evil.invalid'])('recusa destino externo %s', async (redirect) => {
  query.redirect = redirect
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('#email').setValue('user@example.invalid')
  await wrapper.get('#password').setValue('password123')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(push).toHaveBeenCalledWith('/dashboard')
  wrapper.unmount()
})

it('conserva credenciais e associa falha ao formulário para corrigir e reenviar', async () => {
  vi.mocked(login).mockRejectedValueOnce(new Error('Email ou senha inválidos.'))
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('#email').setValue('user@example.invalid')
  await wrapper.get('#password').setValue('password123')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get<HTMLInputElement>('#email').element.value).toBe('user@example.invalid')
  expect(wrapper.get<HTMLInputElement>('#password').element.value).toBe('password123')
  expect(wrapper.get('form').attributes('aria-describedby')).toBe('access-error')
  expect(wrapper.get('[role="alert"]').text()).toBe('Email ou senha inválidos.')
  expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  await wrapper.get('.mode-switch').trigger('click')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  wrapper.unmount()
})


it('associa limite UTF-8 ao campo sem enviar cadastro e permite corrigir', async () => {
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('.mode-switch').trigger('click')
  await wrapper.get('#email').setValue('user@example.invalid')
  await wrapper.get('#password').setValue('é'.repeat(37))
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('[role="alert"]').text()).toContain('72 bytes')
  expect(wrapper.get('#password').attributes('aria-invalid')).toBe('true')
  expect(register).not.toHaveBeenCalled()
  await wrapper.get('#password').setValue('é'.repeat(36))
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(register).toHaveBeenCalledWith('user@example.invalid', 'é'.repeat(36))
  wrapper.unmount()
})


it('foca e descreve o primeiro campo inválido; o segundo não rouba foco', async () => {
  const wrapper = mount(AccessView, { attachTo: document.body, global: { stubs: ['RouterLink'] } })
  // happy-dom não resolve :invalid; o estado nativo é coberto pelo E2E.
  const firstInvalid = vi.spyOn(wrapper.get('form').element, 'querySelector').mockReturnValue(wrapper.get('#email').element)
  await wrapper.get('#email').trigger('invalid')
  await wrapper.get('#password').trigger('invalid')
  expect(document.activeElement).toBe(wrapper.get('#email').element)
  expect(wrapper.get('#email').attributes('aria-invalid')).toBe('true')
  expect(wrapper.get('#email').attributes('aria-describedby')).toBe('access-error')
  expect(wrapper.get('[role="alert"]').text()).toBe('Informe um email válido.')
  await wrapper.get('#email').setValue('user@example.invalid')
  firstInvalid.mockReturnValue(wrapper.get('#password').element)
  await wrapper.get('#password').trigger('invalid')
  expect(document.activeElement).toBe(wrapper.get('#password').element)
  expect(wrapper.get('#password').attributes('aria-describedby')).toBe('access-error')
  expect(wrapper.get('[role="alert"]').text()).toBe('Informe sua senha.')
  wrapper.unmount()
})

it('não associa erro de email à senha curta no cadastro', async () => {
  const wrapper = mount(AccessView, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('.mode-switch').trigger('click')
  const firstInvalid = vi.spyOn(wrapper.get('form').element, 'querySelector').mockReturnValue(wrapper.get('#email').element)
  await wrapper.get('#email').trigger('invalid')
  expect(wrapper.get('#email').attributes('aria-invalid')).toBe('true')
  expect(wrapper.get('#password').attributes('aria-invalid')).toBeUndefined()
  expect(wrapper.get('#password').attributes('aria-describedby')).toBe('password-hint')
  firstInvalid.mockRestore()
  wrapper.unmount()
})
