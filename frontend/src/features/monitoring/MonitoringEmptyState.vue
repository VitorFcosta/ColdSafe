<script setup lang="ts">
import { canWrite } from '../account/session'

defineProps<{ missing: 'environment' | 'device' }>()
</script>

<template>
  <p role="status">
    {{ missing === 'environment' ? 'Nenhum ambiente disponível para sua conta.' : 'Nenhum dispositivo ativo neste ambiente.' }}
    <RouterLink v-if="canWrite" to="/manage" class="underline">Abrir Ambientes e dispositivos</RouterLink>
    <template v-else>Fale com um operador ou administrador para verificar a configuração.</template>
  </p>
</template>
