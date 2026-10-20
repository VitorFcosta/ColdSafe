<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { clearSession, logout, refreshSessionIdentity, sessionRole, sessionToken } from '../features/account/session'
import { fetchMessaging, fetchMessageSamples, MessagingAccessError, type MessagingSnapshot, type MessageSamplesSnapshot } from '../features/messaging/messaging-api'

const router = useRouter()
const snapshot = ref<MessagingSnapshot | null>(null)
const loading = ref(false)
const failed = ref(false)
const samples = ref<MessageSamplesSnapshot | null>(null)
const samplesFailed = ref(false)
const logoutError = ref('')
const now = ref(Date.now())
const authorized = computed(() => Boolean(sessionToken.value) && sessionRole.value === 'admin')
const ageSeconds = computed(() => snapshot.value
  ? Math.max(0, Math.floor((now.value - Date.parse(snapshot.value.sampled_at)) / 1000)) : null)
const stale = computed(() => ageSeconds.value !== null && ageSeconds.value >= 15)
const observationStale = computed(() => samples.value && (samples.value.stale ||
  !samples.value.last_observed_at || now.value - Date.parse(samples.value.last_observed_at) >= samples.value.stale_after_seconds * 1000))
const sampleSections = computed(() => [
  { id: 'messages', title: 'Últimas mensagens', empty: 'Nenhuma mensagem observada nos seus ambientes nesta amostra.', items: samples.value?.messages ?? [] },
  { id: 'dead-letters', title: 'Mensagens mortas (DLQ)', empty: 'Nenhuma mensagem morta observada nos seus ambientes nesta amostra.', items: samples.value?.dead_letters ?? [] },
])
const ageTimer = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(ageTimer))

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

async function signOut() {
  logoutError.value = ''
  try { await logout() } catch {
    logoutError.value = 'Não foi possível encerrar a sessão. Tente novamente.'
  }
}
const formatRate = (value: number | null) => value === null
  ? 'Indisponível' : `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value)} /s`
const formatTime = (value: string) => new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short', timeStyle: 'medium',
}).format(new Date(value))
</script>

<template>
  <main class="messaging">
    <a class="skip-link" href="#messaging-title">Ir para o conteúdo</a>
    <div class="shell">
      <header class="nav">
        <RouterLink to="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</RouterLink>
        <nav aria-label="Navegação principal">
          <RouterLink to="/dashboard">Monitoramento</RouterLink>
          <RouterLink to="/insights">Insights</RouterLink><RouterLink to="/digital-twin">Gêmeo digital</RouterLink>
          <RouterLink to="/manage">Ambientes e dispositivos</RouterLink>
          <RouterLink to="/messaging" aria-current="page">Mensageria</RouterLink>
          <RouterLink to="/laboratory">Laboratório</RouterLink>
          <RouterLink to="/training">Treinamento</RouterLink>
        </nav>
        <button class="sign-out" type="button" @click="signOut">Sair</button>
      </header>
      <p v-if="logoutError" role="alert" class="feedback">{{ logoutError }}</p>
      <section class="heading" aria-labelledby="messaging-title">
        <p class="eyebrow">Operação</p>
        <h1 id="messaging-title" tabindex="-1">Mensageria</h1>
        <p>Filas, taxas e consumidores da infraestrutura compartilhada. Acesso administrativo; as métricas agregam a operação global. As amostras abaixo exibem somente metadados de mensagens dos seus ambientes.</p>
      </section>
      <p v-if="!authorized" role="status">As métricas de mensageria estão disponíveis apenas para administradores. Consulte o monitoramento para ver seus ambientes.</p>
      <template v-else>
      <section class="panel" aria-labelledby="queues-title">
        <h2 id="queues-title">Filas de processamento</h2>
        <p>Atualização automática a cada 5 segundos. Taxas em mensagens por segundo; “Indisponível” indica ausência de amostra.</p>
        <p>Consumidores conta assinaturas ativas no broker. Serviços que consultam a fila periodicamente podem aparecer com zero mesmo em operação.</p>
        <p v-if="failed" role="alert" class="feedback">Não foi possível atualizar a mensageria. A consulta será repetida automaticamente. {{ snapshot ? 'Última consulta bem-sucedida abaixo; a situação atual não está confirmada.' : 'Nenhuma amostra disponível.' }}</p>
        <p v-if="stale" role="status" class="feedback">Informação desatualizada. A situação atual não está confirmada.</p>
        <p v-if="loading && !snapshot" role="status">Consultando mensageria…</p>
        <template v-if="snapshot">
          <p class="sample-age">Amostra de <time :datetime="snapshot.sampled_at">{{ formatTime(snapshot.sampled_at) }}</time> · há {{ ageSeconds }} s</p>
          <p v-if="snapshot.queues.length === 0" role="status">Nenhuma fila disponível nesta amostra.</p>
          <div v-else class="table-scroll" role="region" aria-label="Métricas por fila; role horizontalmente para ver todas as colunas" tabindex="0">
            <table>
              <caption class="sr-only">Métricas por fila na última amostra recebida</caption>
              <thead><tr>
                <th scope="col">Fila</th><th scope="col">Total</th><th scope="col">Prontas</th>
                <th scope="col">Sem confirmação</th><th scope="col">Consumidores</th>
                <th scope="col">Publicação</th><th scope="col">Entrega</th>
              </tr></thead>
              <tbody><tr v-for="queue in snapshot.queues" :key="queue.name">
                <th scope="row">{{ queue.name }}</th><td>{{ queue.messages }}</td><td>{{ queue.messages_ready }}</td>
                <td>{{ queue.messages_unacknowledged }}</td><td>{{ queue.consumers }}</td>
                <td>{{ formatRate(queue.publish_rate) }}</td><td>{{ formatRate(queue.deliver_rate) }}</td>
              </tr></tbody>
            </table>
          </div>
        </template>
      </section>
      <section class="panel observation" aria-labelledby="observation-title">
        <h2 id="observation-title">Observação de mensagens</h2>
        <p>Amostra em memória de até 100 eventos e 100 mensagens mortas, dos mais recentes para os mais antigos. Somente seus ambientes ativos; reiniciar a API limpa a amostra. As mensagens originais permanecem nas filas de negócio e na DLQ.</p>
        <p v-if="samplesFailed" role="alert" class="feedback">Não foi possível atualizar as mensagens. A consulta será repetida automaticamente. {{ samples ? 'Última consulta bem-sucedida abaixo; a situação atual não está confirmada.' : 'Nenhuma amostra disponível.' }}</p>
        <p v-if="loading && !samples" role="status">Consultando mensagens…</p>
        <template v-if="samples">
          <p role="status">{{ samples.connected ? 'Observador conectado.' : 'Observador desconectado. A situação atual não está confirmada.' }}</p>
          <p v-if="observationStale" role="status" class="feedback">Observação desatualizada: nenhum evento recente confirmado nos seus ambientes.</p>
          <p class="sample-age">Consulta de <time :datetime="samples.sampled_at">{{ formatTime(samples.sampled_at) }}</time><template v-if="samples.last_observed_at"> · última observação em <time :datetime="samples.last_observed_at">{{ formatTime(samples.last_observed_at) }}</time></template></p>
          <section v-for="section in sampleSections" :key="section.id" :aria-labelledby="`${section.id}-title`" class="sample-section">
            <h3 :id="`${section.id}-title`">{{ section.title }}</h3>
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
          </section>
        </template>
      </section>
      <section class="panel" aria-labelledby="writer-title">
        <h2 id="writer-title">Ensaio de parada do gravador</h2>
        <p>A parada e a retomada do gravador são feitas manualmente no terminal, seguindo o runbook local. Com a publicação ativa, confira o aumento de mensagens prontas em coldsafe.writer durante a parada e o esvaziamento após retomar.</p>
        <p>Zero consumidores não comprova que o gravador está parado: ele consulta a fila periodicamente. Confirme o estado do serviço no terminal.</p>
      </section>
      </template>
    </div>
  </main>
</template>

<style scoped>
.messaging { min-height: 100vh; background: var(--cs-color-canvas); color: var(--cs-color-ink); padding: var(--cs-space-48); }
.shell { max-width: 1280px; margin: 0 auto; min-width: 0; }
.nav { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.brand { font-size: var(--cs-type-20); font-weight: 700; }
.nav nav { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); font-size: var(--cs-type-14); }
.nav a, .sign-out { display: inline-flex; align-items: center; min-height: 44px; }
.nav a:hover, .sign-out:hover { text-decoration: underline; }
.sign-out { cursor: pointer; color: var(--cs-color-accent); }
.heading { padding-block: var(--cs-space-32); }
.eyebrow { color: var(--cs-color-ink-muted); text-transform: uppercase; font-size: var(--cs-type-12); letter-spacing: .08em; }
h1 { font-size: var(--cs-type-32); font-weight: 700; margin-block: var(--cs-space-8); }
h2 { font-size: var(--cs-type-20); font-weight: 600; margin-bottom: var(--cs-space-16); }
.panel { border: 1px solid var(--cs-color-line); background: var(--cs-color-surface); padding: var(--cs-space-24); border-radius: var(--cs-radius-panel); min-width: 0; }
p { line-height: 1.6; }
.panel + .panel { margin-top: var(--cs-space-24); }
h3 { font-size: var(--cs-type-16); font-weight: 600; margin-bottom: var(--cs-space-16); }
.sample-section { margin-top: var(--cs-space-24); }
.samples { display: grid; gap: var(--cs-space-16); list-style: decimal; padding-left: var(--cs-space-24); }
.samples li { min-width: 0; padding: var(--cs-space-16); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); overflow-wrap: anywhere; }
dl { margin-top: var(--cs-space-8); font-size: var(--cs-type-14); }
dl div { display: flex; flex-wrap: wrap; gap: var(--cs-space-8); }
dt { font-weight: 600; }
dd { min-width: 0; }
.feedback, .sample-age { margin-block: var(--cs-space-16); }
.feedback { color: var(--cs-color-status-critical); }
.table-scroll { max-width: 100%; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: var(--cs-type-14); }
th, td { padding: var(--cs-space-16); border-bottom: 1px solid var(--cs-color-line); white-space: nowrap; }
th { font-weight: 600; }
@media (max-width: 800px) {
  .messaging { padding: var(--cs-space-24); }
  .nav { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--cs-space-8); }
  .nav nav { grid-column: 1 / -1; grid-row: 2; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .nav nav a { min-width: 0; overflow-wrap: anywhere; }
  .panel { padding: var(--cs-space-16); }
  h1 { font-size: var(--cs-type-24); }
}
</style>
