<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { sessionToken, logout } from '../features/account/session'
import {
  createDevice, createEnvironment, deactivateDevice, getRules, listDevices, listEnvironments,
  updateDevice, updateEnvironment, updateRules, type Device, type Environment, type Rules,
} from '../features/account/catalog'

const router = useRouter()
const environments = ref<Environment[]>([])
const devices = ref<Device[]>([])
const selectedEnvironmentId = ref('')
const rules = ref<Rules | null>(null)
const environmentName = ref('')
const deviceName = ref('')
const mqttDeviceId = ref('')
const editingEnvironmentId = ref('')
const editingDeviceId = ref('')
const editName = ref('')
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const success = ref('')
let loadRevision = 0

watch(sessionToken, (token) => { if (!token) void router.replace('/login') })
onMounted(() => { void loadEnvironments() })

async function run(action: () => Promise<unknown>, after: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await action()
    await after()
    success.value = 'Alteração salva.'
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Não foi possível salvar.'
  } finally {
    busy.value = false
  }
}

async function loadEnvironments() {
  const token = sessionToken.value
  if (!token) return
  loading.value = true
  error.value = ''
  try {
    environments.value = await listEnvironments(token)
    if (!environments.value.some((environment) => environment.id === selectedEnvironmentId.value)) {
      selectedEnvironmentId.value = environments.value[0]?.id ?? ''
    }
    await loadSelection()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Não foi possível carregar os ambientes.'
  } finally {
    loading.value = false
  }
}

async function loadSelection() {
  const revision = ++loadRevision
  const token = sessionToken.value
  const id = selectedEnvironmentId.value
  devices.value = []
  rules.value = null
  if (!token || !id) return
  loading.value = true
  error.value = ''
  try {
    const [nextDevices, nextRules] = await Promise.all([listDevices(token, id), getRules(token, id)])
    if (revision !== loadRevision) return
    devices.value = nextDevices
    rules.value = nextRules
    error.value = ''
  } catch (cause) {
    if (revision !== loadRevision) return
    error.value = cause instanceof Error ? cause.message : 'Não foi possível carregar o ambiente.'
  } finally {
    if (revision === loadRevision) loading.value = false
  }
}

function validName(name: string): string {
  const trimmed = name.trim()
  if (!trimmed || trimmed.length > 120) throw new Error('Informe um nome com até 120 caracteres.')
  return trimmed
}

function addEnvironment() {
  void run(async () => {
    const token = sessionToken.value!
    const created = await createEnvironment(token, validName(environmentName.value))
    environmentName.value = ''
    selectedEnvironmentId.value = created.id
  }, loadEnvironments)
}

function saveEnvironment(id: string) {
  void run(() => updateEnvironment(sessionToken.value!, id, validName(editName.value)), async () => {
    editingEnvironmentId.value = ''
    await loadEnvironments()
  })
}

function addDevice() {
  void run(async () => {
    const mqttId = mqttDeviceId.value.trim()
    if (!/^[A-Za-z0-9._-]{1,64}$/.test(mqttId)) throw new Error('ID MQTT: use 1 a 64 letras, números, pontos, _ ou -.')
    await createDevice(sessionToken.value!, selectedEnvironmentId.value, validName(deviceName.value), mqttId)
    deviceName.value = ''
    mqttDeviceId.value = ''
  }, loadSelection)
}

function saveDevice(id: string) {
  void run(() => updateDevice(sessionToken.value!, id, validName(editName.value)), async () => {
    editingDeviceId.value = ''
    await loadSelection()
  })
}

function disableDevice(device: Device) {
  if (!window.confirm(`Desativar ${device.name}? O dispositivo deixará de enviar leituras e receber comandos.`)) return
  void run(() => deactivateDevice(sessionToken.value!, device.id), loadSelection)
}

function saveRules() {
  void run(async () => {
    const value = rules.value!
    const { min_c, max_c, attention_margin_c } = value
    if (![min_c, max_c, attention_margin_c].every(Number.isFinite) || min_c >= max_c || attention_margin_c < 0 || attention_margin_c * 2 >= max_c - min_c) {
      throw new Error('Informe mínimo menor que máximo e uma margem menor que metade da faixa.')
    }
    await updateRules(sessionToken.value!, selectedEnvironmentId.value, value)
  }, loadSelection)
}

async function signOut() {
  try {
    await logout()
    await router.replace('/login')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Não foi possível sair.'
  }
}
</script>

<template>
  <main class="manage">
    <div class="shell">
      <header class="nav">
        <RouterLink to="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</RouterLink>
        <nav aria-label="Navegação principal">
          <RouterLink to="/dashboard">Dashboard</RouterLink>
          <RouterLink to="/manage" aria-current="page">Gerenciar</RouterLink>
          <button type="button" @click="signOut">Sair</button>
        </nav>
      </header>
      <section class="heading">
        <p class="eyebrow">Configuração</p>
        <h1>Ambientes e dispositivos</h1>
        <p>Cadastre as unidades e ajuste a faixa de temperatura usada no monitoramento.</p>
      </section>
      <p v-if="error" role="alert" class="feedback error">{{ error }}</p>
      <p v-if="success" role="status" class="feedback success">{{ success }}</p>
      <p v-if="loading" role="status" aria-live="polite">Carregando dados…</p>

      <div class="grid">
        <section class="panel" aria-labelledby="environments-title">
          <h2 id="environments-title">Ambientes</h2>
          <form class="inline-form" @submit.prevent="addEnvironment">
            <label for="environment-name">Novo ambiente</label>
            <div class="input-row"><input id="environment-name" v-model="environmentName" maxlength="120" required placeholder="Ex.: Câmara fria 1" :disabled="busy" /><button class="primary" type="submit" :disabled="busy">Adicionar</button></div>
          </form>
          <p v-if="!loading && environments.length === 0">Nenhum ambiente cadastrado.</p>
          <ul class="item-list">
            <li v-for="environment in environments" :key="environment.id" :class="{ selected: selectedEnvironmentId === environment.id }">
              <template v-if="editingEnvironmentId === environment.id">
                <form class="edit-form" @submit.prevent="saveEnvironment(environment.id)"><input v-model="editName" aria-label="Nome do ambiente" maxlength="120" required /><button type="submit" :disabled="busy">Salvar</button><button type="button" @click="editingEnvironmentId = ''">Cancelar</button></form>
              </template>
              <template v-else>
                <button type="button" class="item-name" :aria-pressed="selectedEnvironmentId === environment.id" @click="selectedEnvironmentId = environment.id; loadSelection()">{{ environment.name }}</button>
                <button type="button" class="small-action" @click="editingEnvironmentId = environment.id; editName = environment.name">Editar</button>
              </template>
            </li>
          </ul>
        </section>

        <div v-if="selectedEnvironmentId" class="detail">
          <section class="panel" aria-labelledby="devices-title">
            <h2 id="devices-title">Dispositivos</h2>
            <form class="fields" @submit.prevent="addDevice">
              <label for="device-name">Nome do dispositivo</label>
              <input id="device-name" v-model="deviceName" maxlength="120" required placeholder="Ex.: Sensor principal" :disabled="busy" />
              <label for="mqtt-id">Identificador MQTT</label>
              <input id="mqtt-id" v-model="mqttDeviceId" maxlength="64" pattern="[A-Za-z0-9._-]+" required placeholder="Ex.: esp32-camara-1" :disabled="busy" />
              <p class="hint">Use o mesmo identificador configurado no ESP32. Ele não pode ser alterado depois.</p>
              <button class="primary" type="submit" :disabled="busy">Cadastrar dispositivo</button>
            </form>
            <p v-if="!loading && devices.length === 0">Nenhum dispositivo cadastrado neste ambiente.</p>
            <ul class="item-list">
              <li v-for="device in devices" :key="device.id">
                <div class="device-info"><strong>{{ device.name }}</strong><span>{{ device.mqtt_device_id }} · {{ device.is_active ? 'Ativo' : 'Desativado' }}</span></div>
                <form v-if="editingDeviceId === device.id" class="edit-form" @submit.prevent="saveDevice(device.id)"><input v-model="editName" aria-label="Nome do dispositivo" maxlength="120" required /><button type="submit" :disabled="busy">Salvar</button><button type="button" @click="editingDeviceId = ''">Cancelar</button></form>
                <div v-else class="actions"><button type="button" @click="editingDeviceId = device.id; editName = device.name">Editar</button><button v-if="device.is_active" type="button" class="danger" :disabled="busy" @click="disableDevice(device)">Desativar</button></div>
              </li>
            </ul>
          </section>

          <section v-if="rules" class="panel" aria-labelledby="rules-title">
            <h2 id="rules-title">Limites de temperatura</h2>
            <form class="fields" @submit.prevent="saveRules">
              <label for="min-c">Mínimo (°C)</label><input id="min-c" v-model.number="rules.min_c" type="number" step="0.01" required :disabled="busy" />
              <label for="max-c">Máximo (°C)</label><input id="max-c" v-model.number="rules.max_c" type="number" step="0.01" required :disabled="busy" />
              <label for="margin-c">Margem de recuperação (°C)</label><input id="margin-c" v-model.number="rules.attention_margin_c" type="number" step="0.01" min="0" required :disabled="busy" />
              <p class="hint">A margem deve ser menor que metade da faixa entre mínimo e máximo.</p>
              <button class="primary" type="submit" :disabled="busy">Salvar limites</button>
            </form>
          </section>
        </div>
      </div>
    </div>
  </main>
</template>

<style scoped>
.manage { padding: var(--cs-space-48); }
.shell { max-width: 1200px; margin-inline: auto; }
.nav { display: flex; justify-content: space-between; align-items: center; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.brand { display: inline-flex; gap: var(--cs-space-12); align-items: center; font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; }
.nav nav { display: flex; flex-wrap: wrap; align-items: center; gap: var(--cs-space-24); }
.nav button, .small-action, .actions button, .edit-form button { color: var(--cs-color-accent); cursor: pointer; text-decoration: underline; }
.heading { margin-block: var(--cs-space-32); }
.heading p { color: var(--cs-color-ink-muted); }
.eyebrow { font-size: var(--cs-type-12); text-transform: uppercase; }
h1 { margin: var(--cs-space-8) 0; font-size: var(--cs-type-32); }
h2 { margin: 0 0 var(--cs-space-24); font-size: var(--cs-type-20); }
.grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: var(--cs-space-24); align-items: start; }
.detail { display: grid; gap: var(--cs-space-24); }
.panel { padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); }
.fields, .inline-form { display: grid; gap: var(--cs-space-12); }
label { font-size: var(--cs-type-14); font-weight: 600; }
input { width: 100%; min-width: 0; min-height: 44px; padding: var(--cs-space-12); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); color: var(--cs-color-ink); font: inherit; }
.input-row { display: flex; gap: var(--cs-space-8); }
.primary { min-height: 44px; padding: 0 var(--cs-space-16); border-radius: var(--cs-radius-4); background: var(--cs-color-accent); color: var(--cs-color-accent-ink); font-weight: 600; cursor: pointer; }
.primary:hover { background: var(--cs-color-accent-hover); }
button:disabled { cursor: wait; opacity: .65; }
.item-list { padding: 0; margin: var(--cs-space-24) 0 0; list-style: none; }
.item-list li { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-12); padding: var(--cs-space-12); border-top: 1px solid var(--cs-color-line); }
.item-list li.selected { background: var(--cs-color-surface-muted); }
.item-name { min-height: 44px; flex: 1; text-align: left; cursor: pointer; }
.device-info { display: grid; gap: var(--cs-space-4); overflow-wrap: anywhere; }
.device-info span, .hint { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.actions { display: flex; gap: var(--cs-space-16); }
.actions .danger { color: var(--cs-color-status-critical); }
.edit-form { display: flex; flex-wrap: wrap; gap: var(--cs-space-8); width: 100%; }
.edit-form input { flex: 1; }
.feedback { padding: var(--cs-space-12); border-left: 4px solid; }
.error { border-color: var(--cs-color-status-critical); color: var(--cs-color-status-critical); }
.success { border-color: var(--cs-color-status-normal); color: var(--cs-color-status-normal); }
@media (max-width: 800px) { .manage { padding: var(--cs-space-24); } .grid { grid-template-columns: 1fr; } .nav { align-items: flex-start; flex-direction: column; } h1 { font-size: var(--cs-type-24); } }
</style>
