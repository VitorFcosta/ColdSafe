<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import type { Device } from '../account/catalog'
import { sensorRoles } from '../monitoring/aiot-api'
import { fetchMonitoringHistory, type MonitoringHistory } from '../monitoring/monitoring-history'
import type { MonitoringSummary } from '../monitoring/monitoring-summary'
import { sensorMetrics } from '../monitoring/sensor-metrics'
import { formatFreshness } from '../monitoring/use-monitoring-summary'
import { actuatorLabel, useActuators } from '../monitoring/use-actuators'
import LedControl from '../monitoring/LedControl.vue'
import PredictionPanel from '../monitoring/PredictionPanel.vue'
import TemperatureHistoryChart from '../monitoring/TemperatureHistoryChart.vue'
import { twinStatusLabels, type TwinItem } from './twin-state'

const props = defineProps<{
  item: TwinItem; summary: MonitoringSummary; device: Device; token: string
  fresh: boolean; ageSeconds: number | null; revision: number; connectionState: string
}>()
const mqttId = computed(() => props.device.mqtt_device_id)
const { led, buzzer, actuatorPhase, commandError, commandSubmitting, loadActuators, toggleLed } =
  useActuators(toRef(props, 'token'), mqttId, toRef(props, 'revision'), toRef(props, 'connectionState'))
const metricIndex = computed(() => sensorMetrics.findIndex((metric) => metric.key === props.item.key))
const metric = computed(() => sensorMetrics[metricIndex.value] ?? sensorMetrics[0])
const condition = computed(() => {
  if (props.item.kind === 'equipment' && props.item.status === 'no_data') return 'Sem previsão'
  if (props.item.kind === 'sensor' && metricIndex.value > 0 && props.item.status === 'normal') return 'Leitura atual'
  return twinStatusLabels[props.item.status]
})
const equipmentId = computed(() => props.summary.inventory?.equipment_id ?? props.summary.equipment?.equipment_id ?? props.summary.reading?.equipment_id)
const history = ref<MonitoringHistory | null>(null)
const historyPhase = ref<'loading' | 'ready' | 'error'>('loading')
const readings = computed(() => history.value?.readings.filter((reading) =>
  equipmentId.value && reading.equipment_id === equipmentId.value && reading.environment_id === props.device.environment_id &&
  reading.device_record_id === props.device.id && (props.item.kind !== 'sensor' ||
    reading.sensor_ids?.[sensorRoles[metricIndex.value]!] === props.item.id)) ?? [])
const lastValue = computed(() => {
  const reading = props.summary.reading
  if (!reading) return 'Sem leitura recebida'
  if (props.item.kind === 'sensor') {
    const value = reading[metric.value.key]
    return value == null ? 'Sem leitura recebida' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} ${metric.value.unit}`
  }
  const equipment = props.summary.equipment
  if (!equipment) return 'Sem leitura recebida'
  if (props.item.key === 'fan') return equipment.running ? 'Em operação' : 'Parado'
  return equipment[props.item.key as 'led' | 'buzzer'].actual_state ? 'Ligado' : 'Desligado'
})

watch([() => props.token, () => props.device.id, () => props.device.mqtt_device_id, () => props.device.environment_id], ([token, deviceId, deviceMqttId], _old, onCleanup) => {
  let active = true
  let pending = false
  let revision = 0
  let controller: AbortController | null = null
  let deadline: ReturnType<typeof setTimeout> | undefined
  history.value = null; historyPhase.value = 'loading'
  async function refresh() {
    if (!active || pending) return
    pending = true
    const attempt = ++revision
    controller = new AbortController()
    const signal = controller.signal
    deadline = setTimeout(() => {
      if (!active || attempt !== revision) return
      revision++; pending = false; historyPhase.value = 'error'; controller?.abort()
    }, 8000)
    const requestDeadline = deadline
    try {
      const result = await fetchMonitoringHistory({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
        deviceId: deviceMqttId!, token, period: '15m', fetcher: (input, init) => fetch(input, { ...init, signal }) })
      if (!active || attempt !== revision || signal.aborted || props.device.id !== deviceId) return
      history.value = result; historyPhase.value = 'ready'
    } catch {
      if (active && attempt === revision) historyPhase.value = 'error'
    } finally {
      clearTimeout(requestDeadline)
      if (attempt === revision) pending = false
    }
  }
  const interval = setInterval(() => { void refresh() }, 5000)
  onCleanup(() => { active = false; clearInterval(interval); clearTimeout(deadline); controller?.abort() })
  void refresh()
}, { immediate: true })
</script>

<template>
  <section class="item-panel" aria-label="Detalhes do componente">
    <h2>{{ item.label }}</h2>
    <template v-if="item.key !== 'led'">
      <p class="reading-value">{{ fresh ? item.value : lastValue }}</p>
      <p v-if="summary.reading" class="reading-caption">
        {{ fresh ? condition : 'Última leitura' }} · {{ formatFreshness(ageSeconds ?? undefined) }}
      </p>
    </template>
    <p v-if="!fresh && summary.reading" class="reading-warning" role="status">Leitura histórica. A situação atual segue sem confirmação.</p>
    <section v-if="item.key === 'led'" class="led-section" aria-label="Controle do LED selecionado">
      <h3>Controle manual da luz</h3>
      <LedControl :led="led" :phase="actuatorPhase" :submitting="commandSubmitting" :error="commandError"
        :observation="summary.equipment && summary.reading ? { state: summary.equipment.led.actual_state, receivedAt: summary.reading.received_at, ageSeconds } : undefined"
        @toggle="toggleLed" @refresh="loadActuators(mqttId)" />
      <p>A confirmação do pedido e a leitura da luz chegam separadamente.</p>
    </section>
    <p v-else-if="item.key === 'buzzer'">O som de aviso segue a regra de temperatura do ambiente.</p>

    <details class="technical-details">
      <summary>Histórico e identificação</summary>
      <dl>
        <div><dt>ID</dt><dd>{{ item.id }}</dd></div>
        <div><dt>Idade da leitura</dt><dd>{{ formatFreshness(ageSeconds ?? undefined) }}</dd></div>
        <div v-if="summary.reading"><dt>Recebida em</dt><dd><time :datetime="summary.reading.received_at">{{ new Date(summary.reading.received_at).toLocaleString('pt-BR') }}</time></dd></div>
        <div v-if="item.key === 'buzzer'"><dt>Último pedido automático</dt><dd>{{ actuatorLabel(buzzer) }}</dd></div>
      </dl>
      <section class="mini-history" aria-label="Histórico do componente">
        <h3>Histórico de {{ metric.label.toLocaleLowerCase('pt-BR') }} · últimos 15 minutos</h3>
        <p v-if="item.kind !== 'sensor'">Série de referência da temperatura ambiente. O histórico de estado desta peça está indisponível.</p>
        <p>Até 300 leituras. O histórico é atualizado a cada 5 segundos.</p>
        <p v-if="historyPhase === 'loading'" role="status">Carregando histórico…</p>
        <p v-if="historyPhase === 'error'" role="status">Histórico indisponível. A consulta será repetida. O gráfico exibe a última consulta bem-sucedida, se houver.</p>
        <TemperatureHistoryChart v-if="history && readings.length" :readings="readings" period="15m"
          :start="history.start" :end="history.end" :limit="history.limit" :thresholds="summary.thresholds" :metric="metric.key" />
        <p v-else-if="historyPhase === 'ready'" role="status">Sem leituras para esta série no período.</p>
      </section>
    </details>
    <details class="technical-details">
      <summary>Previsão do ventilador</summary>
      <section aria-label="Equipamento associado">
        <p v-if="item.kind !== 'equipment'">A previsão de saúde e vida útil pertence ao ventilador.</p>
        <p>ID do ventilador · {{ equipmentId ?? 'Não confirmado' }}</p>
        <PredictionPanel :summary="summary" :age-seconds="ageSeconds" />
      </section>
    </details>
  </section>
</template>

<style scoped>
.item-panel { min-width: 0; padding: var(--cs-space-16); background: var(--cs-color-surface); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); }
h2 { font-size: var(--cs-type-20); font-weight: 600; }
h3 { font-size: var(--cs-type-16); font-weight: 600; }
.led-section { margin-top: var(--cs-space-12); }
.led-section h3 { margin-bottom: var(--cs-space-8); }
p { margin-top: var(--cs-space-8); line-height: 1.6; font-size: var(--cs-type-14); }
.reading-value { margin-top: var(--cs-space-12); font-size: var(--cs-type-24); font-weight: 650; line-height: 1.25; font-variant-numeric: tabular-nums; }
.reading-caption, dt { color: var(--cs-color-ink-muted); }
.reading-warning { color: var(--cs-color-status-stale); }
.technical-details { border-top: 1px solid var(--cs-color-line); margin-top: var(--cs-space-8); font-size: var(--cs-type-14); }
.technical-details:first-of-type { margin-top: var(--cs-space-16); }
summary { min-height: var(--cs-control-min-height); display: list-item; align-content: center; cursor: pointer; color: var(--cs-color-accent); }
dl { display: grid; gap: var(--cs-space-8); margin-block: var(--cs-space-8) var(--cs-space-16); }
dd { font-variant-numeric: tabular-nums; }
dd, p, h2, h3, summary { overflow-wrap: anywhere; }
.mini-history :deep([role=img]) { height: 240px; }
.mini-history :deep(canvas) { max-width: 100%; }
.technical-details :deep(.prediction-panel) { padding: 0; border: 0; margin-top: var(--cs-space-16); }
</style>
