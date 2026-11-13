// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearSession, sessionRole, setSession } from '../account/session'
import { draftPrompt, installDraftProtection, requestDraftTransition, resolveDraftPrompt, useDraftProtection, type DraftHandle } from './draft-protection'

let wrappers: ReturnType<typeof mount>[] = []
let dispose: (() => void) | undefined
beforeEach(() => { setSession('token', '2099-01-01T00:00:00Z'); sessionRole.value = 'operator' })
afterEach(() => { wrappers.forEach((wrapper) => wrapper.unmount()); wrappers = []; dispose?.(); dispose = undefined; clearSession() })
function setup(initial = 'Original') {
  const value = ref(initial), baseline = ref(initial), discard = vi.fn(() => { value.value = baseline.value })
  let guard!: DraftHandle
  wrappers.push(mount(defineComponent({ setup() {
    guard = useDraftProtection({ dirty: computed(() => value.value !== baseline.value), label: 'Limites da Câmara A', discard })
    return () => null
  } })))
  return { value, baseline, discard, guard }
}
it('consulta e valor original não pedem confirmação; edição revertida fica limpa', async () => {
  const { value, guard } = setup()
  const next = vi.fn()
  await guard.request(next)
  value.value = 'Alterado'; value.value = 'Original'
  await guard.request(next)
  expect(next).toHaveBeenCalledTimes(2)
  expect(draftPrompt.value).toBeNull()
})
it('permanecer preserva edição e não executa transição nem descarte', async () => {
  const { value, discard, guard } = setup(); value.value = 'Alterado'
  const next = vi.fn(), result = guard.request(next)
  expect(draftPrompt.value?.labels).toEqual(['Limites da Câmara A'])
  resolveDraftPrompt(false)
  expect(await result).toBe(false)
  expect(value.value).toBe('Alterado')
  expect(discard).not.toHaveBeenCalled(); expect(next).not.toHaveBeenCalled()
})
it('descartar executa uma transição e ignora ações duplicadas durante a decisão', async () => {
  const { value, discard, guard } = setup(); value.value = 'Alterado'
  const next = vi.fn(), result = guard.request(next)
  expect(await guard.request(next)).toBe(false)
  resolveDraftPrompt(true); resolveDraftPrompt(true)
  expect(await result).toBe(true)
  expect(next).toHaveBeenCalledOnce(); expect(discard).toHaveBeenCalledOnce()
  expect(value.value).toBe('Original')
})
it('descarte local não apaga um formulário independente', async () => {
  const first = setup(), second = setup('Outro')
  first.value.value = 'Novo'; second.value.value = 'Segundo'
  const result = requestDraftTransition(() => {}, [first.guard])
  resolveDraftPrompt(true); await result
  expect(first.discard).toHaveBeenCalledOnce()
  expect(second.discard).not.toHaveBeenCalled()
  expect(second.value.value).toBe('Segundo')
})
it('baseline só fica limpa após confirmação; edição não impede aviso nativo antes disso', () => {
  const { value, baseline } = setup(); value.value = 'Alterado'
  const router = createRouter({ history: createMemoryHistory(), routes: [] })
  dispose = installDraftProtection(router)
  const pending = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(pending); expect(pending.defaultPrevented).toBe(true)
  baseline.value = value.value
  const clean = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(clean); expect(clean.defaultPrevented).toBe(false)
})
it.each(['logout', 'conta', 'revogação'] as const)('%s fecha decisão e limpa edição privada antes de continuar', async (reason) => {
  const { value, discard, guard } = setup(); value.value = 'Privado'
  const result = guard.request(vi.fn())
  if (reason === 'logout') clearSession()
  else if (reason === 'conta') setSession('other', '2099-01-01T00:00:00Z')
  else sessionRole.value = 'viewer'
  expect(await result).toBe(false)
  expect(draftPrompt.value).toBeNull()
  expect(value.value).toBe('Original'); expect(discard).toHaveBeenCalled()
})
it('desmontagem cancela decisão sem executar ação atrasada', async () => {
  const { value, guard } = setup(); value.value = 'Alterado'
  const action = vi.fn(), result = guard.request(action)
  wrappers[0]!.unmount()
  resolveDraftPrompt(true)
  expect(await result).toBe(false); expect(action).not.toHaveBeenCalled()
})
it('troca de identidade no await sem rascunho impede uma ação da sessão anterior', async () => {
  const { guard } = setup(), action = vi.fn()
  const transition = guard.request(action)
  setSession('other', '2099-01-01T00:00:00Z')
  expect(await transition).toBe(false)
  expect(action).not.toHaveBeenCalled()
})
it('rascunho removido por revogação cancela o aviso antes da navegação obrigatória', async () => {
  const { value, baseline, guard } = setup(); value.value = 'Alterado'
  const action = vi.fn(), result = guard.request(action)
  baseline.value = value.value
  expect(await result).toBe(false)
  expect(draftPrompt.value).toBeNull(); expect(action).not.toHaveBeenCalled()
})
it('Router decide antes de atualizar rota/query e permite login após limpar sessão', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/manage', component: { template: '<div />' } }, { path: '/insights', component: { template: '<div />' } },
    { path: '/login', name: 'login', component: { template: '<div />' } },
  ] })
  await router.push('/manage'); dispose = installDraftProtection(router)
  const { value } = setup(); value.value = 'Alterado'
  const blocked = router.push('/insights'); await flushPromises()
  expect(router.currentRoute.value.path).toBe('/manage')
  resolveDraftPrompt(false); await blocked
  expect(router.currentRoute.value.path).toBe('/manage')
  const accepted = router.push('/insights'); await flushPromises()
  resolveDraftPrompt(true); await accepted
  expect(router.currentRoute.value.path).toBe('/insights')
  value.value = 'Privado'; const expiring = router.push('/manage'); await flushPromises()
  clearSession(); const login = router.push('/login')
  await Promise.all([expiring, login])
  expect(router.currentRoute.value.path).toBe('/login')
})
it('nova navegação substitui a decisão anterior sem descartar antes de existir destino válido', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/start', component: { template: '<div />' } }, { path: '/first', component: { template: '<div />' } },
    { path: '/latest', component: { template: '<div />' } },
  ] })
  await router.push('/start'); dispose = installDraftProtection(router)
  const { value, discard } = setup(); value.value = 'Alterado'
  const first = router.push('/first'); await flushPromises()
  const latest = router.push('/latest'); await flushPromises()
  expect(value.value).toBe('Alterado'); expect(discard).not.toHaveBeenCalled()
  resolveDraftPrompt(true); await Promise.all([first, latest])
  expect(router.currentRoute.value.path).toBe('/latest')
  expect(discard).toHaveBeenCalledOnce()
})
