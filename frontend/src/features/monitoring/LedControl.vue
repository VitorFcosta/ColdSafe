<script setup lang="ts">
import { canWrite, sessionRole } from '../account/session'
import type { ActuatorCommand } from './actuators'
import { actuatorLabel, type ActuatorPhase } from './use-actuators'
import { formatFreshness } from './use-monitoring-summary'
import { formatReadingTime } from './temperature-chart'
import { STALE_AFTER_SECONDS } from './monitoring-state'

defineProps<{ led: ActuatorCommand | null; phase: ActuatorPhase; submitting: boolean; error: string
  observation?: { state: boolean; receivedAt: string; ageSeconds: number | null }
}>()
defineEmits<{ toggle: []; refresh: [] }>()
</script>

<template>
  <div class="led-control">
    <p v-if="!canWrite" role="status">{{ sessionRole === 'viewer' ? 'Modo visualizador: você pode consultar o estado dos atuadores.' : 'Permissões ainda não confirmadas. O controle da luz está indisponível.' }}</p>
    <p v-if="phase === 'loading'" role="status">Consultando estado confirmado…</p>
    <p v-else-if="phase === 'error'" role="alert">Estado dos atuadores indisponível.</p>
    <section aria-label="Observação do LED" class="observation">
      <h4>Estado observado</h4>
      <template v-if="observation">
        <p>Luz observada na última leitura: <strong>{{ observation.state ? 'Ligado' : 'Desligado' }}</strong> · {{ formatFreshness(observation.ageSeconds ?? undefined) }}.</p>
        <p><time :datetime="observation.receivedAt">{{ formatReadingTime(observation.receivedAt) }}</time></p>
        <p v-if="observation.ageSeconds === null || observation.ageSeconds > STALE_AFTER_SECONDS">Estado atual não confirmado; aguarde uma leitura recente.</p>
      </template>
      <p v-else>Sem leitura observada. O ACK não substitui a telemetria.</p>
    </section>
    <section aria-label="Pedido do LED" class="request">
      <h4>Pedido manual</h4>
      <p aria-live="polite">{{ submitting ? 'Enviando pedido…' : led?.status === 'confirmed' ? `Confirmado por ACK · ${actuatorLabel(led)}` : actuatorLabel(led) }}</p>
    </section>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button type="button" class="refresh" @click="$emit('refresh')">Atualizar estado</button>
      <button type="button" class="toggle" :disabled="!canWrite || phase !== 'ready' || submitting || led?.status === 'pending'" @click="$emit('toggle')">{{ led?.confirmed_state === true ? 'Desligar Luz' : 'Ligar Luz' }}</button>
    </div>
  </div>
</template>

<style scoped>
.led-control { display: grid; gap: var(--cs-space-8); }
.observation, .request { min-width: 0; font-size: var(--cs-type-14); line-height: 1.6; overflow-wrap: anywhere; }
.observation h4, .request h4 { font-weight: 600; }
.observation time { color: var(--cs-color-ink-muted); }
.request { padding-top: var(--cs-space-12); border-top: 1px solid var(--cs-color-line); }
.actions { display: flex; flex-wrap: wrap; gap: var(--cs-space-12); }
button { min-height: 44px; padding: var(--cs-space-12) var(--cs-space-16); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); cursor: pointer; }
.refresh { color: var(--cs-color-accent); }
.toggle { color: var(--cs-color-accent-ink); background: var(--cs-color-accent); }
button:disabled { color: var(--cs-color-ink-muted); background: var(--cs-color-surface-muted); cursor: not-allowed; }
button:hover:enabled { background: var(--cs-color-surface-muted); }
.toggle:hover:enabled { background: var(--cs-color-accent-hover); }
button:focus-visible { outline: 3px solid var(--cs-color-accent); outline-offset: 3px; }
</style>
