<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { isIdentityVerified, sessionRole, sessionUser } from '../account/session'
import { monitoringLocation } from '../monitoring/use-monitoring-context'
import { areas } from './navigation'

defineProps<{ signingOut: boolean }>()
const emit = defineEmits<{ navigate: [external?: boolean]; signOut: [] }>()
const route = useRoute()
const admin = computed(() => isIdentityVerified.value && sessionRole.value === 'admin')
const visibleAreas = computed(() => areas.filter((area) => !area.adminOnly || admin.value))
const roleLabel = computed(() => sessionRole.value === 'admin' ? 'Administrador' : sessionRole.value === 'operator' ? 'Operador' : 'Visualizador')
const diagnosticsEnabled = import.meta.env.VITE_DIAGNOSTICS_ENABLED === 'true'
const rabbitmqUrl = `http://${window.location.hostname}:15672`
</script>

<template>
  <div class="navigation-panel cs-controls">
    <RouterLink class="brand" :to="monitoringLocation('/dashboard')" @click="emit('navigate')">ColdSafe</RouterLink>
    <nav aria-label="Navegação principal">
      <RouterLink v-for="area in visibleAreas" :key="area.key" :to="monitoringLocation(area.to)" :aria-current="route.meta.area === area.key ? 'location' : undefined" @click="emit('navigate')">{{ area.label }}</RouterLink>
    </nav>
    <nav class="utilities" aria-label="Utilitários">
      <RouterLink to="/assistant" @click="emit('navigate')">Assistente</RouterLink>
      <a href="/docs" target="_blank" rel="noopener noreferrer" @click="emit('navigate', true)">Documentação da API <span>(nova aba)</span></a>
      <RouterLink to="/" @click="emit('navigate')">Apresentação do projeto</RouterLink>
      <a v-if="diagnosticsEnabled && isIdentityVerified" :href="rabbitmqUrl" target="_blank" rel="noopener noreferrer" @click="emit('navigate', true)">RabbitMQ local <span>(nova aba)</span></a>
    </nav>
    <div class="account">
      <template v-if="isIdentityVerified && sessionUser"><p>{{ sessionUser.email }}</p><p>{{ roleLabel }}</p></template>
      <p v-else>Identidade {{ sessionRole ? 'em confirmação' : 'não confirmada' }}</p>
      <button type="button" :disabled="signingOut" @click="emit('signOut')">{{ signingOut ? 'Saindo…' : 'Sair' }}</button>
    </div>
  </div>
</template>

<style scoped>
.navigation-panel { display: flex; flex-direction: column; gap: var(--cs-space-32); min-height: 100%; }
.brand { color: var(--cs-color-ink); font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; }
nav { display: grid; gap: var(--cs-space-8); }
nav a { display: block; min-height: var(--cs-control-min-height); padding: var(--cs-space-12); border: 1px solid transparent; border-radius: var(--cs-radius-8); color: var(--cs-color-ink); font-size: var(--cs-type-14); font-weight: 600; line-height: 1.5; text-decoration: none; overflow-wrap: anywhere; }
nav a:hover { background: var(--cs-color-surface-muted); }
nav a[aria-current] { border-color: var(--cs-color-accent); background: var(--cs-color-surface-muted); color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
.utilities { padding-top: var(--cs-space-24); border-top: 1px solid var(--cs-color-line); }
.utilities span { font-weight: 400; }
.account { margin-top: auto; padding-top: var(--cs-space-24); border-top: 1px solid var(--cs-color-line); }
.account p { margin: 0 0 var(--cs-space-8); color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); overflow-wrap: anywhere; }
.account button { width: 100%; }
</style>
