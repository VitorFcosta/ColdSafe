<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { isIdentityVerified, sessionRole } from '../account/session'
import { monitoringLocation } from '../monitoring/use-monitoring-context'
import { areas } from './navigation'

const route = useRoute()
const links = computed(() => {
  const area = areas.find((item) => item.key === route.meta?.area)
  return area?.adminOnly && sessionRole.value !== 'admin' ? [] : area?.links ?? []
})
</script>

<template>
  <nav v-if="isIdentityVerified && links.length" class="local-navigation" aria-label="Navegação da área">
    <RouterLink v-for="link in links" :key="link.to" :to="route.matched.at(-1)?.path === link.to ? route.fullPath : monitoringLocation(link.to)">{{ link.label }}</RouterLink>
  </nav>
</template>

<style scoped>
.local-navigation { display: flex; flex-wrap: wrap; gap: var(--cs-space-4) var(--cs-space-8); margin-top: var(--cs-space-12); border-bottom: 1px solid var(--cs-color-line); }
a { display: flex; align-items: center; min-height: var(--cs-control-min-height); padding: var(--cs-space-8) var(--cs-space-12); border-bottom: 2px solid transparent; color: var(--cs-color-ink); font-size: var(--cs-type-14); text-decoration: none; overflow-wrap: anywhere; }
a[aria-current='page'] { border-color: var(--cs-color-accent); background: var(--cs-color-surface-muted); color: var(--cs-color-accent); font-weight: 650; text-decoration: none; }
a:hover { background: var(--cs-color-surface-muted); }
</style>
