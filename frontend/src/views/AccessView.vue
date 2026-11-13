<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { safeInternalRedirect } from '../router/redirect'
import { login, register } from '../features/account/session'

const router = useRouter()
const route = useRoute()
const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const invalidField = ref<'email' | 'password' | null>(null)
const passwordInput = ref<HTMLInputElement | null>(null)
const title = ref<HTMLElement | null>(null)
const passwordInvalid = computed(() => Boolean(error.value && invalidField.value === 'password'))

function invalid(event: Event) {
  const input = event.target as HTMLInputElement
  if (input !== input.form?.querySelector(':invalid')) return
  invalidField.value = input.id as 'email' | 'password'
  error.value = input.id === 'email' ? 'Informe um email válido.'
    : mode.value === 'register' ? 'A senha precisa ter ao menos 8 caracteres.' : 'Informe sua senha.'
  input.focus()
}

function clearValidation() {
  if (!invalidField.value) return
  error.value = ''
  invalidField.value = null
}

async function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
  invalidField.value = null
  await nextTick()
  title.value?.focus()
}

async function submit() {
  if (busy.value) return
  error.value = ''
  invalidField.value = null
  if (mode.value === 'register' && password.value.length < 8) {
    error.value = 'A senha precisa ter ao menos 8 caracteres.'
    invalidField.value = 'password'
    passwordInput.value?.focus()
    return
  }
  if (mode.value === 'register' && new TextEncoder().encode(password.value).length > 72) {
    error.value = 'A senha de cadastro deve ter até 72 bytes UTF-8. Reduza o tamanho da senha.'
    invalidField.value = 'password'
    passwordInput.value?.focus()
    return
  }
  const redirect = safeInternalRedirect(route.query.redirect)
  busy.value = true
  try {
    if (mode.value === 'register') await register(email.value.trim(), password.value)
    await login(email.value.trim(), password.value)
    await router.push(redirect)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Não foi possível acessar sua conta.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="access-page cs-controls">
    <header class="access-header">
      <p class="brand">ColdSafe</p>
      <RouterLink to="/" class="return-link">Voltar à apresentação</RouterLink>
    </header>
    <div class="form-region">
      <section class="panel" aria-labelledby="access-title">
        <h1 id="access-title" ref="title" tabindex="-1">{{ mode === 'login' ? 'Entrar' : 'Criar conta' }}</h1>
        <form :aria-busy="busy" :aria-describedby="error ? 'access-error' : undefined" @submit.prevent="submit" @invalid.capture.prevent="invalid">
          <div class="field">
            <label for="email">Email</label>
            <input id="email" v-model.trim="email" name="email" type="email" autocomplete="username" autocapitalize="none" :spellcheck="false" maxlength="254" required :disabled="busy" :aria-invalid="invalidField === 'email' || undefined" :aria-describedby="invalidField === 'email' ? 'access-error' : undefined" @input="clearValidation" />
          </div>
          <div class="field">
            <label for="password">Senha</label>
            <input id="password" ref="passwordInput" v-model="password" name="password" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" :minlength="mode === 'register' ? 8 : 1" :aria-invalid="passwordInvalid || undefined" :aria-describedby="passwordInvalid ? 'access-error' : mode === 'register' ? 'password-hint' : undefined" maxlength="128" required :disabled="busy" @input="clearValidation" />
            <template v-if="mode === 'register'">
              <p id="password-hint" class="hint">Use ao menos 8 caracteres.</p>
              <details class="password-details">
                <summary>Sobre o limite da senha</summary>
                <p class="hint">O limite é de 72 bytes em UTF-8. Letras com acento e emojis podem ocupar mais de um byte.</p>
              </details>
            </template>
          </div>
          <p v-if="error" id="access-error" role="alert" class="feedback error">{{ error }}</p>
          <button class="primary" type="submit" :disabled="busy">{{ busy ? (mode === 'login' ? 'Entrando…' : 'Criando conta…') : mode === 'login' ? 'Entrar' : 'Criar conta e entrar' }}</button>
        </form>
        <div class="mode-choice">
          <p>{{ mode === 'login' ? 'Ainda não tem conta?' : 'Já tem conta?' }}</p>
          <button class="mode-switch" type="button" :disabled="busy" @click="switchMode">{{ mode === 'login' ? 'Criar conta' : 'Entrar' }}</button>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.access-page { display: grid; grid-template-rows: auto 1fr; min-height: 100vh; min-height: 100svh; }
.access-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-4) var(--cs-space-24); padding: var(--cs-space-12) var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); background: var(--cs-color-surface); }
.brand { margin: 0; font-size: var(--cs-type-24); font-weight: 650; letter-spacing: -.025em; }
.return-link { display: inline-flex; align-items: center; min-height: var(--cs-control-min-height); color: var(--cs-color-accent); font-size: var(--cs-type-14); text-decoration: underline; text-underline-offset: .2em; }
.form-region { display: grid; place-items: center; padding: var(--cs-space-32) var(--cs-space-24) var(--cs-space-64); }
.panel { width: 100%; max-width: 30rem; min-width: 0; padding: var(--cs-space-32); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-16); background: var(--cs-color-surface); box-shadow: var(--cs-shadow-panel); }
h1 { margin: 0 0 var(--cs-space-32); font-size: var(--cs-type-32); }
form { display: grid; gap: var(--cs-space-24); }
.field { display: grid; gap: var(--cs-space-8); min-width: 0; }
.hint { margin: 0; }
.password-details { font-size: var(--cs-type-14); }
.password-details summary { width: fit-content; min-height: var(--cs-control-min-height); padding-block: var(--cs-space-12); color: var(--cs-color-accent); cursor: pointer; }
.password-details .hint { margin-top: var(--cs-space-8); }
.feedback { margin: 0; }
.mode-choice { display: flex; flex-wrap: wrap; align-items: center; gap: 0 var(--cs-space-12); margin-top: var(--cs-space-24); padding-top: var(--cs-space-8); border-top: 1px solid var(--cs-color-line); }
.mode-choice p { margin: 0; color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.mode-switch { padding-inline: 0; border-color: transparent; background: transparent; color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; text-align: left; }
@media (max-width: 480px) {
  .access-header { padding-inline: var(--cs-space-16); }
  .form-region { align-items: start; padding: var(--cs-space-24) var(--cs-space-16); }
  .panel { padding: var(--cs-space-16); }
}
</style>
