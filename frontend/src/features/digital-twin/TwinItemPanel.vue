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
    <dl>
      <div><dt>ID</dt><dd>{{ item.id }}</dd></div>
      <div><dt>Estado atual</dt><dd>{{ twinStatusLabels[item.status] }}</dd></div>
      <div><dt>Valor atual</dt><dd>{{ item.value }}</dd></div>
      <div><dt>Última leitura recebida</dt><dd>{{ lastValue }}</dd></div>
      <div><dt>Idade da leitura</dt><dd>{{ formatFreshness(ageSeconds ?? undefined) }}</dd></div>
      <div><dt>Recebida em</dt><dd><time v-if="summary.reading" :datetime="summary.reading.received_at">{{ new Date(summary.reading.received_at).toLocaleString('pt-BR') }}</time><template v-else>Sem leitura recebida</template></dd></div>
    </dl>
    <p v-if="!fresh" role="status">Leitura histórica; situação atual não confirmada. Aguarde dados recentes.</p>
    <p v-if="item.kind !== 'equipment'">Saúde/RUL deste item: não aplicável — este {{ item.kind === 'sensor' ? 'sensor' : 'atuador' }} não possui modelo próprio.</p>
    <section aria-label="Equipamento associado">
      <h3>Previsão do equipamento associado</h3>
      <p>Ventilador · ID: {{ equipmentId ?? 'Não confirmado' }}. A previsão abaixo pertence ao equipamento, não aos sensores ou atuadores.</p>
      <PredictionPanel :summary="summary" :age-seconds="ageSeconds" />
    </section>
    <section class="mini-history" aria-label="Histórico do componente">
      <h3>Histórico de {{ metric.label.toLocaleLowerCase('pt-BR') }} · últimos 15 minutos</h3>
      <p v-if="item.kind !== 'sensor'">Este item não possui histórico próprio de estado disponível. Exibindo temperatura ambiente do equipamento associado.</p>
      <p>Consulta autorizada a cada 5 s, limitada a 300 leituras; histórico não renova a leitura atual.</p>
      <p v-if="historyPhase === 'loading'" role="status">Carregando histórico…</p>
      <p v-if="historyPhase === 'error'" role="status">Histórico indisponível. Nova consulta será tentada; eventual gráfico conserva a última consulta confirmada.</p>
      <TemperatureHistoryChart v-if="history && readings.length" :readings="readings" period="15m" :start="history.start" :end="history.end" :limit="history.limit" :thresholds="summary.thresholds" :metric="metric.key" />
      <p v-else-if="historyPhase === 'ready'" role="status">Sem leituras históricas para este ID no período.</p>
    </section>
    <section v-if="item.key === 'led'" aria-label="Controle do LED selecionado">
      <h3>LED · comando manual</h3>
      <LedControl :led="led" :phase="actuatorPhase" :submitting="commandSubmitting" :error="commandError" @toggle="toggleLed" @refresh="loadActuators(mqttId)" />
      <p>Confirmação do comando e estado observado são informações separadas; enviar não confirma o LED.</p>
    </section>
    <section v-else-if="item.key === 'buzzer'" aria-label="Buzzer automático">
      <h3>Buzzer automático</h3><p>{{ actuatorLabel(buzzer) }}</p>
      <p>Buzzer segue a regra térmica do ambiente. Comando manual não aplicável.</p>
    </section>
  </section>
</template>

<style scoped>
.item-panel { min-width: 0; padding: var(--cs-space-24); background: var(--cs-color-surface); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); }
h2 { font-size: var(--cs-type-20); font-weight: 600; }h3 { font-weight: 600; }section, dl { margin-top: var(--cs-space-24); }dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-16); }dt { color: var(--cs-color-ink-muted); }dd { margin-top: var(--cs-space-8); }p { margin-top: var(--cs-space-12); line-height: 1.7; }dd, p { overflow-wrap: anywhere; }.mini-history :deep([role=img]) { height: 180px; }
@media (max-width: 420px) { .item-panel { padding: var(--cs-space-16); }dl { grid-template-columns: minmax(0, 1fr); } }
</style>
