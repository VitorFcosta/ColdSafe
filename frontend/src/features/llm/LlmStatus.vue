<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { clearSession, sessionToken } from '../account/session'

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const messages = {
  loading: 'Preparando o modelo local. O carregamento pode levar alguns segundos.',
  ready: 'Modelo local carregado. O Assistente está disponível no menu.',
  paused: 'Modelo local pausado durante geração ou treinamento para liberar memória. Será recarregado automaticamente ao terminar.',
  unavailable: 'Modelo local indisponível. O estado será consultado novamente automaticamente; a geração e o treino aguardam se a liberação de memória não puder ser confirmada.',
  model_missing: 'Modelo local ainda não preparado. O administrador precisa fazer o download inicial antes de usar o assistente.',
}
type State = keyof typeof messages | 'disabled'
const state = ref<State>('disabled')
const message = computed(() => state.value === 'disabled' ? '' : messages[state.value])

watch(sessionToken, (token, _previous, onCleanup) => {
  let active = true
  let timer: ReturnType<typeof setTimeout> | undefined
  let deadline: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  state.value = 'disabled'
  onCleanup(() => { active = false; clearTimeout(timer); clearTimeout(deadline); controller?.abort() })
  if (!token) return
  async function poll() {
    controller = new AbortController()
    deadline = setTimeout(() => controller?.abort(), 4000)
    let retry = true
    try {
      const response = await fetch(`${baseUrl}/api/v3/llm/status`, {
        headers: { authorization: `Bearer ${token}` }, signal: controller.signal,
      })
      if (!active) return
      if (response.status === 401 || response.status === 403) {
        retry = false; state.value = 'disabled'
        if (response.status === 401) clearSession()
        return
      }
      if (!response.ok) throw new Error('LLM status unavailable')
      const result = await response.json()
      if (!active) return
      const next = result?.data?.state
      if (result?.success !== true || result?.meta?.schema_version !== 3 ||
          typeof result?.data?.model !== 'string' || typeof next !== 'string' ||
          (next !== 'disabled' && !Object.hasOwn(messages, next))) throw new Error('Invalid LLM status')
      state.value = next as State
    } catch {
      if (active) state.value = 'unavailable'
    } finally {
      clearTimeout(deadline)
      if (active && retry) timer = setTimeout(() => { void poll() }, 2000)
    }
  }
  void poll()
}, { immediate: true, flush: 'sync' })
</script>

<template>
  <p v-if="message" class="llm-status" role="status" aria-live="polite">{{ message }}</p>
</template>

<style scoped>
.llm-status { padding: var(--cs-space-16); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); line-height: 1.7; overflow-wrap: anywhere; }
</style>
