<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { clearSession, sessionToken } from '../features/account/session'
import { askAssistant, AssistantRequestError, fetchLlmStatus, type LlmState } from '../features/assistant/assistant-api'

type Turn = Readonly<{ id: number; question: string; answer: string; state: 'responding' | 'complete' | 'incomplete' }>
const router = useRouter()
const question = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const leaveDialog = ref<HTMLDialogElement | null>(null)
let leaveDecision: ((leave: boolean) => void) | undefined
function resolveLeave(leave: boolean) {
  const finish = leaveDecision
  leaveDecision = undefined
  leaveDialog.value?.close()
  finish?.(leave)
}
onBeforeRouteLeave((to) => {
  if (!responding.value || !sessionToken.value || accessDenied.value || to.name === 'login') return true
  resolveLeave(false)
  return new Promise<boolean>((resolve) => {
    leaveDecision = resolve
    void nextTick(() => { if (leaveDecision === resolve) leaveDialog.value?.showModal() })
  })
})
const turns = ref<Turn[]>([])
const modelState = ref<LlmState>('loading')
const responding = ref(false)
const accessDenied = ref(false)
const notice = ref('')
const inputError = ref('')
const cooldownUntil = ref(0)
const now = ref(Date.now())
const questionLimit = 256
const bytes = computed(() => new TextEncoder().encode(question.value).length)
const overLimit = computed(() => bytes.value > questionLimit)
const questionError = computed(() => overLimit.value
  ? `A pergunta passou de ${questionLimit} bytes. Encurte o texto para enviar.`
  : inputError.value)
const cooldown = computed(() => Math.max(0, Math.ceil((cooldownUntil.value - now.value) / 1000)))
const canSend = computed(() => Boolean(sessionToken.value) && !accessDenied.value && modelState.value === 'ready' && !responding.value &&
  cooldown.value === 0 && Boolean(question.value.trim()) && !overLimit.value)
const statusMessages: Record<LlmState, string> = {
  loading: 'Preparando o modelo local. Aguarde o carregamento para perguntar.',
  ready: 'Modelo local pronto. Você já pode perguntar.',
  paused: 'Assistente pausado enquanto a memória está ocupada. Aguarde a liberação e a recarga do modelo.',
  disabled: 'O assistente local não está habilitado. O administrador precisa preparar a configuração.',
  model_missing: 'O modelo local ainda não foi preparado. Solicite o preparo ao administrador.',
  unavailable: 'Assistente local indisponível. O estado será consultado novamente automaticamente.',
}
const status = computed(() => accessDenied.value ? 'Seu acesso ao assistente não está autorizado.' : responding.value ? 'Respondendo…' : cooldown.value > 0
  ? 'Limite de perguntas atingido. Aguarde o prazo indicado antes de tentar novamente.' : statusMessages[modelState.value])
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
  resolveLeave(false)
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
  if (!question.value.trim()) inputError.value = 'Digite uma pergunta.'
  if (questionError.value) {
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
  textarea.value?.focus()
}
function prepare(text: string) { question.value = text; inputError.value = ''; textarea.value?.focus() }
function beforeUnload(event: BeforeUnloadEvent) { event.preventDefault(); event.returnValue = 'true' }
watch(responding, (active) => {
  if (active) window.addEventListener('beforeunload', beforeUnload)
  else window.removeEventListener('beforeunload', beforeUnload)
}, { flush: 'sync' })
watch(accessDenied, (denied) => { if (denied) resolveLeave(false) }, { flush: 'sync' })
onUnmounted(() => {
  alive = false; revision += 1; generation?.abort(); clearInterval(clock)
  resolveLeave(false); window.removeEventListener('beforeunload', beforeUnload)
})
</script>

<template>
  <main class="assistant cs-controls">
    <div class="shell">
      <h1 id="assistant-title" tabindex="-1">Assistente</h1>
      <div class="workspace">
        <form class="panel composer" aria-label="Perguntar ao assistente" @submit.prevent="send">
          <p class="model-status" :class="accessDenied ? 'error' : responding ? 'responding' : cooldown ? 'paused' : modelState" role="status" aria-live="polite">{{ status }}</p>
          <p id="assistant-scope" class="account-scope">A resposta usa um resumo dos dados autorizados da sua conta. A seleção de equipamento no Monitoramento não é usada aqui.</p>
          <div class="questions">
            <h2>Sugestões de perguntas</h2>
            <p class="field-help">Escolha uma sugestão para preencher o campo. Revise a pergunta antes de enviar.</p>
            <ul>
              <li v-for="suggestion in suggestions" :key="suggestion.label">
                <button type="button" data-testid="suggestion" :disabled="responding" @click="prepare(suggestion.question)">{{ suggestion.label }}</button>
              </li>
            </ul>
          </div>
          <label for="assistant-question">Sua pergunta</label>
          <textarea id="assistant-question" ref="textarea" v-model="question" name="question" rows="3" :readonly="responding"
            :aria-describedby="`assistant-scope assistant-history question-limit${questionError ? ' question-error' : ''}`"
            :aria-invalid="questionError ? 'true' : undefined" @input="inputError = ''" />
          <p id="question-limit" class="field-help">
            <strong>{{ bytes }} / {{ questionLimit }} bytes UTF-8.</strong> Acentos e emojis podem ocupar mais de um byte.
          </p>
          <p v-if="questionError" id="question-error" role="alert" class="field-error">{{ questionError }}</p>
          <p class="field-help">As perguntas são registradas na auditoria local. Não inclua senhas ou segredos.</p>
          <p class="field-help">Até 5 perguntas por minuto.</p>
          <p v-if="cooldown" class="field-help">Aguarde {{ cooldown }} s antes de tentar novamente.</p>
          <div class="actions">
            <button type="submit" class="primary" :disabled="!canSend">Enviar pergunta</button>
            <button v-if="responding" type="button" data-testid="cancel" @click="cancel">Cancelar resposta</button>
          </div>
        </form>
        <section v-if="turns.length" class="panel conversation" aria-label="Conversa com o assistente">
          <h2>Conversa</h2>
          <p v-if="notice" role="status" class="notice">{{ notice }}</p>
          <ol aria-label="Conversa desta sessão">
            <li v-for="turn in turns" :key="turn.id" class="turn">
              <h3>Sua pergunta</h3><p class="plain-text">{{ turn.question }}</p>
              <h3>Assistente</h3>
              <p v-if="turn.answer" data-testid="answer" class="plain-text">{{ turn.answer }}</p>
              <p v-else>{{ turn.state === 'responding' ? 'Aguardando a primeira parte da resposta…' : 'Nenhuma resposta recebida.' }}</p>
              <p class="turn-state" :class="turn.state">{{ turn.state === 'responding' ? 'Resposta em andamento' : turn.state === 'complete' ? 'Resposta concluída' : 'Resposta incompleta' }}</p>
            </li>
          </ol>
        </section>
        <aside class="panel limits" aria-labelledby="assistant-limits">
          <h2 id="assistant-limits">Privacidade e limites</h2>
          <p id="assistant-history">A conversa guarda até oito perguntas nesta página. Ao sair ou trocar de conta, ela é apagada, inclusive respostas concluídas.</p>
          <p>Cada pergunta é independente. As anteriores não são enviadas ao modelo.</p>
          <p>O modelo não consulta os bancos de dados nem executa comandos. Respostas podem conter erros.</p>
          <p>Saúde e vida útil restante são estimativas sintéticas, sem calibração física. Confirme os dados em <RouterLink to="/insights">Saúde e previsões</RouterLink>.</p>
        </aside>
      </div>
    </div>
    <Teleport to="body">
      <dialog ref="leaveDialog" class="leave-dialog cs-controls" aria-labelledby="assistant-leave-title" aria-describedby="assistant-leave-description" @cancel.prevent="resolveLeave(false)">
        <h2 id="assistant-leave-title">Sair e apagar a conversa?</h2>
        <p id="assistant-leave-description">Sair interrompe a resposta que ainda estiver chegando e apaga a conversa, inclusive respostas concluídas.</p>
        <div class="actions">
          <button type="button" autofocus @click="resolveLeave(false)">Permanecer</button>
          <button type="button" @click="resolveLeave(true)">Sair do assistente</button>
        </div>
      </dialog>
    </Teleport>
  </main>
</template>

<style scoped>
.assistant { padding: var(--cs-space-48); }
.shell { max-width: 1200px; margin-inline: auto; display: grid; gap: var(--cs-space-24); min-width: 0; }
h1 { font-size: var(--cs-type-32); } h2 { font-size: var(--cs-type-20); } h3 { margin-top: var(--cs-space-16); font-weight: 600; }
p { margin-top: var(--cs-space-12); line-height: 1.6; overflow-wrap: anywhere; }
.account-scope { max-width: 70ch; }
a { color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
.model-status { display: inline-block; margin-top: 0; padding: var(--cs-space-8) var(--cs-space-12); border-radius: var(--cs-radius-4); font-weight: 600; color: var(--cs-color-status-stale); background: var(--cs-color-stale-surface); }
.model-status.ready { color: var(--cs-color-status-normal); background: var(--cs-color-normal-surface); }.model-status.responding { color: var(--cs-color-accent); background: var(--cs-color-surface-muted); }.model-status.error { color: var(--cs-color-status-critical); background: var(--cs-color-critical-surface); }
.workspace { display: grid; grid-template-columns: minmax(0, 1fr) 300px; align-items: start; gap: var(--cs-space-24); }
.panel { min-width: 0; padding: var(--cs-space-24); background: var(--cs-color-surface); border-radius: var(--cs-radius-panel); }
.composer, .conversation { grid-column: 1; }
.limits { grid-column: 2; grid-row: 1; }
.notice { color: var(--cs-color-ink-muted); }
.turn { padding-block: var(--cs-space-16) var(--cs-space-24); border-bottom: 1px solid var(--cs-color-line); }.turn:last-child { padding-bottom: 0; border-bottom: 0; }
.plain-text { white-space: pre-wrap; overflow-wrap: anywhere; max-width: 72ch; }
.turn-state, .field-help { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }.turn-state { display: inline-block; margin-top: var(--cs-space-16); font-weight: 600; padding: var(--cs-space-4) var(--cs-space-8); border-radius: var(--cs-radius-4); }.turn-state.incomplete { color: var(--cs-color-status-attention); background: var(--cs-color-attention-surface); }.turn-state.complete { color: var(--cs-color-status-normal); background: var(--cs-color-normal-surface); }
label { display: block; margin-bottom: var(--cs-space-8); }
textarea { width: 100%; min-width: 0; resize: vertical; padding: var(--cs-space-12); background: var(--cs-color-surface); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); color: var(--cs-color-ink); caret-color: var(--cs-color-accent); font: inherit; font-size: var(--cs-type-16); line-height: 1.5; }
textarea[aria-invalid='true'] { border-color: var(--cs-color-status-critical); } textarea:read-only { background: var(--cs-color-surface-muted); }
.actions { display: flex; flex-wrap: wrap; gap: var(--cs-space-12); margin-top: var(--cs-space-16); }
.questions { margin-block: var(--cs-space-24); }
.questions h2 { font-size: var(--cs-type-16); }
.questions p { margin-top: var(--cs-space-4); }
.questions ul { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr)); gap: var(--cs-space-8); margin-top: var(--cs-space-12); }
.questions button { text-align: left; width: 100%; height: 100%; }
.limits p { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.leave-dialog { width: min(100% - 32px, 520px); max-width: none; max-height: calc(100dvh - 32px); margin: auto; padding: var(--cs-space-24); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); color: var(--cs-color-ink); overflow-y: auto; overflow-wrap: anywhere; }
.leave-dialog::backdrop { background: rgb(8 27 32 / .55); }.leave-dialog h2 { font-size: var(--cs-type-24); }.leave-dialog .actions { margin-top: var(--cs-space-24); }.leave-dialog button { flex: 1 1 180px; }
::selection { background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
@media (max-width: 1100px) {
  .assistant { padding: var(--cs-space-16); }
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .limits { grid-area: auto; }
  .panel { padding: var(--cs-space-16); } h1 { font-size: var(--cs-type-24); line-height: 1.3333; }
}
@media (max-width: 600px) {
  .questions ul { grid-template-columns: repeat(auto-fit, minmax(min(100%, 9rem), 1fr)); }
  .composer .actions button { width: 100%; justify-content: center; }
}
</style>
