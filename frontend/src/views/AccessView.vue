<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register } from '../features/account/session'

const router = useRouter()
const route = useRoute()
const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  if (busy.value) return
  error.value = ''
  if (mode.value === 'register' && password.value.length < 8) {
    error.value = 'A senha precisa ter ao menos 8 caracteres.'
    return
  }
  busy.value = true
  try {
    if (mode.value === 'register') await register(email.value.trim(), password.value)
    await login(email.value.trim(), password.value)
    const redirect = route.query.redirect
    await router.push(typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/dashboard')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Não foi possível acessar sua conta.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="access-page">
    <div class="access-shell">
      <RouterLink to="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</RouterLink>
      <section class="panel" aria-labelledby="access-title">
        <p class="eyebrow">Acesso à sua operação</p>
        <h1 id="access-title" tabindex="-1">{{ mode === 'login' ? 'Entrar' : 'Criar conta' }}</h1>
        <p class="intro">Seus ambientes e dispositivos ficam vinculados à sua conta.</p>
        <form @submit.prevent="submit">
          <label for="email">Email</label>
          <input id="email" v-model.trim="email" type="email" autocomplete="email" maxlength="254" required :disabled="busy" />
          <label for="password">Senha</label>
          <input id="password" v-model="password" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" :minlength="mode === 'register' ? 8 : 1" maxlength="128" required :disabled="busy" />
          <p v-if="error" role="alert" class="error">{{ error }}</p>
          <button class="primary" type="submit" :disabled="busy">{{ busy ? 'Aguarde…' : mode === 'login' ? 'Entrar' : 'Criar conta e entrar' }}</button>
        </form>
        <button class="mode-switch" type="button" :disabled="busy" @click="mode = mode === 'login' ? 'register' : 'login'; error = ''">
          {{ mode === 'login' ? 'Ainda não tem conta? Cadastre-se' : 'Já tem conta? Entre' }}
        </button>
      </section>
    </div>
  </main>
</template>

<style scoped>
.access-page { min-height: 100vh; padding: var(--cs-space-48) var(--cs-space-24); }
.access-shell { max-width: 480px; margin-inline: auto; }
.brand { display: inline-flex; gap: var(--cs-space-12); align-items: center; margin-bottom: var(--cs-space-48); font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; }
.panel { padding: var(--cs-space-32); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.eyebrow { color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); text-transform: uppercase; }
h1 { margin: var(--cs-space-8) 0 var(--cs-space-12); font-size: var(--cs-type-32); }
.intro { color: var(--cs-color-ink-muted); line-height: 1.5; }
form { display: grid; gap: var(--cs-space-12); margin-top: var(--cs-space-32); }
label { font-size: var(--cs-type-14); font-weight: 600; }
input { width: 100%; min-height: 44px; padding: var(--cs-space-12); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); color: var(--cs-color-ink); font: inherit; }
button { min-height: 44px; cursor: pointer; }
.primary { margin-top: var(--cs-space-12); border-radius: var(--cs-radius-4); background: var(--cs-color-accent); color: var(--cs-color-accent-ink); font-weight: 600; }
.primary:hover { background: var(--cs-color-accent-hover); }
.mode-switch { margin-top: var(--cs-space-24); color: var(--cs-color-accent); text-decoration: underline; }
.error { padding: var(--cs-space-12); border-left: 4px solid var(--cs-color-status-critical); color: var(--cs-color-status-critical); }
button:disabled { cursor: wait; opacity: .65; }
@media (max-width: 600px) { .access-page { padding-top: var(--cs-space-24); } .brand { margin-bottom: var(--cs-space-32); } .panel { padding: var(--cs-space-24); } }
</style>
