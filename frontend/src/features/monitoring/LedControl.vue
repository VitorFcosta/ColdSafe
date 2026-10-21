<script setup lang="ts">
import { canWrite, sessionRole } from '../account/session'
import type { ActuatorCommand } from './actuators'
import { actuatorLabel, type ActuatorPhase } from './use-actuators'

defineProps<{ led: ActuatorCommand | null; phase: ActuatorPhase; submitting: boolean; error: string }>()
defineEmits<{ toggle: []; refresh: [] }>()
</script>

<template>
  <div class="led-control">
    <p v-if="!canWrite" role="status">{{ sessionRole === 'viewer' ? 'Modo visualizador: você pode consultar o estado dos atuadores.' : 'Permissões ainda não confirmadas. O controle da luz está indisponível.' }}</p>
    <p v-if="phase === 'loading'" role="status">Consultando estado confirmado…</p>
    <p v-else-if="phase === 'error'" role="alert">Estado dos atuadores indisponível.</p>
    <p aria-live="polite">{{ actuatorLabel(led) }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button type="button" class="refresh" @click="$emit('refresh')">Atualizar estado</button>
      <button type="button" class="toggle" :disabled="!canWrite || phase !== 'ready' || submitting || led?.status === 'pending'" @click="$emit('toggle')">{{ led?.confirmed_state === true ? 'Desligar Luz' : 'Ligar Luz' }}</button>
    </div>
  </div>
</template>

<style scoped>
.led-control { display: grid; gap: var(--cs-space-8); }
.actions { display: flex; flex-wrap: wrap; gap: var(--cs-space-12); }
button { min-height: 44px; padding: var(--cs-space-12) var(--cs-space-16); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); cursor: pointer; }
.refresh { color: var(--cs-color-accent); }
.toggle { color: var(--cs-color-accent-ink); background: var(--cs-color-accent); }
button:disabled { opacity: .5; cursor: default; }
button:focus-visible { outline: 3px solid var(--cs-color-accent); outline-offset: 3px; }
</style>
