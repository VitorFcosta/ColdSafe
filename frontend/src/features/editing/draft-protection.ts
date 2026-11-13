import { onScopeDispose, shallowRef, watch, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { sessionRole, sessionToken } from '../account/session'

type DraftOptions = Readonly<{ dirty: Readonly<Ref<boolean>>; label: string | Readonly<Ref<string>>; discard: () => void }>
export type DraftHandle = DraftOptions & { request: (action: () => void | Promise<void>) => Promise<boolean> }
const drafts = shallowRef<readonly DraftHandle[]>([])
export const draftPrompt = shallowRef<{ labels: readonly string[] } | null>(null)
let pending: { handles: readonly DraftHandle[]; finish: (discard: boolean) => void } | null = null
let identityRevision = 0

export function resolveDraftPrompt(discard: boolean) {
  const decision = pending
  if (!decision) return
  pending = null
  draftPrompt.value = null
  if (discard) decision.handles.forEach((handle) => handle.discard())
  decision.finish(discard)
}

async function confirmDrafts(handles: readonly DraftHandle[], supersede = false): Promise<boolean> {
  if (pending) {
    if (!supersede) return false
    resolveDraftPrompt(false)
  }
  const modified = handles.filter((handle) => handle.dirty.value)
  if (!modified.length) return true
  return new Promise((finish) => {
    pending = { handles: modified, finish }
    draftPrompt.value = { labels: modified.map((handle) => typeof handle.label === 'string' ? handle.label : handle.label.value) }
  })
}

export async function requestDraftTransition(action: () => void | Promise<void>, handles = drafts.value): Promise<boolean> {
  const revision = identityRevision
  if (!await confirmDrafts(handles) || revision !== identityRevision || handles.some((handle) => !drafts.value.includes(handle))) return false
  await action()
  return true
}

export function useDraftProtection(options: DraftOptions): DraftHandle {
  const handle: DraftHandle = { ...options, request: (action) => requestDraftTransition(action, [handle]) }
  drafts.value = [...drafts.value, handle]
  watch([sessionToken, sessionRole], () => {
    identityRevision += 1
    resolveDraftPrompt(false)
    options.discard()
  }, { flush: 'sync' })
  watch(options.dirty, (dirty) => {
    if (!dirty && pending?.handles.includes(handle)) resolveDraftPrompt(false)
  }, { flush: 'sync' })
  onScopeDispose(() => {
    if (pending?.handles.includes(handle)) resolveDraftPrompt(false)
    drafts.value = drafts.value.filter((draft) => draft !== handle)
  })
  return handle
}

export function installDraftProtection(router: Router) {
  const removeGuard = router.beforeEach((to) => {
    if (!sessionToken.value || to.name === 'login') return true
    return confirmDrafts(drafts.value, true)
  })
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (!drafts.value.some((draft) => draft.dirty.value)) return
    event.preventDefault()
    event.returnValue = 'true'
  }
  const stopUnload = watch(() => drafts.value.some((draft) => draft.dirty.value), (dirty) => {
    if (dirty) window.addEventListener('beforeunload', beforeUnload)
    else window.removeEventListener('beforeunload', beforeUnload)
  }, { immediate: true, flush: 'sync' })
  return () => { removeGuard(); stopUnload(); window.removeEventListener('beforeunload', beforeUnload) }
}
