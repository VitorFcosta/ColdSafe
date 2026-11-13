<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue'
import type { MonitoringSummary } from './monitoring-summary'
import type { Prediction, PredictionUnavailableReason } from './aiot-api'
import { STALE_AFTER_SECONDS } from './monitoring-state'
import { formatFreshness } from './use-monitoring-summary'
import { formatReadingTime } from './temperature-chart'

const props = defineProps<{ summary: MonitoringSummary; ageSeconds: number | null; streamedPrediction?: Prediction | null }>()
// A leitura pode chegar antes da inferência; o último resultado conserva seu horário de origem.
const prediction = shallowRef<Prediction | null>(null)
function acceptPrediction(next: Prediction) {
  const { summary } = props
  const equipment = summary.equipment?.equipment_id ?? summary.reading?.equipment_id ?? summary.inventory?.equipment_id
  if (next.device_id !== summary.device.id || next.environment_id !== summary.environment.id ||
      (equipment && next.data.equipment_id !== equipment) ||
      (summary.reading?.device_record_id && next.device_record_id !== summary.reading.device_record_id)) return
  const previous = prediction.value
  if (previous) {
    const difference = Date.parse(next.data.input_received_at) - Date.parse(previous.data.input_received_at)
    if (difference < 0 || (difference === 0 && Date.parse(next.occurred_at) < Date.parse(previous.occurred_at))) return
  }
  prediction.value = next
}
watch([
  () => props.summary.environment.id,
  () => props.summary.device.id,
  () => props.summary.equipment?.equipment_id ?? props.summary.reading?.equipment_id ?? props.summary.inventory?.equipment_id,
  () => props.summary.prediction,
  () => props.summary.prediction_unavailable_reason,
], ([environment, device, equipment, next, reason], previous) => {
  if (environment !== previous?.[0] || device !== previous?.[1] || equipment !== previous?.[2] || reason != null) {
    prediction.value = null
  }
  if (next) acceptPrediction(next)
}, { immediate: true, flush: 'sync' })
watch(() => props.streamedPrediction, (next) => { if (next) acceptPrediction(next) }, { immediate: true, flush: 'sync' })

const predictionAge = computed(() => {
  const input = prediction.value?.data.input_received_at
  const latest = props.summary.reading?.received_at
  return (props.ageSeconds ?? 0) + (input && latest ? Math.max(0, (Date.parse(latest) - Date.parse(input)) / 1000) : 0)
})
const staleReading = computed(() => props.summary.prediction_unavailable_reason === 'stale_input' ||
  (props.ageSeconds !== null && props.ageSeconds > STALE_AFTER_SECONDS))
const stale = computed(() => staleReading.value || predictionAge.value > STALE_AFTER_SECONDS)
const available = computed(() => prediction.value?.data.status === 'available' && !stale.value)
const reasons: Record<PredictionUnavailableReason, string> = {
  no_model: 'Nenhum modelo ativo. Aguardando ativação de um modelo para este equipamento.',
  insufficient_history: 'Histórico insuficiente. Aguardando mais leituras para calcular a previsão.',
  invalid_features: 'Não foi possível calcular a previsão com estas leituras.',
  model_unavailable: 'Modelo indisponível. Não foi possível carregar ou executar a versão ativa.',
  stale_input: 'Leitura desatualizada. Aguardando uma nova leitura para calcular a previsão.',
}
const message = computed(() => {
  if (staleReading.value) return reasons.stale_input
  if (prediction.value && stale.value) return 'Previsão desatualizada. Aguardando um novo resultado para o equipamento.'
  const reason = prediction.value?.data.reason ?? props.summary.prediction_unavailable_reason
  return available.value ? 'Previsão disponível' : reason ? reasons[reason] : 'Aguardando previsão para a última leitura.'
})
const formatNumber = (value: number | null | undefined) => value?.toLocaleString('pt-BR', { maximumFractionDigits: 2 }) ?? '—'
const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const formatTime = (value: string) => formatReadingTime(value, timeZone)
</script>

<template>
  <section aria-label="Previsão do equipamento" class="prediction-panel">
    <h2 class="text-xl font-semibold">Previsão do equipamento</h2>
    <p class="prediction-origin">Modelo treinado com dados gerados para teste, sem calibração em equipamento real.</p>
    <p class="mt-2 text-sm leading-6 text-ink-muted" role="status" aria-live="polite">{{ message }}</p>
    <dl class="prediction-values">
      <div><dt>Saúde estimada</dt><dd>{{ available ? `${formatNumber(prediction?.data.health_score)} / 100` : '—' }}</dd></div>
      <div><dt>Vida útil restante</dt><dd>{{ available ? `${formatNumber(prediction?.data.rul_hours)} h` : '—' }}</dd></div>
    </dl>
    <dl class="prediction-summary">
      <div><dt>Modelo</dt><dd>{{ prediction?.data.model_version ?? (prediction?.data.reason === 'no_model' ? 'Nenhum modelo ativo' : '—') }}</dd></div>
      <div><dt>Idade da leitura</dt><dd>{{ prediction ? formatFreshness(predictionAge) : 'Sem leitura associada à previsão' }}</dd></div>
    </dl>
    <details class="prediction-details">
      <summary>Origem da previsão e horários</summary>
      <dl class="prediction-meta">
        <div><dt>Equipamento</dt><dd>{{ prediction?.data.equipment_id ?? summary.equipment?.equipment_id ?? summary.inventory?.equipment_id ?? summary.reading?.equipment_id ?? 'Não identificado' }}</dd></div>
        <div><dt>Versão das variáveis</dt><dd>{{ prediction?.data.features_version ?? '—' }}</dd></div>
        <div><dt>Horário da leitura usada</dt><dd><time v-if="prediction" :datetime="prediction.data.input_received_at">{{ formatTime(prediction.data.input_received_at) }}</time><span v-else>—</span></dd></div>
        <div><dt>Previsão calculada em</dt><dd><time v-if="prediction" :datetime="prediction.occurred_at">{{ formatTime(prediction.occurred_at) }}</time><span v-else>—</span></dd></div>
      </dl>
      <p class="mt-2 text-sm text-ink-muted">Horários no fuso {{ timeZone }}.</p>
    </details>
    <p class="mt-3 text-sm leading-6 text-ink-muted">A idade da leitura é contada a partir da chegada dos dados dos sensores.</p>
  </section>
</template>

<style scoped>
.prediction-panel { min-width: 0; margin-top: var(--cs-space-24); padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.prediction-values, .prediction-meta, .prediction-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16); margin-top: var(--cs-space-16); }
dt { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
dd { margin-top: var(--cs-space-4); overflow-wrap: anywhere; }
.prediction-summary { grid-template-columns: minmax(0, 1fr); }
.prediction-details { margin-top: var(--cs-space-16); border-top: 1px solid var(--cs-color-line); }
.prediction-details summary { min-height: var(--cs-control-min-height); padding-block: var(--cs-space-12); color: var(--cs-color-accent); font-size: var(--cs-type-14); font-weight: 600; cursor: pointer; }
.prediction-panel > [role="status"] { min-height: 3em; }
.prediction-values dd { font-size: var(--cs-type-32); }
.prediction-meta { margin-top: var(--cs-space-8); }
.prediction-origin { margin-top: var(--cs-space-8); color: var(--cs-color-status-stale); font-size: var(--cs-type-14); line-height: 1.5; }
@media (max-width: 767px) { .prediction-panel { padding: var(--cs-space-16); } }
@media (max-width: 374px) { .prediction-values, .prediction-meta, .prediction-summary { grid-template-columns: minmax(0, 1fr); } }
</style>
