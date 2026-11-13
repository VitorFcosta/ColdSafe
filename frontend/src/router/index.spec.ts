// @vitest-environment happy-dom
import { beforeEach, expect, it } from 'vitest'
import router from './index'
import { clearSession, setSession } from '../features/account/session'
import { areas } from '../features/navigation/navigation'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { resolveDraftPrompt, useDraftProtection } from '../features/editing/draft-protection'

beforeEach(() => clearSession())
it('preserva dez rotas e protege visitante mantendo query e fragmento no destino', async () => {
  expect(router.getRoutes()).toHaveLength(10)
  await router.push('/training?dataset=dataset-1&job=job-1#resultado')
  expect(router.currentRoute.value.name).toBe('login')
  expect(router.currentRoute.value.query.redirect).toBe('/training?dataset=dataset-1&job=job-1#resultado')
})
it('sessão existente usa somente redirecionamento interno e preserva parâmetros', async () => {
  setSession('token', '2099-01-01T00:00:00Z')
  await router.push('/login?redirect=%2Ftraining%3Fjob%3Djob-1')
  expect(router.currentRoute.value.fullPath).toBe('/training?job=job-1')
  await router.push('/login?redirect=https://evil.example')
  expect(router.currentRoute.value.path).toBe('/dashboard')
  expect(document.title).toBe('Visão geral · ColdSafe')
})
it('navegação e guardas usam os mesmos papéis para as áreas administrativas', () => {
  for (const area of areas) for (const link of area.links ?? [area]) {
    expect(Boolean(router.resolve(link.to).meta.requiresAdmin)).toBe(Boolean(area.adminOnly))
  }
  expect(router.resolve('/endereco-desconhecido').matched).toHaveLength(0)
})
it('permanecer conserva título e foco quando a navegação é abortada', async () => {
  setSession('token', '2099-01-01T00:00:00Z')
  await router.push('/manage')
  const wrapper = mount(defineComponent({ setup() {
    useDraftProtection({ dirty: ref(true), label: 'Edição', discard: () => {} })
    return () => null
  } }))
  const title = document.title
  try {
    const next = router.push('/insights'); await flushPromises()
    resolveDraftPrompt(false); await next
    expect(router.currentRoute.value.path).toBe('/manage')
    expect(document.title).toBe(title)
  } finally { wrapper.unmount() }
})
