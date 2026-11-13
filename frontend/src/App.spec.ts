// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, onMounted } from 'vue'
import App from './App.vue'
import { clearSession, refreshSessionIdentity, sessionIdentityState, sessionToken, setSession } from './features/account/session'

const mountedPrivate = vi.fn()
const PrivatePage = defineComponent({ setup() { onMounted(mountedPrivate) }, template: '<main><h1 tabindex="-1">Conteúdo privado</h1></main>' })
const fetcher = vi.fn()
let wrapper: ReturnType<typeof mount> | undefined
const response = (role = 'viewer') => ({ ok: true, status: 200, json: async () => ({ success: true, data: { user_id: 'owner', email: 'owner@example.com', role } }) })
async function start(path = '/dashboard') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<main><h1>Apresentação pública</h1></main>' } },
    { path: '/login', name: 'login', component: { template: '<main><h1>Entrar</h1></main>' } },
    { path: '/dashboard', name: 'dashboard', component: PrivatePage, meta: { requiresAuth: true, contentId: 'private-title' } },
    { path: '/training', name: 'training', component: PrivatePage, meta: { requiresAuth: true, requiresAdmin: true } },
  ] })
  await router.push(path)
  wrapper = mount(App, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return router
}
beforeEach(() => { clearSession(); mountedPrivate.mockClear(); fetcher.mockReset(); vi.stubGlobal('fetch', fetcher) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; clearSession(); vi.unstubAllGlobals() })

it('não monta conteúdo enquanto confirma; erro permite retry sem reenviar login', async () => {
  let finish!: (value: unknown) => void
  fetcher.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  setSession('token-a', '2099-01-01T00:00:00Z')
  await start()
  expect(wrapper!.text()).toContain('Verificando identidade')
  expect(mountedPrivate).not.toHaveBeenCalled()
  finish({ ok: false, status: 503, json: async () => ({ success: false }) })
  await flushPromises()
  expect(wrapper!.text()).toContain('Não foi possível verificar a identidade')
  expect(mountedPrivate).not.toHaveBeenCalled()
  fetcher.mockResolvedValue(response())
  await wrapper!.get('[data-testid="retry-identity"]').trigger('click')
  await flushPromises()
  expect(mountedPrivate).toHaveBeenCalledOnce()
  expect(fetcher.mock.calls.every(([url]) => String(url).endsWith('/auth/me'))).toBe(true)
})
it.each(['viewer', 'operator', 'admin'])('URL administrativa preservada e controlada para %s', async (role) => {
  fetcher.mockResolvedValue(response(role))
  setSession(`token-${role}`, '2099-01-01T00:00:00Z')
  const router = await start('/training?job=job-1&dataset=dataset-1')
  expect(router.currentRoute.value.fullPath).toBe('/training?job=job-1&dataset=dataset-1')
  if (role === 'admin') expect(mountedPrivate).toHaveBeenCalledOnce()
  else { expect(wrapper!.text()).toContain('Acesso restrito'); expect(mountedPrivate).not.toHaveBeenCalled() }
})
it('nova conta desmonta dados anteriores antes da verificação e 401 anterior não vence nova sessão', async () => {
  fetcher.mockResolvedValue(response('admin'))
  setSession('token-a', '2099-01-01T00:00:00Z')
  await start('/training')
  expect(wrapper!.text()).toContain('Conteúdo privado')
  let finish!: (value: unknown) => void
  fetcher.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  setSession('token-b', '2099-01-01T00:00:00Z')
  await flushPromises()
  expect(wrapper!.text()).not.toContain('Conteúdo privado')
  setSession('token-c', '2099-01-01T00:00:00Z')
  fetcher.mockResolvedValue(response('viewer'))
  await refreshSessionIdentity()
  finish({ ok: false, status: 401 })
  await flushPromises()
  expect(sessionToken.value).toBe('token-c')
  expect(wrapper!.text()).toContain('Acesso restrito')
})
it('rota desconhecida tem recuperação sem montar conteúdo privado', async () => {
  await start('/nao-existe?origem=externa')
  expect(wrapper!.text()).toContain('Página não encontrada')
  expect(mountedPrivate).not.toHaveBeenCalled()
})
it('sessão criada no login chega ao gate de identidade sem novo POST de credenciais', async () => {
  let fail!: (reason: Error) => void
  const router = await start('/login?redirect=/training%3Fjob%3Djob-1')
  fetcher.mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject }))
  setSession('token-login', '2099-01-01T00:00:00Z')
  await flushPromises()
  fail(new Error('offline'))
  await flushPromises()
  expect(router.currentRoute.value.fullPath).toBe('/training?job=job-1')
  expect(sessionIdentityState.value).toBe('error')
  expect(wrapper!.text()).toContain('Não foi possível verificar a identidade')
})


it('reestabelecer token igual exige nova confirmação e revogação desmonta página administrativa', async () => {
  fetcher.mockResolvedValue(response('admin'))
  setSession('token-a', '2099-01-01T00:00:00Z')
  await start('/training')
  expect(wrapper!.text()).toContain('Conteúdo privado')
  let finish!: (value: unknown) => void
  fetcher.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  setSession('token-a', '2099-01-01T00:00:00Z')
  await flushPromises()
  expect(wrapper!.text()).toContain('Verificando identidade')
  expect(wrapper!.text()).not.toContain('Conteúdo privado')
  finish(response('viewer')); await flushPromises()
  expect(wrapper!.text()).toContain('Acesso restrito')
  expect(wrapper!.text()).not.toContain('Conteúdo privado')
})
