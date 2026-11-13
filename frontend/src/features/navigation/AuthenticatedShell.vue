<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { isNavigationFailure, NavigationFailureType, useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { logout, sessionToken } from '../account/session'
import AppNavigation from './AppNavigation.vue'
import { monitoringLocation } from '../monitoring/use-monitoring-context'
import { focusPageHeading } from './navigation'

const route = useRoute(), router = useRouter()
const compact = useMediaQuery('(max-width: 63.999rem)')
const dialog = ref<HTMLDialogElement | null>(null)
const menuButton = ref<HTMLButtonElement | null>(null)
const menuOpen = ref(false)
const signingOut = ref(false), logoutError = ref('')
let navigating = false
const contentId = computed(() => String(route.meta.contentId ?? 'page-title'))

function openMenu() {
  dialog.value?.showModal()
  menuOpen.value = Boolean(dialog.value?.open)
}
function closeMenu(forNavigation = false) {
  if (!dialog.value?.open) return
  navigating = forNavigation
  dialog.value.close()
}
async function menuClosed() {
  menuOpen.value = false
  const destination = navigating
  navigating = false
  await nextTick()
  if (destination) await focusPageHeading()
  // O dialog nativo já devolve foco; repetir aqui poderia roubar o foco da próxima ação.
}
async function signOut() {
  if (signingOut.value) return
  signingOut.value = true
  logoutError.value = ''
  closeMenu()
  try { await logout(); if (!sessionToken.value) await router.replace('/login') }
  catch { logoutError.value = 'Não foi possível encerrar a sessão. Tente novamente.' }
  finally { signingOut.value = false }
}
watch(() => route.fullPath, () => { logoutError.value = '' })
const removeNavigationHook = router.afterEach((_to, _from, failure) => {
  if (!failure || isNavigationFailure(failure, NavigationFailureType.duplicated)) closeMenu(true)
})
watch(compact, async (value) => {
  if (!value && menuOpen.value) { closeMenu(true); menuOpen.value = false; await focusPageHeading() }
})
onBeforeUnmount(() => { removeNavigationHook(); navigating = true; dialog.value?.close() })
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" :href="`#${contentId}`">Ir para o conteúdo</a>
    <header v-if="compact" class="mobile-header cs-controls">
      <RouterLink class="mobile-brand" :to="monitoringLocation('/dashboard')">ColdSafe</RouterLink>
      <button ref="menuButton" type="button" aria-controls="navigation-dialog" :aria-expanded="menuOpen" @click="openMenu">Menu</button>
    </header>
    <aside v-if="!compact" class="sidebar"><AppNavigation :signing-out="signingOut" @sign-out="signOut" /></aside>
    <dialog v-else id="navigation-dialog" ref="dialog" class="navigation-dialog" aria-labelledby="menu-title" @close="menuClosed">
      <div class="dialog-heading cs-controls"><h2 id="menu-title">Menu de navegação</h2><button type="button" autofocus @click="closeMenu()">Fechar menu</button></div>
      <AppNavigation :signing-out="signingOut" @navigate="(external) => { if (external) closeMenu() }" @sign-out="signOut" />
    </dialog>
    <div class="page-content">
      <p v-if="logoutError" class="logout-error" role="alert">{{ logoutError }}</p>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.app-shell { display: grid; grid-template-columns: 256px minmax(0, 1fr); min-height: 100vh; color: var(--cs-color-ink); }
.sidebar { position: sticky; top: 0; align-self: start; height: 100dvh; overflow: auto; padding: var(--cs-space-24); border-right: 1px solid var(--cs-color-line); background: var(--cs-color-surface); }
.page-content { min-width: 0; max-width: 1600px; width: 100%; margin-inline: auto; padding: var(--cs-space-32); }
.page-content :deep(> main) { padding: 0; min-height: auto; }
.mobile-header { display: flex; align-items: center; justify-content: space-between; gap: var(--cs-space-16); padding: var(--cs-space-16); background: var(--cs-color-surface); border-bottom: 1px solid var(--cs-color-line); }
.mobile-brand { color: var(--cs-color-ink); font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; }
.navigation-dialog { width: min(100% - 32px, 360px); max-width: none; max-height: calc(100dvh - 32px); margin: auto; padding: var(--cs-space-24); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); overflow-y: auto; overflow-wrap: anywhere; }
.navigation-dialog::backdrop { background: rgb(8 27 32 / .55); }
.dialog-heading { display: grid; gap: var(--cs-space-12); margin-bottom: var(--cs-space-24); }
.dialog-heading h2 { font-size: var(--cs-type-20); font-weight: 650; }
.logout-error { margin-bottom: var(--cs-space-16); color: var(--cs-color-status-critical); }
@media (max-width: 63.999rem) { .app-shell { display: block; } .page-content { padding: var(--cs-space-16); } }
</style>
