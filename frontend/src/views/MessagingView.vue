<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { clearSession, logout, refreshSessionIdentity, sessionRole, sessionToken } from '../features/account/session'
import { fetchMessaging, MessagingAccessError, type MessagingSnapshot } from '../features/messaging/messaging-api'

const router = useRouter()
const snapshot = ref<MessagingSnapshot | null>(null)
const loading = ref(false)
const failed = ref(false)
const logoutError = ref('')
const now = ref(Date.now())
const authorized = computed(() => Boolean(sessionToken.value) && sessionRole.value === 'admin')
const ageSeconds = computed(() => snapshot.value
  ? Math.max(0, Math.floor((now.value - Date.parse(snapshot.value.sampled_at)) / 1000)) : null)
const stale = computed(() => ageSeconds.value !== null && ageSeconds.value >= 15)
const ageTimer = setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(ageTimer))

watch([sessionToken, sessionRole], ([token, role], _previous, onCleanup) => {
  snapshot.value = null
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
      const result = await fetchMessaging(token!, controller.signal)
      if (!active) return
      snapshot.value = result
      now.value = Date.now()
      failed.value = false
    } catch (cause) {
      if (!active) return
      if (cause instanceof MessagingAccessError) {
        snapshot.value = null
        if (cause.status === 401) clearSession()
        else void refreshSessionIdentity().catch(() => { /* Unknown permissions keep metrics hidden. */ })
        return
      }
      failed.value = true
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
          <RouterLink to="/manage">Ambientes e dispositivos</RouterLink>
          <RouterLink to="/messaging" aria-current="page">Mensageria</RouterLink>
        </nav>
        <button class="sign-out" type="button" @click="signOut">Sair</button>
      </header>
      <p v-if="logoutError" role="alert" class="feedback">{{ logoutError }}</p>
      <section class="heading" aria-labelledby="messaging-title">
        <p class="eyebrow">Operação</p>
        <h1 id="messaging-title" tabindex="-1">Mensageria</h1>
        <p>Filas, taxas e consumidores da infraestrutura compartilhada. Acesso administrativo; este painel agrega a operação global e não exibe conteúdo de mensagens.</p>
      </section>
      <p v-if="!authorized" role="status">As métricas de mensageria estão disponíveis apenas para administradores. Consulte o monitoramento para ver seus ambientes.</p>
      <section v-else class="panel" aria-labelledby="queues-title">
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
