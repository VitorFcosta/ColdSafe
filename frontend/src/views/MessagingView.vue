<script setup lang="ts">
import LiveDataRegion from '../features/monitoring/LiveDataRegion.vue'
import { computed, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { clearSession, refreshSessionIdentity, sessionRole, sessionToken } from '../features/account/session'
import { fetchMessaging, fetchMessageSamples, MessagingAccessError, type MessagingSnapshot, type MessageSamplesSnapshot } from '../features/messaging/messaging-api'

const router = useRouter()
const snapshot = ref<MessagingSnapshot | null>(null)
const loading = ref(false)
const failed = ref(false)
const samples = ref<MessageSamplesSnapshot | null>(null)
const samplesFailed = ref(false)
const now = ref(Date.now())
const tableScroll = useTemplateRef<HTMLElement>('tableScroll')
const tableOverflows = ref(false)
const queueLabels = new Map([
  ['coldsafe.gateway', 'Comandos aos dispositivos'],
  ['coldsafe.writer', 'Gravação de leituras'],
  ['coldsafe.inference', 'Análise de leituras e previsões'],
  ['coldsafe.delivery', 'Atualizações do painel'],
  ['coldsafe.commands', 'Regras e comandos'],
  ['coldsafe.generation', 'Geração de dados'],
  ['coldsafe.training', 'Treinamento de modelos'],
  ['coldsafe.observability', 'Cópias para acompanhamento'],
  ['coldsafe.model-activation', 'Ativação de modelos'],
  ['coldsafe.dlq', 'Mensagens que falharam'],
])
const authorized = computed(() => Boolean(sessionToken.value) && sessionRole.value === 'admin')
const ageSeconds = computed(() => snapshot.value
  ? Math.max(0, Math.floor((now.value - Date.parse(snapshot.value.sampled_at)) / 1000)) : null)
const stale = computed(() => ageSeconds.value !== null && ageSeconds.value >= 15)
const queueTotals = computed(() => {
  const queues = snapshot.value?.queues ?? []
  if (!queues.length) return null
  function sum(key: 'messages_ready' | 'messages_unacknowledged' | 'consumers' | 'publish_rate') {
    let total = 0
    for (const queue of queues) {
      const value = queue[key]
      if (value === null) return null
      total += value
    }
    return Number.isFinite(total) && (key === 'publish_rate' || Number.isSafeInteger(total)) ? total : null
  }
  return { ready: sum('messages_ready'), unacknowledged: sum('messages_unacknowledged'),
    consumers: sum('consumers'), publishRate: sum('publish_rate') }
})
const unknownPublishRates = computed(() => snapshot.value?.queues.filter(queue => queue.publish_rate === null).length ?? 0)
const busiestQueues = computed(() => (snapshot.value?.queues ?? [])
  .filter(queue => queue.messages_ready > 0)
  .sort((first, second) => second.messages_ready - first.messages_ready)
  .slice(0, 3))
const observationStale = computed(() => samples.value && (samples.value.stale ||
  !samples.value.last_observed_at || now.value - Date.parse(samples.value.last_observed_at) >= samples.value.stale_after_seconds * 1000))
const sampleSections = computed(() => [
  { id: 'messages', title: 'Últimas mensagens', empty: 'Nenhuma mensagem observada nos seus ambientes nesta amostra.', items: samples.value?.messages ?? [] },
  { id: 'dead-letters', title: 'Falhas nas mensagens', empty: 'Nenhuma falha observada nos seus ambientes nesta amostra.', items: samples.value?.dead_letters ?? [] },
])
const ageTimer = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(ageTimer))

watch(tableScroll, (container, _, onCleanup) => {
  tableOverflows.value = false
  if (!container) return
  const measure = () => { tableOverflows.value = container.scrollWidth > container.clientWidth }
  const observer = new ResizeObserver(measure)
  observer.observe(container)
  observer.observe(container.querySelector('table')!)
  measure()
  onCleanup(() => observer.disconnect())
}, { flush: 'post' })

watch([sessionToken, sessionRole], ([token, role], _previous, onCleanup) => {
  snapshot.value = null
  samples.value = null
  samplesFailed.value = false
  failed.value = false
  loading.value = false
  if (!token) { void router.replace('/login'); return }
  if (role !== 'admin') return
  let active = true
  let pending = false
  let controller: AbortController | null = null
  let deadline: ReturnType<typeof setTimeout> | undefined
  async function refresh() {
    if (!active || pending) return
    pending = true
    loading.value = true
    controller = new AbortController()
    deadline = setTimeout(() => controller?.abort(), 8000)
    try {
      const [metricsResult, samplesResult] = await Promise.allSettled([
        fetchMessaging(token!, controller.signal), fetchMessageSamples(token!, controller.signal),
      ])
      if (!active) return
      const denied = [metricsResult, samplesResult].find((result) =>
        result.status === 'rejected' && result.reason instanceof MessagingAccessError)
      if (denied?.status === 'rejected') {
        snapshot.value = null
        samples.value = null
        if (denied.reason.status === 401) clearSession()
        else void refreshSessionIdentity().catch(() => { /* Unknown permissions keep private samples hidden. */ })
        return
      }
      now.value = Date.now()
      failed.value = metricsResult.status === 'rejected'
      samplesFailed.value = samplesResult.status === 'rejected'
      if (metricsResult.status === 'fulfilled') snapshot.value = metricsResult.value
      if (samplesResult.status === 'fulfilled') samples.value = samplesResult.value
    } finally {
      clearTimeout(deadline)
      pending = false
      if (active) loading.value = false
    }
  }
  const poll = setInterval(() => { void refresh() }, 5000)
  onCleanup(() => {
    active = false
    clearInterval(poll)
    clearTimeout(deadline)
    controller?.abort()
  })
  void refresh()
}, { immediate: true, flush: 'sync' })

const rateNumber = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 })
const countNumber = new Intl.NumberFormat('pt-BR')
function formatRate(value: number | null) {
  if (value === null) return 'Indisponível'
  if (value > 0 && value < 0.01) return '< 0,01 /s'
  return `${rateNumber.format(value)} /s`
}
const formatCount = (value: number | null | undefined) => value == null
  ? 'Indisponível' : countNumber.format(value)
const formatTime = (value: string) => new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short', timeStyle: 'medium',
}).format(new Date(value))
</script>

<template>
  <main class="messaging cs-controls">
    <div class="shell">
      <section class="heading" aria-labelledby="messaging-title">
        <h1 id="messaging-title" tabindex="-1">Filas e mensagens</h1>
        <p>Acompanhe as filas do sistema e veja amostras de mensagens dos seus ambientes.</p>
      </section>
      <p v-if="!authorized" role="status">Só administradores podem ver as métricas das filas. Para ver seus ambientes, abra o Monitoramento.</p>
      <LiveDataRegion v-else>
      <section class="global-metrics" aria-labelledby="global-metrics-title">
        <div class="section-heading">
          <h2 id="global-metrics-title">Estado das filas</h2>
          <p v-if="snapshot" class="sample-age">Coleta das métricas há {{ ageSeconds }} s · <time :datetime="snapshot.sampled_at">{{ formatTime(snapshot.sampled_at) }}</time></p>
        </div>
        <p v-if="failed" role="alert" class="feedback error">Não foi possível atualizar as filas. O painel tentará de novo. {{ snapshot ? 'Última consulta bem-sucedida abaixo; a situação atual não está confirmada.' : 'Ainda não há dados para mostrar.' }}</p>
        <p v-if="stale" role="status" class="feedback stale">Informação desatualizada. A situação atual não está confirmada.</p>
        <p v-if="loading && !snapshot" role="status">Carregando dados das filas…</p>
        <dl class="metric-grid">
          <div class="primary-metric"><dt>Disponíveis nas filas</dt><dd :class="{ unavailable: queueTotals?.ready == null }">{{ formatCount(queueTotals?.ready) }}</dd></div>
          <div><dt>Entregues sem confirmação</dt><dd :class="{ unavailable: queueTotals?.unacknowledged == null }">{{ formatCount(queueTotals?.unacknowledged) }}</dd></div>
          <div><dt>Assinaturas ativas</dt><dd :class="{ unavailable: queueTotals?.consumers == null }">{{ formatCount(queueTotals?.consumers) }}</dd></div>
          <div><dt>Mensagens entrando</dt><dd :class="{ unavailable: queueTotals?.publishRate == null }">{{ formatRate(queueTotals?.publishRate ?? null) }}</dd></div>
        </dl>
        <p class="hint">Totais das filas listadas. Uma mensagem pode passar por mais de uma fila.</p>
        <p v-if="unknownPublishRates" class="hint">{{ unknownPublishRates }} {{ unknownPublishRates === 1 ? 'fila sem taxa de entrada medida.' : 'filas sem taxa de entrada medida.' }}</p>
        <section v-if="busiestQueues.length" class="queue-highlights" aria-labelledby="queue-highlights-title">
          <h3 id="queue-highlights-title">Filas com mais mensagens disponíveis</h3>
          <ul>
            <li v-for="queue in busiestQueues" :key="queue.name">
              <span>{{ queueLabels.get(queue.name) ?? queue.name }}</span>
              <strong>{{ formatCount(queue.messages_ready) }} disponíveis</strong>
            </li>
          </ul>
        </section>
      </section>
      <section class="panel" aria-labelledby="queues-title">
        <h2 id="queues-title">Filas do sistema</h2>
        <p class="hint">Atualização a cada 5 segundos. Serviços que consultam a fila periodicamente podem operar com zero assinaturas.</p>
        <p v-if="tableOverflows" id="queues-help" class="hint">Role para os lados para ver todas as colunas. Com a tabela em foco, use as setas.</p>
        <template v-if="snapshot">
          <p v-if="snapshot.queues.length === 0" role="status">Nenhuma fila disponível nesta amostra.</p>
          <div v-else ref="tableScroll" class="table-scroll" role="region" aria-label="Métricas por fila" :aria-describedby="tableOverflows ? 'queues-help' : undefined" tabindex="0">
            <table>
              <caption>Entrada e entrega em mensagens por segundo</caption>
              <thead><tr>
                <th scope="col">Fila</th><th scope="col">Total</th><th scope="col">Disponíveis</th>
                <th scope="col">Entregues sem confirmação</th><th scope="col">Assinaturas ativas</th>
                <th scope="col">Entrada</th><th scope="col">Entrega</th>
              </tr></thead>
              <tbody><tr v-for="queue in snapshot.queues" :key="queue.name">
                <th scope="row"><span v-if="queueLabels.has(queue.name)">{{ queueLabels.get(queue.name) }}</span><span :class="{ 'queue-id': queueLabels.has(queue.name) }">{{ queue.name }}</span></th>
                <td>{{ formatCount(queue.messages) }}</td><td :class="{ 'positive-count': queue.messages_ready > 0 }">{{ formatCount(queue.messages_ready) }}</td>
                <td>{{ formatCount(queue.messages_unacknowledged) }}</td><td>{{ formatCount(queue.consumers) }}</td>
                <td>{{ formatRate(queue.publish_rate) }}</td><td>{{ formatRate(queue.deliver_rate) }}</td>
              </tr></tbody>
            </table>
          </div>
        </template>
      </section>
      <section class="panel observation" aria-labelledby="observation-title">
        <h2 id="observation-title">Mensagens dos seus ambientes</h2>
        <p>Amostra dos dispositivos ativos, com tipo, horário e outros dados de cada mensagem observada.</p>
        <p v-if="samplesFailed" role="alert" class="feedback error">Não foi possível atualizar as mensagens. A consulta será repetida automaticamente. {{ samples ? 'Última consulta bem-sucedida abaixo; a situação atual não está confirmada.' : 'Nenhuma amostra disponível.' }}</p>
        <p v-if="loading && !samples" role="status">Consultando mensagens…</p>
        <template v-if="samples">
          <p role="status" class="observer-state" :class="samples.connected && !observationStale && !samplesFailed ? 'current' : 'stale'">{{ samples.connected ? 'Observador conectado na última consulta.' : 'Observador desconectado na última consulta.' }}</p>
          <p v-if="observationStale" role="status" class="feedback stale">Observação desatualizada. Nenhuma mensagem recente dos seus ambientes foi observada.</p>
          <p class="sample-age">Consulta de <time :datetime="samples.sampled_at">{{ formatTime(samples.sampled_at) }}</time><template v-if="samples.last_observed_at"> · última mensagem observada em <time :datetime="samples.last_observed_at">{{ formatTime(samples.last_observed_at) }}</time></template></p>
          <details v-for="section in sampleSections" :key="section.id" :aria-labelledby="`${section.id}-title`" class="sample-section">
            <summary><span :id="`${section.id}-title`">{{ section.title }}</span><span class="sample-count">{{ formatCount(section.items.length) }} na amostra</span></summary>
            <p v-if="section.items.length === 0" role="status">{{ section.empty }}</p>
            <ol v-else class="samples">
              <li v-for="sample in section.items" :key="`${sample.event_id}:${sample.source_queue}`">
                <p><strong>{{ sample.type }}</strong> · {{ sample.device_id }}</p>
                <dl>
                  <div><dt>Evento</dt><dd>{{ sample.event_id }}</dd></div>
                  <div><dt>Ambiente</dt><dd>{{ sample.environment_id }}</dd></div>
                  <div><dt>Ocorrido em</dt><dd><time :datetime="sample.occurred_at">{{ formatTime(sample.occurred_at) }}</time></dd></div>
                  <div><dt>Observado em</dt><dd><time :datetime="sample.observed_at">{{ formatTime(sample.observed_at) }}</time></dd></div>
                  <template v-if="section.id === 'dead-letters'">
                    <div><dt>Fila de origem</dt><dd>{{ sample.source_queue ?? 'Não informada' }}</dd></div>
                    <div><dt>Motivo</dt><dd>{{ sample.reason ?? 'Não informado' }}</dd></div>
                    <div><dt>Erro</dt><dd>{{ sample.error_code ?? 'Não informado' }}</dd></div>
                  </template>
                </dl>
              </li>
            </ol>
          </details>
        </template>
        <details class="sample-section">
          <summary>Como a amostra é coletada</summary>
          <p>O observador guarda até 100 eventos e 100 cópias de falhas em memória e mostra os registros dos seus dispositivos ativos, do mais recente ao mais antigo. Reiniciar a API limpa a amostra.</p>
        </details>
      </section>
      <details class="panel diagnostic" aria-labelledby="writer-title">
        <summary id="writer-title">Diagnóstico técnico</summary>
        <h2>Ensaio de parada do gravador</h2>
        <p>Siga o guia de operação para parar e retomar o gravador no terminal. Com a entrada de mensagens ativa, acompanhe quantas ficam disponíveis em <code>coldsafe.writer</code> durante a parada e como a fila esvazia após retomar o serviço.</p>
        <p>O gravador pode funcionar com zero assinaturas porque consulta a fila periodicamente. Confirme o estado do serviço no terminal.</p>
      </details>
      </LiveDataRegion>
    </div>
  </main>
</template>

<style scoped>
.messaging { padding: var(--cs-space-48); }
.shell { max-width: 1200px; margin-inline: auto; min-width: 0; display: grid; gap: var(--cs-space-24); }
.heading p { color: var(--cs-color-ink-muted); max-width: 70ch; }
h1 { font-size: var(--cs-type-32); margin-block: var(--cs-space-8); }
h2 { font-size: var(--cs-type-20); margin-bottom: var(--cs-space-12); }
p { line-height: 1.6; margin-block: var(--cs-space-8); }
.section-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: var(--cs-space-8) var(--cs-space-24); }
.sample-age { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--cs-space-16); margin-top: var(--cs-space-16); }
.metric-grid > div { min-width: 0; padding: var(--cs-space-16); background: var(--cs-color-surface); border-radius: var(--cs-radius-panel); border: 1px solid var(--cs-color-line); }
.metric-grid > .primary-metric { border-color: var(--cs-color-control-border); }
.metric-grid dt { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); font-weight: 500; }
.metric-grid dd { margin-top: var(--cs-space-8); font-size: var(--cs-type-24); font-weight: 650; line-height: 1.3333; overflow-wrap: anywhere; }
.metric-grid dd.unavailable { font-size: var(--cs-type-16); font-weight: 500; line-height: 2; }
.queue-highlights { margin-top: var(--cs-space-16); padding: var(--cs-space-12) var(--cs-space-16); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.queue-highlights h3 { font-size: var(--cs-type-16); margin-bottom: var(--cs-space-8); }
.queue-highlights ul { list-style: none; padding: 0; margin: 0; }
.queue-highlights li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 var(--cs-space-16); justify-content: space-between; padding-block: var(--cs-space-4); overflow-wrap: anywhere; }
.queue-highlights li + li { border-top: 1px solid var(--cs-color-line); }
.panel { background: var(--cs-color-surface); padding: var(--cs-space-24); border-radius: var(--cs-radius-panel); min-width: 0; }
.observer-state { display: inline-block; padding: var(--cs-space-8) var(--cs-space-12); border-radius: var(--cs-radius-4); font-weight: 600; }
.current { color: var(--cs-color-status-normal); background: var(--cs-color-normal-surface); }
.feedback.stale, .observer-state.stale { color: var(--cs-color-status-stale); background: var(--cs-color-stale-surface); }
.sample-section { border-top: 1px solid var(--cs-color-line); margin-top: var(--cs-space-8); }
summary { cursor: pointer; font-weight: 650; padding-block: var(--cs-space-12); }
summary::marker { color: var(--cs-color-accent); }
summary:focus-visible, .table-scroll:focus-visible { outline: 3px solid var(--cs-focus-ring); outline-offset: 3px; }
.sample-count { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); font-weight: 400; margin-inline-start: var(--cs-space-8); }
.diagnostic { padding-block: var(--cs-space-8); }
.diagnostic h2 { margin-top: var(--cs-space-8); }
.samples { list-style: decimal; padding-left: var(--cs-space-24); }
.samples li { min-width: 0; padding-block: var(--cs-space-16); border-top: 1px solid var(--cs-color-line); overflow-wrap: anywhere; }
.samples li:first-child { padding-top: 0; border-top: 0; }
.samples li > p { margin-top: 0; }
.samples dl { margin-top: var(--cs-space-8); font-size: var(--cs-type-14); }
.samples dl > div { display: flex; flex-wrap: wrap; gap: var(--cs-space-8); }
.samples dt { font-weight: 600; }.samples dd { min-width: 0; }
.table-scroll { max-width: 100%; overflow-x: auto; margin-top: var(--cs-space-16); }
table { width: 100%; min-width: 47rem; border-collapse: collapse; text-align: left; font-size: var(--cs-type-14); font-variant-numeric: tabular-nums; }
caption { text-align: left; color: var(--cs-color-ink-muted); margin-bottom: var(--cs-space-8); }
th, td { padding: var(--cs-space-8) var(--cs-space-12); border-bottom: 1px solid var(--cs-color-line); }
th { font-weight: 600; }
thead { background: var(--cs-color-surface-muted); }
thead th { overflow-wrap: normal; }
tbody th { min-width: 12rem; overflow-wrap: anywhere; }
td, thead th:not(:first-child) { text-align: right; }
td { white-space: nowrap; }
.queue-id { display: block; color: var(--cs-color-ink-muted); font-weight: 400; }
.positive-count { font-weight: 650; }
@media (max-width: 1100px) {
  .messaging { padding: var(--cs-space-16); }.panel { padding: var(--cs-space-16); }
  h1 { font-size: var(--cs-type-24); line-height: 1.3333; }
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 360px) { .metric-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
