<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { sessionToken, sessionRole, canWrite, logout } from '../features/account/session'
import {
  createDevice, createEnvironment, deactivateDevice, getRules, listDevices, listEnvironments,
  updateDevice, updateEnvironment, updateRules, type Device, type Environment, type Rules,
} from '../features/account/catalog'

const router = useRouter()
const environments = ref<Environment[]>([])
const devices = ref<Device[]>([])
const selectedEnvironmentId = ref('')
const selectedEnvironment = computed(() => environments.value.find((environment) => environment.id === selectedEnvironmentId.value))
const rules = ref<Rules | null>(null)
const showEnvironmentForm = ref(false)
const showDeviceForm = ref(false)
const environmentNameInput = ref<HTMLInputElement | null>(null)
const deviceNameInput = ref<HTMLInputElement | null>(null)
const environmentOpenButton = ref<HTMLButtonElement | null>(null)
const deviceOpenButton = ref<HTMLButtonElement | null>(null)
const environmentName = ref('')
const deviceName = ref('')
const mqttDeviceId = ref('')
const editingEnvironmentId = ref('')
const editingDeviceId = ref('')
const environmentEditName = ref('')
const deviceEditName = ref('')
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const success = ref('')
const ruleErrors = ref<Partial<Record<keyof Rules, string>>>({})
const rulesSaveError = ref('')
let loadRevision = 0

watch(sessionToken, (token) => { if (!token) void router.replace('/login') })
onMounted(() => { void loadEnvironments() })

async function run(action: () => Promise<unknown>, after: () => Promise<void>) {
  if (busy.value || !canWrite.value) return
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
  ruleErrors.value = {}
  rulesSaveError.value = ''
  success.value = ''
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
  }, async () => {
    await loadEnvironments()
    showEnvironmentForm.value = false
    await nextTick()
    environmentOpenButton.value?.focus()
  })
}

function saveEnvironment(id: string) {
  void run(() => updateEnvironment(sessionToken.value!, id, validName(environmentEditName.value)), async () => {
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
  }, async () => {
    await loadSelection()
    showDeviceForm.value = false
    await nextTick()
    deviceOpenButton.value?.focus()
  })
}

async function openEnvironmentForm() {
  showEnvironmentForm.value = true
  await nextTick()
  environmentNameInput.value?.focus()
}

async function cancelEnvironmentForm() {
  showEnvironmentForm.value = false
  environmentName.value = ''
  await nextTick()
  environmentOpenButton.value?.focus()
}

async function openDeviceForm() {
  showDeviceForm.value = true
  await nextTick()
  deviceNameInput.value?.focus()
}

async function cancelDeviceForm() {
  showDeviceForm.value = false
  deviceName.value = ''
  mqttDeviceId.value = ''
  await nextTick()
  deviceOpenButton.value?.focus()
}

function saveDevice(id: string) {
  void run(() => updateDevice(sessionToken.value!, id, validName(deviceEditName.value)), async () => {
    editingDeviceId.value = ''
    await loadSelection()
  })
}

function disableDevice(device: Device) {
  if (!window.confirm(`Desativar ${device.name}? O dispositivo deixará de enviar leituras e receber comandos.`)) return
  void run(() => deactivateDevice(sessionToken.value!, device.id), loadSelection)
}

function validTemperature(value: number) {
  return Number.isFinite(value) && /^-?\d{1,3}(?:\.\d{1,2})?$/.test(String(value))
}

function validateRules(value: Rules): Partial<Record<keyof Rules, string>> {
  const errors: Partial<Record<keyof Rules, string>> = {}
  if (!validTemperature(value.min_c)) errors.min_c = 'Informe um mínimo válido, com até duas casas decimais.'
  if (!validTemperature(value.max_c)) errors.max_c = 'Informe um máximo válido, com até duas casas decimais.'
  if (!validTemperature(value.attention_margin_c) || value.attention_margin_c < 0) {
    errors.attention_margin_c = 'Informe uma margem igual ou maior que zero, com até duas casas decimais.'
  }
  if (!errors.min_c && !errors.max_c && value.min_c >= value.max_c) {
    errors.min_c = 'O mínimo deve ser menor que o máximo.'
    errors.max_c = 'O máximo deve ser maior que o mínimo.'
  }
  if (!errors.min_c && !errors.max_c && !errors.attention_margin_c && value.attention_margin_c * 2 >= value.max_c - value.min_c) {
    errors.attention_margin_c = 'A margem deve ser menor que metade da faixa entre mínimo e máximo.'
  }
  return errors
}

function clearRuleError(field: keyof Rules) {
  ruleErrors.value = { ...ruleErrors.value, [field]: '' }
  rulesSaveError.value = ''
}

async function saveRules() {
  const token = sessionToken.value
  const environmentId = selectedEnvironmentId.value
  if (busy.value || !canWrite.value || !token || !environmentId || !rules.value) return
  const value = { ...rules.value }
  const nextErrors = validateRules(value)
  ruleErrors.value = nextErrors
  rulesSaveError.value = ''
  success.value = ''
  if (Object.keys(nextErrors).length) {
    const first = (['min_c', 'max_c', 'attention_margin_c'] as const).find((field) => nextErrors[field])
    await nextTick()
    document.getElementById(first === 'min_c' ? 'min-c' : first === 'max_c' ? 'max-c' : 'margin-c')?.focus()
    return
  }
  busy.value = true
  try {
    const saved = await updateRules(token, environmentId, value)
    if (selectedEnvironmentId.value === environmentId) rules.value = saved
    success.value = `Limites de ${selectedEnvironment.value?.name ?? 'temperatura'} salvos.`
  } catch (cause) {
    rulesSaveError.value = cause instanceof Error ? cause.message : 'Não foi possível salvar os limites.'
  } finally {
    busy.value = false
  }
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
    <a class="skip-link" href="#manage-title">Ir para o conteúdo</a>
    <div class="shell">
      <header class="nav">
        <RouterLink to="/" class="brand"><span aria-hidden="true">◉</span> ColdSafe</RouterLink>
        <nav aria-label="Navegação principal">
          <RouterLink to="/dashboard">Monitoramento</RouterLink>
          <RouterLink to="/insights">Insights</RouterLink>
          <RouterLink to="/manage" aria-current="page">Ambientes e dispositivos</RouterLink>
          <RouterLink to="/messaging">Mensageria</RouterLink>
          <RouterLink to="/laboratory">Laboratório</RouterLink>
          <RouterLink to="/training">Treinamento</RouterLink>
        </nav>
        <button class="sign-out" type="button" @click="signOut">Sair</button>
      </header>
      <section class="heading">
        <p class="eyebrow">Configuração</p>
        <h1 id="manage-title" tabindex="-1">Ambientes e dispositivos</h1>
        <p>Cadastre as unidades e ajuste a faixa de temperatura usada no monitoramento.</p>
      </section>
      <p v-if="!canWrite" role="status">{{ sessionRole === 'viewer' ? 'Modo visualizador: você pode consultar seus ambientes, dispositivos e limites.' : 'Permissões ainda não confirmadas. As alterações estão indisponíveis.' }}</p>
      <p v-if="error" role="alert" class="feedback error">{{ error }}</p>
      <p v-if="success" role="status" class="feedback success">{{ success }}</p>
      <p v-if="loading" role="status" aria-live="polite">Carregando dados…</p>

      <div class="grid">
        <section class="panel" aria-labelledby="environments-title">
          <h2 id="environments-title">Ambientes</h2>
          <p v-if="!loading && environments.length === 0">Nenhum ambiente cadastrado. Adicione o primeiro ambiente para configurar dispositivos e limites.</p>
          <ul class="item-list">
            <li v-for="environment in environments" :key="environment.id" :class="{ selected: selectedEnvironmentId === environment.id }">
              <template v-if="editingEnvironmentId === environment.id">
                <form class="edit-form" @submit.prevent="saveEnvironment(environment.id)"><input v-model="environmentEditName" :aria-label="`Nome do ambiente ${environment.name}`" maxlength="120" required /><button type="submit" :aria-label="`Salvar ambiente ${environment.name}`" :disabled="busy || !canWrite">Salvar</button><button type="button" :aria-label="`Cancelar edição do ambiente ${environment.name}`" @click="editingEnvironmentId = ''">Cancelar</button></form>
              </template>
              <template v-else>
                <button type="button" class="item-name" :aria-pressed="selectedEnvironmentId === environment.id" :disabled="busy" @click="selectedEnvironmentId = environment.id; loadSelection()">{{ environment.name }}</button>
                <button type="button" class="small-action" :disabled="!canWrite" :aria-label="`Editar ambiente ${environment.name}`" @click="editingEnvironmentId = environment.id; environmentEditName = environment.name">Editar</button>
              </template>
            </li>
          </ul>
          <button v-if="!showEnvironmentForm" ref="environmentOpenButton" data-test="open-environment-form" :disabled="!canWrite" class="primary add-action" type="button" @click="openEnvironmentForm">Adicionar ambiente</button>
          <form v-else class="inline-form add-form" @submit.prevent="addEnvironment">
            <label for="environment-name">Nome do novo ambiente</label>
            <input id="environment-name" ref="environmentNameInput" v-model="environmentName" maxlength="120" required placeholder="Ex.: Câmara fria 1" :disabled="busy || !canWrite" />
            <div class="actions"><button class="primary" type="submit" :disabled="busy || !canWrite">Adicionar ambiente</button><button data-test="cancel-environment-form" type="button" aria-label="Cancelar inclusão de ambiente" :disabled="busy || !canWrite" @click="cancelEnvironmentForm">Cancelar</button></div>
          </form>
        </section>

        <div v-if="selectedEnvironment" class="detail">
          <section class="panel" aria-labelledby="devices-title">
            <h2 id="devices-title">Dispositivos de {{ selectedEnvironment.name }}</h2>
            <p v-if="!loading && devices.length === 0">Nenhum dispositivo cadastrado neste ambiente. Adicione um dispositivo para começar a monitorar.</p>
            <ul class="item-list">
              <li v-for="device in devices" :key="device.id">
                <div class="device-info"><strong>{{ device.name }}</strong><span>{{ device.mqtt_device_id }} · {{ device.is_active ? 'Ativo' : 'Desativado' }}</span></div>
                <form v-if="editingDeviceId === device.id" class="edit-form" @submit.prevent="saveDevice(device.id)"><input v-model="deviceEditName" :aria-label="`Nome do dispositivo ${device.name}`" maxlength="120" required /><button type="submit" :aria-label="`Salvar dispositivo ${device.name}`" :disabled="busy || !canWrite">Salvar</button><button type="button" :aria-label="`Cancelar edição do dispositivo ${device.name}`" @click="editingDeviceId = ''">Cancelar</button></form>
                <div v-else class="actions"><button type="button" :disabled="!canWrite" :aria-label="`Editar dispositivo ${device.name}`" @click="editingDeviceId = device.id; deviceEditName = device.name">Editar</button><button v-if="device.is_active" type="button" class="danger" :aria-label="`Desativar dispositivo ${device.name}`" :disabled="busy || !canWrite" @click="disableDevice(device)">Desativar</button></div>
              </li>
            </ul>
            <button v-if="!showDeviceForm" ref="deviceOpenButton" data-test="open-device-form" :disabled="!canWrite" class="primary add-action" type="button" @click="openDeviceForm">Adicionar dispositivo</button>
            <form v-else class="fields add-form" @submit.prevent="addDevice">
              <h3>Adicionar dispositivo em {{ selectedEnvironment.name }}</h3>
              <label for="device-name">Nome do dispositivo</label>
              <input id="device-name" ref="deviceNameInput" v-model="deviceName" maxlength="120" required placeholder="Ex.: Sensor principal" :disabled="busy || !canWrite" />
              <label for="mqtt-id">Identificador MQTT</label>
              <input id="mqtt-id" v-model="mqttDeviceId" maxlength="64" pattern="[A-Za-z0-9._-]+" required placeholder="Ex.: esp32-camara-1" :disabled="busy || !canWrite" />
              <p class="hint">Use o mesmo identificador configurado no ESP32. Ele não pode ser alterado depois.</p>
              <div class="actions"><button class="primary" type="submit" :disabled="busy || !canWrite">Cadastrar dispositivo</button><button data-test="cancel-device-form" type="button" aria-label="Cancelar inclusão de dispositivo" :disabled="busy || !canWrite" @click="cancelDeviceForm">Cancelar</button></div>
            </form>
          </section>

          <section v-if="rules" class="panel" aria-labelledby="rules-title">
            <h2 id="rules-title">Limites de temperatura de {{ selectedEnvironment.name }}</h2>
            <form class="fields" novalidate @submit.prevent="saveRules">
              <p v-if="Object.values(ruleErrors).some(Boolean)" role="alert" class="error">Revise os limites destacados abaixo.</p>
              <label for="min-c">Mínimo (°C)</label><input id="min-c" v-model.number="rules.min_c" type="number" step="0.01" required :disabled="busy || !canWrite" :aria-invalid="Boolean(ruleErrors.min_c)" :aria-describedby="ruleErrors.min_c ? 'min-c-error' : undefined" @input="clearRuleError('min_c')" />
              <p v-if="ruleErrors.min_c" id="min-c-error" class="field-error">{{ ruleErrors.min_c }}</p>
              <label for="max-c">Máximo (°C)</label><input id="max-c" v-model.number="rules.max_c" type="number" step="0.01" required :disabled="busy || !canWrite" :aria-invalid="Boolean(ruleErrors.max_c)" :aria-describedby="ruleErrors.max_c ? 'max-c-error' : undefined" @input="clearRuleError('max_c')" />
              <p v-if="ruleErrors.max_c" id="max-c-error" class="field-error">{{ ruleErrors.max_c }}</p>
              <label for="margin-c">Margem de atenção (°C)</label><input id="margin-c" v-model.number="rules.attention_margin_c" type="number" step="0.01" min="0" required :disabled="busy || !canWrite" :aria-invalid="Boolean(ruleErrors.attention_margin_c)" :aria-describedby="`margin-c-hint${ruleErrors.attention_margin_c ? ' margin-c-error' : ''}`" @input="clearRuleError('attention_margin_c')" />
              <p v-if="ruleErrors.attention_margin_c" id="margin-c-error" class="field-error">{{ ruleErrors.attention_margin_c }}</p>
              <p id="margin-c-hint" class="hint">Dentro da faixa, a leitura entra em Atenção quando está a até esta margem do mínimo ou do máximo. A margem deve ser menor que metade da faixa.</p>
              <p v-if="rulesSaveError" id="rules-save-error" role="alert" class="field-error">{{ rulesSaveError }}</p>
              <button class="primary" type="submit" :disabled="busy || !canWrite">Salvar limites</button>
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
.nav { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-24); padding-bottom: var(--cs-space-32); border-bottom: 1px solid var(--cs-color-line); }
.brand { display: inline-flex; gap: var(--cs-space-12); align-items: center; margin-right: auto; font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; }
.nav nav { display: flex; flex-wrap: wrap; align-items: center; gap: var(--cs-space-16); font-size: var(--cs-type-14); }
.nav button, .small-action, .actions button, .edit-form button { color: var(--cs-color-accent); cursor: pointer; text-decoration: underline; }
.nav nav a, .sign-out, .small-action, .actions button, .edit-form button { display: inline-flex; align-items: center; min-height: 44px; }
.heading { margin-block: var(--cs-space-32); }
.heading p { color: var(--cs-color-ink-muted); }
.eyebrow { font-size: var(--cs-type-12); text-transform: uppercase; }
h1 { margin: var(--cs-space-8) 0; font-size: var(--cs-type-32); }
h2 { margin: 0 0 var(--cs-space-24); font-size: var(--cs-type-20); }
.grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: var(--cs-space-24); align-items: start; }
.detail { display: grid; min-width: 0; gap: var(--cs-space-24); }
.panel { min-width: 0; padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); overflow-wrap: anywhere; }
.fields, .inline-form { display: grid; gap: var(--cs-space-12); }
label { font-size: var(--cs-type-14); font-weight: 600; }
input { width: 100%; min-width: 0; min-height: 44px; padding: var(--cs-space-12); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); color: var(--cs-color-ink); font: inherit; }
.primary { min-height: 44px; padding: 0 var(--cs-space-16); border-radius: var(--cs-radius-4); background: var(--cs-color-accent); color: var(--cs-color-accent-ink); font-weight: 600; cursor: pointer; }
.primary:hover { background: var(--cs-color-accent-hover); }
.add-action, .add-form { margin-top: var(--cs-space-24); }
.add-form { padding-top: var(--cs-space-24); border-top: 1px solid var(--cs-color-line); }
h3 { margin: 0; font-size: var(--cs-type-16); }
button:disabled { cursor: wait; opacity: .65; }
.item-list { padding: 0; margin: var(--cs-space-24) 0 0; list-style: none; }
.item-list li { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-12); padding: var(--cs-space-12); border-top: 1px solid var(--cs-color-line); }
.item-list li.selected { background: var(--cs-color-surface-muted); }
.item-name { min-height: 44px; flex: 1; text-align: left; cursor: pointer; }
.device-info { display: grid; gap: var(--cs-space-4); overflow-wrap: anywhere; }
.device-info span, .hint { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--cs-space-16); }
.actions .primary { color: var(--cs-color-accent-ink); text-decoration: none; }
.actions .danger { color: var(--cs-color-status-critical); }
.edit-form { display: flex; flex-wrap: wrap; gap: var(--cs-space-8); width: 100%; }
.edit-form input { flex: 1; }
.feedback { padding: var(--cs-space-12); border-left: 4px solid; }
.error { border-color: var(--cs-color-status-critical); color: var(--cs-color-status-critical); }
.field-error { color: var(--cs-color-status-critical); font-size: var(--cs-type-14); }
input[aria-invalid='true'] { border-color: var(--cs-color-status-critical); }
.success { border-color: var(--cs-color-status-normal); color: var(--cs-color-status-normal); }
@media (max-width: 800px) { .manage { padding: var(--cs-space-24); } .grid { grid-template-columns: 1fr; } .nav { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--cs-space-8); } .nav nav { display: grid; grid-column: 1 / -1; grid-row: 2; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-8); } .nav nav a { min-width: 0; overflow-wrap: anywhere; } h1 { font-size: var(--cs-type-24); } }
</style>
