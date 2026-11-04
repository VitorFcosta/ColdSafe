<script setup lang="ts">
import { computed, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { isIdentityVerified, refreshSessionIdentity, sessionIdentityError, sessionIdentityState, sessionRole, sessionToken } from './features/account/session'
import AuthenticatedShell from './features/navigation/AuthenticatedShell.vue'
import { focusPageHeading } from './features/navigation/navigation'
import { safeInternalRedirect } from './router/redirect'
import DraftDiscardDialog from './features/editing/DraftDiscardDialog.vue'

const route = useRoute(), router = useRouter()
const protectedRoute = computed(() => route.meta.requiresAuth === true)
const knownRoute = computed(() => route.matched.length > 0)
const allowed = computed(() => isIdentityVerified.value && (!route.meta.requiresAdmin || sessionRole.value === 'admin'))
const contentId = computed(() => String(route.meta.contentId ?? 'page-title'))

function verifyIdentity() { void refreshSessionIdentity().catch(() => { /* Estado recuperável pertence à sessão. */ }) }
watch([sessionToken, sessionIdentityState], ([token, state]) => { if (token && !isIdentityVerified.value && state === 'pending') verifyIdentity() }, { immediate: true })
watch([sessionToken, () => route.fullPath], ([token]) => {
  if (token && route.name === 'login') void router.replace(safeInternalRedirect(route.query.redirect))
  else if (!token && protectedRoute.value) void router.replace({ name: 'login', query: { redirect: route.fullPath } })
}, { immediate: true })
watch([isIdentityVerified, allowed, () => route.name], () => { if (protectedRoute.value) void focusPageHeading() }, { flush: 'post' })
</script>

<template>
  <DraftDiscardDialog />
  <AuthenticatedShell v-if="protectedRoute && sessionToken" :key="sessionToken">
    <RouterView v-if="allowed" :key="sessionToken" />
    <main v-else class="access-state cs-controls" :aria-busy="sessionIdentityState === 'pending'">
      <template v-if="!isIdentityVerified">
        <h1 :id="contentId" tabindex="-1">{{ sessionIdentityState === 'error' ? 'Não foi possível verificar a identidade' : 'Verificando identidade' }}</h1>
        <p role="status">{{ sessionIdentityState === 'error' ? sessionIdentityError : 'Confirmando as permissões da sua conta. O conteúdo privado ficará disponível após a verificação.' }}</p>
        <button v-if="sessionIdentityState === 'error'" data-testid="retry-identity" type="button" @click="verifyIdentity">Verificar novamente</button>
      </template>
      <template v-else><h1 :id="contentId" tabindex="-1">Acesso restrito</h1><p>Esta área está disponível apenas para administradores. Sua conta pode acessar as demais áreas permitidas.</p><RouterLink to="/dashboard">Voltar ao Monitoramento</RouterLink></template>
    </main>
  </AuthenticatedShell>
  <main v-else-if="!knownRoute" class="missing-page cs-controls">
    <h1 id="page-title" tabindex="-1">Página não encontrada</h1><p>O endereço não corresponde a uma página do ColdSafe.</p><RouterLink :to="sessionToken ? '/dashboard' : '/'">{{ sessionToken ? 'Voltar ao Monitoramento' : 'Ver apresentação do projeto' }}</RouterLink>
  </main>
  <RouterView v-else-if="!protectedRoute" />
</template>

<style scoped>
.access-state { max-width: 720px; line-height: 1.5; }
.access-state h1, .missing-page h1 { margin: 0 0 var(--cs-space-16); font-size: var(--cs-type-32); font-weight: 650; }
.access-state p, .missing-page p { margin-bottom: var(--cs-space-24); }
.access-state a, .missing-page a { color: var(--cs-color-accent); text-decoration: underline; }
.missing-page { padding: var(--cs-space-32); max-width: 720px; margin-inline: auto; }
@media(max-width: 600px) { .access-state h1, .missing-page h1 { font-size: var(--cs-type-24); } .missing-page { padding: var(--cs-space-16); } }
</style>
