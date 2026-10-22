<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { clearSession, logout, sessionToken } from '../features/account/session'
import { askAssistant, AssistantRequestError, fetchLlmStatus, type LlmState } from '../features/assistant/assistant-api'

type Turn = Readonly<{ id: number; question: string; answer: string; state: 'responding' | 'complete' | 'incomplete' }>
const router = useRouter()
const question = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const turns = ref<Turn[]>([])
const modelState = ref<LlmState>('loading')
const responding = ref(false)
const accessDenied = ref(false)
const notice = ref('')
const inputError = ref('')
const cooldownUntil = ref(0)
const now = ref(Date.now())
const bytes = computed(() => new TextEncoder().encode(question.value).length)
const cooldown = computed(() => Math.max(0, Math.ceil((cooldownUntil.value - now.value) / 1000)))
const canSend = computed(() => Boolean(sessionToken.value) && !accessDenied.value && modelState.value === 'ready' && !responding.value &&
  cooldown.value === 0 && Boolean(question.value.trim()) && bytes.value <= 256)
const statusMessages: Record<LlmState, string> = {
  loading: 'Preparando o modelo local. Aguarde o carregamento para perguntar.',
  ready: 'Modelo local pronto. Você já pode perguntar.',
  paused: 'Assistente pausado enquanto a memória está ocupada. Aguarde a liberação e a recarga do modelo.',
  disabled: 'O assistente local não está habilitado. O administrador precisa preparar a configuração.',
  model_missing: 'O modelo local ainda não foi preparado. Solicite o preparo ao administrador.',
  unavailable: 'Assistente local indisponível. O estado será consultado novamente automaticamente.',
}
const status = computed(() => accessDenied.value ? 'Seu acesso ao assistente não está autorizado.' : responding.value ? 'Respondendo…' : cooldown.value > 0
  ? `Limite de perguntas atingido. Aguarde ${cooldown.value} s antes de tentar novamente.` : statusMessages[modelState.value])
const suggestions = [
  { label: 'Estado atual', question: 'Qual é o estado atual dos equipamentos da minha conta?' },
  { label: 'Pior equipamento', question: 'Qual equipamento tem a pior saúde ou menor vida útil restante?' },
  { label: 'Vida útil restante', question: 'Qual é a vida útil restante (RUL), em horas, e quais são suas limitações?' },
  { label: 'Significado dos alertas', question: 'O que significam os alertas térmicos e preditivos da minha conta?' },
  { label: 'Métricas do modelo', question: 'Quais são as métricas de teste do modelo ativo e suas limitações?' },
  { label: 'Arquitetura', question: 'Como funciona a arquitetura do ColdSafe, dos sensores ao assistente local?' },
]
let alive = true
let revision = 0
let generation: AbortController | null = null
let statusController: AbortController | null = null
let pollCurrent = () => {}
const clock = setInterval(() => { now.value = Date.now() }, 1000)

function current(token: string, id: number) { return alive && sessionToken.value === token && revision === id }
function updateTurn(id: number, change: Partial<Turn>) {
  turns.value = turns.value.map((turn) => turn.id === id ? { ...turn, ...change } : turn)
}
function unauthorized(error: unknown, token: string): boolean {
  if (!(error instanceof AssistantRequestError) || (error.status !== 401 && error.code !== 'UNAUTHORIZED')) return false
  if (sessionToken.value === token) clearSession()
  return true
}
function errorMessage(error: unknown): string {
  if (!(error instanceof AssistantRequestError)) return 'A resposta foi interrompida. Confira a conexão e tente novamente quando o modelo estiver pronto.'
  const messages: Record<string, string> = {
    LLM_BUSY: 'A memória do assistente está ocupada. Aguarde e tente novamente quando o modelo estiver pronto.',
    LLM_NOT_READY: 'O modelo local ainda está sendo preparado. Aguarde e tente novamente.',
    LLM_DISABLED: 'O assistente local não está habilitado. Solicite a configuração ao administrador.',
    LLM_UNAVAILABLE: 'O assistente local está indisponível. Aguarde e tente novamente.',
    LLM_TIMEOUT: 'O assistente excedeu o tempo de resposta. Tente uma pergunta mais curta quando estiver pronto.',
    RATE_LIMITED: 'Limite de perguntas atingido. Aguarde o prazo indicado antes de enviar outra pergunta.',
    VALIDATION_ERROR: 'A API recusou a pergunta. Use de 1 a 256 bytes UTF-8 e tente novamente.',
  }
  return messages[error.code] ?? 'A resposta foi interrompida. O texto recebido está incompleto; você pode tentar novamente.'
}

watch(sessionToken, (token, _old, onCleanup) => {
  let active = true
  let allowed = true
  let timer: ReturnType<typeof setTimeout> | undefined
  let cancelPendingStatus = () => {}
  revision += 1
  generation?.abort(); generation = null
  statusController?.abort(); statusController = null
  responding.value = false
  accessDenied.value = false
  question.value = ''; turns.value = []; notice.value = ''; inputError.value = ''; cooldownUntil.value = 0
  modelState.value = 'loading'
  onCleanup(() => { active = false; clearTimeout(timer); cancelPendingStatus() })
  if (!token) { pollCurrent = () => {}; void router.replace('/login'); return }
  async function poll() {
    if (!active || !allowed || accessDenied.value || responding.value || statusController) return
    const controller = new AbortController()
    statusController = controller
    const deadline = setTimeout(() => controller.abort(), 4000)
    cancelPendingStatus = () => { clearTimeout(deadline); controller.abort() }
    try {
      const state = await fetchLlmStatus(token!, controller.signal)
      if (active && !responding.value && statusController === controller) modelState.value = state
    } catch (error) {
      if (!active || responding.value || statusController !== controller) return
      if (unauthorized(error, token!)) return
      if (error instanceof AssistantRequestError && error.status === 403) {
        allowed = false; accessDenied.value = true; modelState.value = 'disabled'; turns.value = []; question.value = ''
      } else modelState.value = 'unavailable'
    } finally {
      clearTimeout(deadline)
      const latest = statusController === controller
      if (latest) statusController = null
      if (active && allowed && latest && !accessDenied.value && !responding.value) timer = setTimeout(() => { void poll() }, 2000)
    }
  }
  pollCurrent = () => { clearTimeout(timer); void poll() }
  void poll()
}, { immediate: true, flush: 'sync' })

async function send() {
  inputError.value = ''
  if (!question.value.trim() || bytes.value > 256) {
    inputError.value = 'Digite uma pergunta de 1 a 256 bytes UTF-8. Acentos e emojis podem ocupar mais de um byte.'
    textarea.value?.focus(); return
  }
  const token = sessionToken.value
  if (!token || !canSend.value) return
  const id = ++revision
  const controller = new AbortController()
  generation = controller
  responding.value = true; notice.value = ''
  statusController?.abort(); statusController = null
  const text = question.value
  turns.value = [...turns.value.slice(-7), { id, question: text, answer: '', state: 'responding' }]
  try {
    await askAssistant(token, text, (delta) => {
      if (!current(token, id)) return
      turns.value = turns.value.map((turn) => turn.id === id ? { ...turn, answer: turn.answer + delta } : turn)
    }, controller.signal)
    if (!current(token, id)) return
    updateTurn(id, { state: 'complete' }); question.value = ''
    notice.value = 'Resposta concluída. Confira os valores nos painéis de monitoramento e Insights.'
  } catch (error) {
    if (!current(token, id)) return
    if (unauthorized(error, token)) return
    updateTurn(id, { state: 'incomplete' })
    notice.value = errorMessage(error)
    if (error instanceof AssistantRequestError && error.status === 429) {
      now.value = Date.now(); cooldownUntil.value = now.value + (error.retryAfterSeconds ?? 60) * 1000
    }
    if (error instanceof AssistantRequestError && error.status === 403) {
      accessDenied.value = true; turns.value = []; question.value = ''; notice.value = ''
    }
  } finally {
    if (current(token, id)) { responding.value = false; generation = null; modelState.value = 'loading'; pollCurrent() }
  }
}
function cancel() {
  if (!responding.value) return
  updateTurn(revision, { state: 'incomplete' })
  revision += 1; generation?.abort(); generation = null; responding.value = false
  notice.value = 'Geração cancelada. O texto recebido é incompleto. Aguarde o modelo ficar pronto antes de tentar novamente.'
  modelState.value = 'loading'; pollCurrent()
}
function prepare(text: string) { question.value = text; inputError.value = ''; textarea.value?.focus() }
async function signOut() {
  const token = sessionToken.value
  try { await logout() } catch { if (sessionToken.value === token) notice.value = 'Não foi possível encerrar a sessão. Tente novamente.' }
}
onUnmounted(() => { alive = false; revision += 1; generation?.abort(); clearInterval(clock) })
</script>

<template>
  <main class="assistant">
    <a class="skip-link" href="#assistant-title">Ir para o conteúdo</a>
    <div class="shell">
      <header class="nav">
        <RouterLink to="/" class="brand">ColdSafe</RouterLink>
        <nav aria-label="Navegação principal">
          <RouterLink to="/dashboard">Monitoramento</RouterLink><RouterLink to="/insights">Insights</RouterLink>
          <RouterLink to="/digital-twin">Gêmeo digital</RouterLink><RouterLink to="/manage">Ambientes e dispositivos</RouterLink>
          <RouterLink to="/messaging">Mensageria</RouterLink><RouterLink to="/laboratory">Laboratório</RouterLink>
          <RouterLink to="/training">Treinamento</RouterLink><RouterLink to="/assistant" aria-current="page">Assistente</RouterLink>
        </nav>
        <button type="button" @click="signOut">Sair</button>
      </header>
      <section class="heading">
        <h1 id="assistant-title" tabindex="-1">Assistente</h1>
        <p>Pergunte sobre os equipamentos da sua conta. O backend prepara um resumo limitado dos dados autorizados; o modelo local não consulta os bancos nem executa comandos.</p>
      </section>
      <div class="workspace">
        <section class="panel conversation" aria-label="Conversa com o assistente">
          <h2>Entenda os dados da sua conta</h2>
          <p class="model-status" role="status" aria-live="polite">{{ status }}</p>
          <p v-if="notice" role="status" class="notice">{{ notice }}</p>
          <ol v-if="turns.length" aria-label="Conversa desta sessão">
            <li v-for="turn in turns" :key="turn.id" class="turn">
              <h3>Sua pergunta</h3><p class="plain-text">{{ turn.question }}</p>
              <h3>Assistente</h3>
              <p v-if="turn.answer" data-testid="answer" class="plain-text">{{ turn.answer }}</p>
              <p v-else>{{ turn.state === 'responding' ? 'Aguardando a primeira parte da resposta…' : 'Nenhuma resposta recebida.' }}</p>
              <p class="turn-state">{{ turn.state === 'responding' ? 'Resposta em andamento' : turn.state === 'complete' ? 'Resposta concluída' : 'Resposta incompleta' }}</p>
            </li>
          </ol>
          <p v-else class="empty">Ainda não há perguntas nesta página. Escolha uma sugestão ou escreva sua pergunta abaixo.</p>
          <form aria-label="Perguntar ao assistente" @submit.prevent="send">
            <label for="assistant-question">Sua pergunta</label>
            <textarea id="assistant-question" ref="textarea" v-model="question" name="question" rows="3" :readonly="responding"
              :aria-describedby="inputError ? 'question-limit question-error' : 'question-limit'" :aria-invalid="inputError || bytes > 256 ? 'true' : undefined" />
            <p id="question-limit" class="field-help">{{ bytes }} / 256 bytes UTF-8 · Até 5 perguntas por minuto.</p>
            <p v-if="inputError" id="question-error" role="alert">{{ inputError }}</p>
            <div class="actions">
              <button type="submit" class="primary" :disabled="!canSend">Enviar pergunta</button>
              <button v-if="responding" type="button" data-testid="cancel" @click="cancel">Cancelar resposta</button>
            </div>
          </form>
        </section>
        <aside class="panel questions" aria-label="Perguntas sugeridas e limites">
          <h2>Por onde começar</h2>
          <ul><li v-for="suggestion in suggestions" :key="suggestion.label"><button type="button" data-testid="suggestion" :disabled="responding" @click="prepare(suggestion.question)">{{ suggestion.label }}</button></li></ul>
          <p>Cada pergunta é independente. As anteriores não são enviadas ao modelo.</p>
          <p>A conversa fica somente nesta página, com até oito perguntas. Ao sair ou trocar de conta, ela é apagada.</p>
          <p>As perguntas são registradas na auditoria local. Não inclua senhas ou segredos.</p>
          <p>Respostas podem conter erros. Saúde e RUL são estimativas sintéticas, sem calibração física. Confirme os dados em <RouterLink to="/insights">Insights</RouterLink>.</p>
        </aside>
      </div>
    </div>
  </main>
</template>

<style scoped>
.assistant { min-height: 100vh; padding: var(--cs-space-48); color: var(--cs-color-ink); background: var(--cs-color-canvas); }
.shell { max-width: 1280px; margin: auto; display: grid; gap: var(--cs-space-24); min-width: 0; }
.nav { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.brand { font-weight: 700; }.nav nav { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); font-size: var(--cs-type-14); }
a, button { color: var(--cs-color-accent); }button { cursor: pointer; }.nav a, button { display: inline-flex; align-items: center; min-height: 44px; }button:disabled { opacity: .6; cursor: not-allowed; }
a:hover, button:hover:not(:disabled) { text-decoration: underline; }a { text-underline-offset: .2em; }
:is(a, button, textarea):focus-visible { outline: 2px solid var(--cs-focus-ring); outline-offset: 3px; }
h1 { font-size: var(--cs-type-32); font-weight: 600; }h2 { font-size: var(--cs-type-20); font-weight: 600; }h3 { margin-top: var(--cs-space-16); font-weight: 600; }
p { margin-top: var(--cs-space-12); line-height: 1.7; overflow-wrap: anywhere; }.heading p { max-width: 72ch; }
.workspace { display: grid; grid-template-columns: minmax(0, 1fr) 280px; align-items: start; gap: var(--cs-space-24); }.panel { min-width: 0; padding: var(--cs-space-24); background: var(--cs-color-surface); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); }
.model-status { font-weight: 600; }.notice, [role=alert] { color: var(--cs-color-status-attention); }.empty { margin-block: var(--cs-space-32); color: var(--cs-color-ink-muted); }
.turn { padding-block: var(--cs-space-16) var(--cs-space-24); border-bottom: 1px solid var(--cs-color-line); }.plain-text { white-space: pre-wrap; overflow-wrap: anywhere; max-width: 72ch; }.turn-state, .field-help { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }.turn-state { margin-top: var(--cs-space-16); }
form { margin-top: var(--cs-space-32); }label { display: block; font-weight: 600; margin-bottom: var(--cs-space-8); }textarea { width: 100%; min-width: 0; resize: vertical; padding: var(--cs-space-12); background: var(--cs-color-canvas); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); color: inherit; caret-color: var(--cs-color-accent); line-height: 1.6; }
.actions { display: flex; flex-wrap: wrap; gap: var(--cs-space-16); margin-top: var(--cs-space-16); }.actions button { padding: var(--cs-space-8) var(--cs-space-16); border: 1px solid var(--cs-color-accent); border-radius: var(--cs-radius-4); }.primary { color: var(--cs-color-accent-ink); background: var(--cs-color-accent); }
.questions ul { display: grid; gap: var(--cs-space-8); margin-top: var(--cs-space-16); }.questions button { text-align: left; justify-content: flex-start; width: 100%; border-bottom: 1px solid var(--cs-color-line); }.questions p { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.skip-link { position: absolute; transform: translateY(-200%); }.skip-link:focus { transform: none; background: var(--cs-color-surface); padding: var(--cs-space-12); }
::selection { background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
@media (max-width: 900px) { .assistant { padding: var(--cs-space-24); }.workspace { grid-template-columns: minmax(0, 1fr); }.nav { gap: var(--cs-space-8); }.nav nav { order: 3; width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }.nav a { min-width: 0; overflow-wrap: anywhere; }.questions ul { grid-template-columns: repeat(2, minmax(0, 1fr)); }.panel { padding: var(--cs-space-16); }h1 { font-size: var(--cs-type-24); } }
@media (max-width: 420px) { .assistant { padding: var(--cs-space-16); }.questions ul { grid-template-columns: minmax(0, 1fr); }.actions button { width: 100%; justify-content: center; } }
</style>
