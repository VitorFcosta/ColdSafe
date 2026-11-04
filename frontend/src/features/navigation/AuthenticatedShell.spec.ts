// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { clearSession, refreshSessionIdentity, sessionToken, setSession } from '../account/session'
import AuthenticatedShell from './AuthenticatedShell.vue'
import AreaNavigation from './AreaNavigation.vue'

const fetcher = vi.fn()
let wrapper: ReturnType<typeof mount> | undefined
async function setup(role = 'operator') {
  fetcher.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ success: true, data: { user_id: 'owner', email: 'owner@example.com', role } }) })
  setSession('token-a', '2099-01-01T00:00:00Z')
  await refreshSessionIdentity()
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/login', component: { template: '<main />' } },
    { path: '/dashboard', name: 'dashboard', component: { template: '<main />' }, meta: { area: 'monitoring', contentId: 'dashboard-title' } },
    { path: '/digital-twin', name: 'digital-twin', component: { template: '<main />' }, meta: { area: 'monitoring', contentId: 'digital-twin-title' } },
    { path: '/manage', component: { template: '<main />' }, meta: { area: 'manage' } },
    { path: '/training', component: { template: '<main />' }, meta: { area: 'data', requiresAdmin: true } },
  ] })
  await router.push('/dashboard')
  wrapper = mount(AuthenticatedShell, { attachTo: document.body, slots: { default: defineComponent({ components: { AreaNavigation }, template: '<main><h1 id="dashboard-title" tabindex="-1">Página privada</h1><AreaNavigation v-if="[\'dashboard\', \'digital-twin\'].includes($route.name)" /></main>' }) }, global: { plugins: [router] } })
  await flushPromises()
  return router
}
beforeEach(() => { clearSession(); fetcher.mockReset(); vi.stubGlobal('fetch', fetcher) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; clearSession(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })

it('logout com falha mantém sessão, explica sem detalhes internos e permite repetir', async () => {
  await setup()
  fetcher.mockRejectedValueOnce(new Error('private diagnostic')).mockResolvedValueOnce({ ok: true, status: 200 })
  const button = wrapper!.get('button')
  await button.trigger('click'); await flushPromises()
  expect(sessionToken.value).toBe('token-a')
  expect(wrapper!.get('[role="alert"]').text()).toContain('Não foi possível encerrar a sessão')
  expect(wrapper!.text()).not.toContain('private diagnostic')
  await button.trigger('click'); await flushPromises()
  expect(sessionToken.value).toBeNull()
  expect(wrapper!.text()).not.toContain('owner@example.com')
})
it('logout ocupado não duplica pedidos e retorno antigo não apaga a nova conta', async () => {
  await setup()
  let finish!: (value: unknown) => void
  fetcher.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const button = wrapper!.get('button')
  await button.trigger('click')
  expect(button.text()).toBe('Saindo…')
  await button.trigger('click')
  expect(fetcher).toHaveBeenCalledTimes(2) // identidade + logout
  setSession('token-b', '2099-01-01T00:00:00Z')
  finish({ ok: true, status: 200 }); await flushPromises()
  expect(sessionToken.value).toBe('token-b')
})
it.each(['viewer', 'operator', 'admin'])('aplica áreas e links locais ao papel %s', async (role) => {
  const router = await setup(role)
  expect(wrapper!.findAll('nav[aria-label="Navegação principal"] a')).toHaveLength(role === 'admin' ? 4 : 2)
  expect(wrapper!.findAll('nav[aria-label="Navegação da área"] a')).toHaveLength(3)
  expect(wrapper!.get('a.brand').attributes('href')).toBe('/dashboard')
  expect(wrapper!.get('nav[aria-label="Utilitários"] a[target="_blank"]').text()).toContain('nova aba')
  await router.push('/training?job=job-1'); await flushPromises()
  expect(wrapper!.findAll('nav[aria-label="Navegação da área"] a')).toHaveLength(role === 'admin' ? 2 : 0)
})


it('preserva o diagnóstico habilitado para conta confirmada sem conceder área administrativa', async () => {
  vi.stubEnv('VITE_DIAGNOSTICS_ENABLED', 'true')
  await setup('viewer')
  const diagnostics = 'nav[aria-label="Utilitários"] a[href$=":15672"]'
  expect(wrapper!.get(diagnostics).text()).toContain('RabbitMQ local')
  expect(wrapper!.get(diagnostics).attributes('target')).toBe('_blank')
  expect(wrapper!.find('a[href="/laboratory"]').exists()).toBe(false)
  clearSession(); await flushPromises()
  expect(wrapper!.find(diagnostics).exists()).toBe(false)
})

it('deixa a página do gêmeo posicionar uma única navegação após seu contexto', async () => {
  const router = await setup()
  await router.push('/digital-twin'); await flushPromises()
  expect(wrapper!.findAll('nav[aria-label="Navegação da área"]')).toHaveLength(1)
  expect(wrapper!.find('main nav').exists()).toBe(true)
})
