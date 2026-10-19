<script setup lang="ts">
import { computed } from 'vue'
import type { MonitoringSummary } from './monitoring-summary'
import type { PredictionUnavailableReason } from './aiot-api'
import { STALE_AFTER_SECONDS } from './monitoring-state'

const props = defineProps<{ summary: MonitoringSummary; ageSeconds: number | null }>()
const prediction = computed(() => props.summary.prediction)
const stale = computed(() => prediction.value?.data.status === 'available' && props.ageSeconds !== null && props.ageSeconds > STALE_AFTER_SECONDS)
const available = computed(() => prediction.value?.data.status === 'available' && !stale.value)
const reasons: Record<PredictionUnavailableReason, string> = {
  no_model: 'Nenhum modelo ativo. Aguardando ativação de um modelo para este equipamento.',
  insufficient_history: 'Histórico insuficiente. Aguardando leituras para completar a janela da previsão.',
  invalid_features: 'Variáveis inválidas. Não foi possível calcular uma previsão com estas leituras.',
  model_unavailable: 'Modelo indisponível. Não foi possível carregar ou executar a versão ativa.',
  stale_input: 'Leitura desatualizada. Aguardando uma entrada recente para calcular a previsão.',
}
const message = computed(() => {
  const reason = stale.value ? 'stale_input' : prediction.value?.data.reason ?? props.summary.prediction_unavailable_reason
  return available.value ? 'Previsão disponível para a última leitura.' : reason ? reasons[reason] : 'Aguardando previsão para a última leitura.'
})
const formatNumber = (value: number | null | undefined) => value?.toLocaleString('pt-BR', { maximumFractionDigits: 2 }) ?? '—'
const formatTime = (value: string) => new Date(value).toLocaleString('pt-BR')
</script>

<template>
  <section aria-label="Previsão do equipamento" class="prediction-panel">
    <h2 class="text-xl font-semibold">Previsão do equipamento</h2>
    <p class="mt-2 text-sm leading-6 text-ink-muted" role="status" aria-live="polite">{{ message }}</p>
    <dl v-if="available" class="prediction-values">
      <div><dt>Saúde estimada</dt><dd>{{ formatNumber(prediction?.data.health_score) }} / 100</dd></div>
      <div><dt>Vida útil restante estimada (RUL)</dt><dd>{{ formatNumber(prediction?.data.rul_hours) }} h</dd></div>
    </dl>
    <dl v-if="prediction" class="prediction-meta">
      <div><dt>Modelo</dt><dd>{{ prediction.data.model_version ?? 'Nenhum modelo ativo' }}</dd></div>
      <div><dt>Versão das variáveis</dt><dd>{{ prediction.data.features_version }}</dd></div>
      <div><dt>Entrada recebida em</dt><dd><time :datetime="prediction.data.input_received_at">{{ formatTime(prediction.data.input_received_at) }}</time></dd></div>
      <div><dt>Previsão calculada em</dt><dd><time :datetime="prediction.occurred_at">{{ formatTime(prediction.occurred_at) }}</time></dd></div>
    </dl>
    <p class="mt-3 text-sm leading-6 text-ink-muted">Estimativas do modelo, vinculadas à leitura recebida. Uma previsão não renova a atualidade dos sensores.</p>
  </section>
</template>

<style scoped>
.prediction-panel { min-width: 0; margin-top: var(--cs-space-24); padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.prediction-values, .prediction-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16); margin-top: var(--cs-space-16); }
dt { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
dd { margin-top: var(--cs-space-4); overflow-wrap: anywhere; }
.prediction-values dd { font-size: var(--cs-type-32); }
.prediction-meta { padding-top: var(--cs-space-16); border-top: 1px solid var(--cs-color-line); }
@media (max-width: 767px) { .prediction-panel { padding: var(--cs-space-16); } }
@media (max-width: 374px) { .prediction-values, .prediction-meta { grid-template-columns: minmax(0, 1fr); } }
</style>
