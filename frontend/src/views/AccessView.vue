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
    <div class="identity presentation-theme">
      <p class="brand">ColdSafe</p>
      <div class="identity-copy">
        <p class="identity-title">Precisão para acompanhar.</p>
        <p>Acesse os dados e as ferramentas autorizadas da sua conta.</p>
      </div>
      <RouterLink to="/" class="return-link">Voltar à apresentação</RouterLink>
    </div>
    <div class="form-region">
      <section class="panel" aria-labelledby="access-title">
        <h1 id="access-title" ref="title" tabindex="-1">{{ mode === 'login' ? 'Entrar' : 'Criar conta' }}</h1>
        <p class="intro">{{ mode === 'login' ? 'Use sua conta para continuar.' : 'Crie sua conta com email e senha para continuar.' }}</p>
        <form :aria-busy="busy" :aria-describedby="error ? 'access-error' : undefined" @submit.prevent="submit" @invalid.capture.prevent="invalid">
          <div class="field">
            <label for="email">Email</label>
            <input id="email" v-model.trim="email" name="email" type="email" autocomplete="username" autocapitalize="none" :spellcheck="false" maxlength="254" required :disabled="busy" :aria-invalid="invalidField === 'email' || undefined" :aria-describedby="invalidField === 'email' ? 'access-error' : undefined" @input="clearValidation" />
          </div>
          <div class="field">
            <label for="password">Senha</label>
            <input id="password" ref="passwordInput" v-model="password" name="password" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" :minlength="mode === 'register' ? 8 : 1" :aria-invalid="passwordInvalid || undefined" :aria-describedby="mode === 'register' ? `password-hint${passwordInvalid ? ' access-error' : ''}` : passwordInvalid ? 'access-error' : undefined" maxlength="128" required :disabled="busy" @input="clearValidation" />
            <p v-if="mode === 'register'" id="password-hint" class="hint">Use ao menos 8 caracteres. O cadastro aceita até 72 bytes UTF-8; acentos e emojis podem ocupar mais de um byte.</p>
          </div>
          <p v-if="error" id="access-error" role="alert" class="feedback error">{{ error }}</p>
          <button class="primary" type="submit" :disabled="busy">{{ busy ? (mode === 'login' ? 'Entrando…' : 'Criando conta…') : mode === 'login' ? 'Entrar' : 'Criar conta e entrar' }}</button>
        </form>
        <div class="mode-choice">
          <p>{{ mode === 'login' ? 'Ainda não tem conta?' : 'Já tem conta?' }}</p>
          <button class="mode-switch" type="button" :disabled="busy" @click="switchMode">{{ mode === 'login' ? 'Criar conta' : 'Entrar' }}</button>
        </div>
        <p class="session-note">Sessão e acesso serão verificados antes de abrir o destino solicitado.</p>
      </section>
    </div>
  </main>
</template>

<style scoped>
.access-page { display: grid; grid-template-columns: 43% minmax(0, 1fr); min-height: 100vh; min-height: 100svh; }
.identity { display: flex; flex-direction: column; gap: var(--cs-space-48); padding: var(--cs-space-64); background: var(--cs-color-canvas); color: var(--cs-color-ink); }
.brand { margin: 0; font-size: var(--cs-type-32); font-weight: 650; }
.identity-copy { margin-block: auto; padding-block: var(--cs-space-48); max-width: 34ch; }
.identity-title { margin: 0 0 var(--cs-space-48); font-size: var(--cs-type-48); font-weight: 650; line-height: 1.2; text-wrap: balance; }
.identity-copy > p:last-child { margin: 0; color: var(--cs-color-ink-muted); }
.return-link { align-self: flex-start; display: inline-flex; align-items: center; min-height: var(--cs-control-min-height); color: var(--cs-color-accent); text-underline-offset: .2em; }
.form-region { display: grid; align-items: center; padding: var(--cs-space-64) var(--cs-space-48); }
.panel { width: 100%; max-width: 31rem; margin-inline: auto; min-width: 0; }
h1 { margin: 0 0 var(--cs-space-16); font-size: var(--cs-type-32); }
.intro { margin: 0; color: var(--cs-color-ink-muted); }
form { display: grid; gap: var(--cs-space-24); margin-top: var(--cs-space-48); }
.field { display: grid; gap: var(--cs-space-8); min-width: 0; }
.hint { margin: 0; }
.primary { margin-top: var(--cs-space-8); text-align: left; }
.feedback { margin: 0; }
.mode-choice { margin-top: var(--cs-space-24); }
.mode-choice p { margin: 0; color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.mode-switch { padding-inline: 0; border-color: transparent; background: transparent; color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; text-align: left; }
.session-note { margin: var(--cs-space-48) 0 0; color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
@media (max-width: 800px) {
  .access-page { display: block; }
  .identity { --cs-color-canvas: inherit; --cs-color-ink: inherit; --cs-color-accent: inherit; --cs-focus-ring: inherit; color-scheme: light; gap: var(--cs-space-8); padding: var(--cs-space-24); background: var(--cs-color-canvas); color: var(--cs-color-ink); }
  .identity .brand { font-size: var(--cs-type-24); }
  .identity .return-link { color: var(--cs-color-accent); }
  .identity-copy { display: none; }
  .form-region { padding: var(--cs-space-32) var(--cs-space-24) var(--cs-space-48); }
  form { margin-top: var(--cs-space-32); }
}
</style>
