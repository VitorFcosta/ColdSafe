<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { sessionToken, sessionRole, canWrite } from '../features/account/session'
import { requestDraftTransition, resolveDraftPrompt, useDraftProtection } from '../features/editing/draft-protection'
import {
  CatalogAccessError, createDevice, createEnvironment, deactivateDevice, getRules, listDevices, listEnvironments,
  updateDevice, updateEnvironment, updateRules, type Device, type Environment, type Rules,
} from '../features/account/catalog'

const router = useRouter()
const environments = ref<Environment[]>([])
const devices = ref<Device[]>([])
const selectedEnvironmentId = ref('')
const selectedEnvironment = computed(() => environments.value.find((environment) => environment.id === selectedEnvironmentId.value))
const editingEnvironment = computed(() => environments.value.find(environment => environment.id === editingEnvironmentId.value))
const rules = ref<Rules | null>(null)
const rulesBaseline = ref<Rules | null>(null)
const temperatureFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 })
let rulesEnvironmentId = ''
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
const environmentEditBaseline = ref('')
const deviceEditBaseline = ref('')
const busy = ref(false)
const loading = ref(true)
const environmentsFailed = ref(false)
const error = ref('')
const success = ref('')
const ruleErrors = ref<Partial<Record<keyof Rules, string>>>({})
const rulesSaveError = ref('')
const selectionFailed = ref(false)
const deactivation = ref<Device | null>(null)
const deactivationDialog = ref<HTMLDialogElement | null>(null)
const deactivationCancel = ref<HTMLButtonElement | null>(null)
const devicesTitle = ref<HTMLElement | null>(null)
const selectionRetryButton = ref<HTMLButtonElement | null>(null)
let deactivationTrigger: HTMLElement | null = null
const fieldIds = { environment: 'environment-name', environmentEdit: 'environment-edit-name', device: 'device-name', deviceEdit: 'device-edit-name', mqtt: 'mqtt-id' } as const
type FormField = keyof typeof fieldIds
const fieldErrors = ref<Partial<Record<FormField, string>>>({})
let loadRevision = 0
let environmentsRequest = 0
let privateRevision = 0
let disposed = false

function discardEnvironment() { showEnvironmentForm.value = false; environmentName.value = ''; clearFieldError('environment') }
function discardDevice() { showDeviceForm.value = false; deviceName.value = ''; mqttDeviceId.value = ''; clearFieldError('device'); clearFieldError('mqtt') }
function discardEnvironmentEdit() { editingEnvironmentId.value = ''; environmentEditName.value = ''; environmentEditBaseline.value = ''; clearFieldError('environmentEdit') }
function discardDeviceEdit() { editingDeviceId.value = ''; deviceEditName.value = ''; deviceEditBaseline.value = ''; clearFieldError('deviceEdit') }
function discardRules() { rules.value = rulesBaseline.value ? { ...rulesBaseline.value } : null; ruleErrors.value = {}; rulesSaveError.value = '' }
const rulesDirty = computed(() => Boolean(canWrite.value && rules.value && rulesBaseline.value &&
  (rules.value.min_c !== rulesBaseline.value.min_c || rules.value.max_c !== rulesBaseline.value.max_c ||
   rules.value.attention_margin_c !== rulesBaseline.value.attention_margin_c)))
const environmentDraft = useDraftProtection({ label: 'Novo ambiente',
  dirty: computed(() => canWrite.value && showEnvironmentForm.value && environmentName.value !== ''), discard: discardEnvironment })
const deviceDraft = useDraftProtection({ label: computed(() => `Novo dispositivo em ${selectedEnvironment.value?.name ?? 'ambiente selecionado'}`),
  dirty: computed(() => canWrite.value && showDeviceForm.value && (deviceName.value !== '' || mqttDeviceId.value !== '')), discard: discardDevice })
const environmentEditDraft = useDraftProtection({ label: 'Nome do ambiente',
  dirty: computed(() => canWrite.value && Boolean(editingEnvironmentId.value) && environmentEditName.value !== environmentEditBaseline.value), discard: discardEnvironmentEdit })
const deviceEditDraft = useDraftProtection({ label: 'Nome do dispositivo',
  dirty: computed(() => canWrite.value && Boolean(editingDeviceId.value) && deviceEditName.value !== deviceEditBaseline.value), discard: discardDeviceEdit })
const rulesDraft = useDraftProtection({ label: computed(() => `Limites de temperatura de ${selectedEnvironment.value?.name ?? 'ambiente selecionado'}`), dirty: rulesDirty, discard: discardRules })
const scopedDrafts = [deviceDraft, deviceEditDraft, rulesDraft]

function clearPrivate() {
  closeDeactivation(false)
  resolveDraftPrompt(false)
  privateRevision += 1; loadRevision += 1; environmentsRequest += 1
  environments.value = []; devices.value = []; selectedEnvironmentId.value = ''
  rulesBaseline.value = null; rulesEnvironmentId = ''; rules.value = null
  discardEnvironment(); discardDevice(); discardEnvironmentEdit(); discardDeviceEdit(); discardRules()
  busy.value = false; loading.value = false; environmentsFailed.value = false; selectionFailed.value = false; error.value = ''; success.value = ''; fieldErrors.value = {}
}
function current(token: string, revision: number) {
  return !disposed && sessionToken.value === token && revision === privateRevision
}
function accessError(cause: unknown) {
  if (!(cause instanceof CatalogAccessError)) return false
  const authorizedEnvironments = environments.value
  clearPrivate()
  environments.value = authorizedEnvironments
  error.value = 'Acesso ao ambiente indisponível. Selecione outro ambiente autorizado ou consulte a lista novamente.'
  return true
}
watch([sessionToken, canWrite], ([token], [oldToken]) => {
  clearPrivate()
  if (!token) { void router.replace('/login'); return }
  if (token !== oldToken || sessionRole.value !== null) void loadEnvironments()
}, { flush: 'sync' })
onMounted(() => { void loadEnvironments() })
onUnmounted(() => { closeDeactivation(false); disposed = true; privateRevision += 1; loadRevision += 1; environmentsRequest += 1 })
watch(selectedEnvironmentId, () => closeDeactivation(false), { flush: 'sync' })

async function run<T>(action: () => Promise<T>, after: (value: T) => Promise<void>) {
  const token = sessionToken.value, revision = privateRevision
  if (busy.value || !canWrite.value || !token) return
  busy.value = true; error.value = ''; success.value = ''
  try {
    const value = await action()
    if (!current(token, revision)) return
    await after(value)
    if (current(token, revision)) success.value = 'Alteração salva.'
  } catch (cause) {
    if (current(token, revision) && !accessError(cause)) error.value = cause instanceof Error ? cause.message : 'Não foi possível salvar.'
  } finally { if (current(token, revision)) busy.value = false }
}

async function loadEnvironments() {
  const token = sessionToken.value, request = ++environmentsRequest
  if (!token) return
  loading.value = true; environmentsFailed.value = false; error.value = ''
  try {
    const result = await listEnvironments(token)
    if (disposed || token !== sessionToken.value || request !== environmentsRequest) return
    environments.value = result
    if (!result.some((environment) => environment.id === selectedEnvironmentId.value)) selectedEnvironmentId.value = result[0]?.id ?? ''
    await loadSelection()
  } catch (cause) {
    if (disposed || token !== sessionToken.value || request !== environmentsRequest) return
    if (!accessError(cause)) error.value = cause instanceof Error ? cause.message : 'Não foi possível carregar os ambientes.'
    environmentsFailed.value = true
    loading.value = false
  }
}

async function loadSelection() {
  const revision = ++loadRevision, token = sessionToken.value, id = selectedEnvironmentId.value
  devices.value = []
  if (rulesEnvironmentId !== id) {
    rulesBaseline.value = null; rulesEnvironmentId = ''
    discardRules()
  }
  success.value = ''; selectionFailed.value = false
  if (!token || !id) { loading.value = false; return }
  loading.value = true; error.value = ''
  try {
    const [nextDevices, nextRules] = await Promise.all([listDevices(token, id), getRules(token, id)])
    if (disposed || token !== sessionToken.value || revision !== loadRevision) return
    devices.value = nextDevices
    const preserveDraft = rulesDirty.value
    rulesBaseline.value = { ...nextRules }
    if (!preserveDraft) discardRules()
    rulesEnvironmentId = id
    error.value = ''
  } catch (cause) {
    if (disposed || token !== sessionToken.value || revision !== loadRevision) return
    if (!accessError(cause)) { selectionFailed.value = true; error.value = cause instanceof Error ? cause.message : 'Não foi possível carregar o ambiente.' }
  } finally { if (!disposed && token === sessionToken.value && revision === loadRevision) loading.value = false }
}

async function selectEnvironment(id: string) {
  if (id === selectedEnvironmentId.value) { await loadSelection(); return }
  await requestDraftTransition(async () => {
    privateRevision += 1
    discardDevice(); discardDeviceEdit()
    selectedEnvironmentId.value = id
    await loadSelection()
  }, scopedDrafts)
}

async function changeEnvironment(event: Event) {
  const select = event.target as HTMLSelectElement
  const id = select.value
  select.value = selectedEnvironmentId.value
  await selectEnvironment(id)
}

async function retrySelection() {
  const token = sessionToken.value, revision = privateRevision, id = selectedEnvironmentId.value
  await loadSelection()
  await nextTick()
  if (token && current(token, revision) && selectedEnvironmentId.value === id) (selectionFailed.value ? selectionRetryButton.value : devicesTitle.value)?.focus()
}
async function focusEdit(kind: 'environment' | 'device', id: string) {
  const token = sessionToken.value, revision = privateRevision
  await nextTick()
  if (!token || !current(token, revision) || !canWrite.value) return
  const attribute = kind === 'environment' ? 'data-edit-environment' : 'data-edit-device'
  const trigger = [...document.querySelectorAll<HTMLButtonElement>(`[${attribute}]`)].find(button => button.getAttribute(attribute) === id && button.getClientRects().length)
  ;(trigger ?? (kind === 'device' ? devicesTitle.value : document.getElementById('environments-title')))?.focus()
}
async function cancelEnvironmentEdit() {
  const id = editingEnvironmentId.value
  await environmentEditDraft.request(async () => { discardEnvironmentEdit(); await focusEdit('environment', id) })
}
async function cancelDeviceEdit() {
  const id = editingDeviceId.value
  await deviceEditDraft.request(async () => { discardDeviceEdit(); await focusEdit('device', id) })
}

async function editEnvironment(environment: Environment) {
  if (environment.id === editingEnvironmentId.value) return
  await environmentEditDraft.request(() => {
    editingEnvironmentId.value = environment.id
    environmentEditName.value = environment.name
    environmentEditBaseline.value = environment.name
  })
}
async function editDevice(device: Device) {
  if (device.id === editingDeviceId.value) return
  await deviceEditDraft.request(() => {
    editingDeviceId.value = device.id
    deviceEditName.value = device.name
    deviceEditBaseline.value = device.name
  })
}

function clearFieldError(field: FormField) { fieldErrors.value = { ...fieldErrors.value, [field]: '' } }
function invalidField(field: FormField, message: string): never {
  fieldErrors.value = { ...fieldErrors.value, [field]: message }
  void nextTick(() => document.getElementById(fieldIds[field])?.focus())
  throw new Error(message)
}
function validName(name: string, field: FormField): string {
  const trimmed = name.trim()
  if (!trimmed || trimmed.length > 120) invalidField(field, 'Informe um nome com até 120 caracteres.')
  return trimmed
}

function addEnvironment() {
  const token = sessionToken.value, revision = privateRevision
  void requestDraftTransition(async () => {
    await run(() => createEnvironment(token!, validName(environmentName.value, 'environment')), async (created) => {
    discardEnvironment(); discardDevice(); discardDeviceEdit()
    selectedEnvironmentId.value = created.id
    await loadEnvironments()
    })
    if (token && current(token, revision) && !showEnvironmentForm.value) { await nextTick(); environmentOpenButton.value?.focus() }
  }, scopedDrafts)
}

async function saveEnvironment(id: string) {
  const token = sessionToken.value, revision = privateRevision
  await run(() => updateEnvironment(token!, id, validName(environmentEditName.value, 'environmentEdit')), async () => {
    discardEnvironmentEdit()
    await loadEnvironments()
  })
  if (token && current(token, revision) && !editingEnvironmentId.value) await focusEdit('environment', id)
}

async function addDevice() {
  const token = sessionToken.value, id = selectedEnvironmentId.value, revision = privateRevision
  await run(() => {
    const mqttId = mqttDeviceId.value.trim()
    if (!/^[A-Za-z0-9._-]{1,64}$/.test(mqttId)) invalidField('mqtt', 'ID MQTT: use 1 a 64 letras, números, pontos, _ ou -.')
    return createDevice(token!, id, validName(deviceName.value, 'device'), mqttId)
  }, async () => {
    discardDevice()
    await loadSelection()
  })
  if (token && current(token, revision) && !showDeviceForm.value) { await nextTick(); focusDeviceAction() }
}

async function openEnvironmentForm() {
  showEnvironmentForm.value = true
  await nextTick(); environmentNameInput.value?.focus()
}
async function cancelEnvironmentForm() {
  await environmentDraft.request(async () => {
    discardEnvironment()
    await nextTick(); environmentOpenButton.value?.focus()
  })
}
async function openDeviceForm() {
  showDeviceForm.value = true
  await nextTick(); deviceNameInput.value?.focus()
}
async function cancelDeviceForm() {
  await deviceDraft.request(async () => {
    discardDevice()
    await nextTick(); focusDeviceAction()
  })
}
function focusDeviceAction() {
  const button = deviceOpenButton.value
  ;(button && !button.disabled ? button : selectionRetryButton.value ?? devicesTitle.value)?.focus()
}

async function saveDevice(id: string) {
  const token = sessionToken.value, revision = privateRevision
  await run(() => updateDevice(token!, id, validName(deviceEditName.value, 'deviceEdit')), async () => {
    discardDeviceEdit()
    await loadSelection()
  })
  if (token && current(token, revision) && !editingDeviceId.value) await focusEdit('device', id)
}

async function disableDevice(device: Device, event: Event) {
  if (!canWrite.value || busy.value || !device.is_active || device.environment_id !== selectedEnvironmentId.value) return
  deactivationTrigger = event.currentTarget as HTMLElement
  deactivation.value = { ...device }
  await nextTick()
  if (!deactivation.value || !canWrite.value) return
  deactivationDialog.value?.showModal()
  deactivationCancel.value?.focus()
}
function closeDeactivation(restoreFocus = true) {
  const trigger = deactivationTrigger
  deactivation.value = null
  deactivationTrigger = null
  deactivationDialog.value?.close()
  if (restoreFocus) void nextTick(() => (trigger?.isConnected ? trigger : devicesTitle.value)?.focus())
}
async function confirmDeactivation() {
  const target = deactivation.value, token = sessionToken.value, revision = privateRevision
  if (!target || !canWrite.value || busy.value || !token) return
  if (!devices.value.some(device => device.id === target.id && device.is_active && device.environment_id === selectedEnvironmentId.value)) { closeDeactivation(); return }
  await run(() => deactivateDevice(token, target.id), loadSelection)
  if (current(token, revision)) closeDeactivation()
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
  const revision = privateRevision
  if (busy.value || loading.value || !canWrite.value || !token || !environmentId || !rules.value) return
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
    if (!current(token, revision) || selectedEnvironmentId.value !== environmentId) return
    rulesBaseline.value = { ...saved }
    discardRules()
    success.value = `Limites de ${selectedEnvironment.value?.name ?? 'temperatura'} salvos.`
  } catch (cause) {
    if (current(token, revision) && !accessError(cause)) rulesSaveError.value = cause instanceof Error ? cause.message : 'Não foi possível salvar os limites.'
  } finally {
    if (current(token, revision)) busy.value = false
  }
}

</script>

<template>
  <main class="manage cs-controls">
    <div class="shell">
      <section class="heading">
        <h1 id="manage-title" tabindex="-1">Ambientes e dispositivos</h1>
        <p>{{ canWrite ? 'Cadastre ambientes e dispositivos e ajuste a faixa de temperatura do monitoramento.' : 'Consulte os ambientes, dispositivos e limites de temperatura disponíveis para sua conta.' }}</p>
      </section>
      <p v-if="!canWrite" role="status">{{ sessionRole === 'viewer' ? 'Modo visualizador: você pode consultar seus ambientes, dispositivos e limites.' : 'Permissões ainda não confirmadas. As alterações estão indisponíveis.' }}</p>
      <p v-if="error" role="alert" class="feedback error">{{ error }}</p>
      <button v-if="environmentsFailed" type="button" :disabled="loading" @click="loadEnvironments">Consultar ambientes novamente</button>
      <p v-if="success" role="status" class="feedback success">{{ success }}</p>
      <p v-if="loading" role="status" aria-live="polite">Carregando dados…</p>

      <div class="grid">
        <section class="panel" aria-labelledby="environments-title">
          <h2 id="environments-title" tabindex="-1">Ambientes</h2>
          <p v-if="environments.length" class="section-note">Selecione um ambiente para consultar seus dispositivos e limites.</p>
          <p v-if="!loading && !error && environments.length === 0">Nenhum ambiente cadastrado. {{ canWrite ? 'Adicione o primeiro ambiente para configurar dispositivos e limites.' : 'Um operador ou administrador precisa cadastrar o ambiente.' }}</p>
          <div v-if="environments.length" class="environment-picker"><label for="manage-environment">Ambiente</label><select id="manage-environment" :value="selectedEnvironmentId" :disabled="busy" @change="changeEnvironment"><option value="" disabled>Selecione um ambiente</option><option v-for="environment in environments" :key="environment.id" :value="environment.id">{{ environment.name }}</option></select></div>
          <ul class="item-list desktop-environments">
            <li v-for="environment in environments" :key="environment.id">
                <button type="button" class="item-name" :aria-pressed="selectedEnvironmentId === environment.id" :disabled="busy" @click="selectEnvironment(environment.id)">{{ environment.name }}</button>
                <button v-if="canWrite" type="button" class="small-action" :data-edit-environment="environment.id" :disabled="busy" :aria-label="`Renomear ambiente ${environment.name}`" @click="editEnvironment(environment)">Renomear</button>
            </li>
          </ul>
          <button v-if="canWrite && selectedEnvironment" type="button" class="mobile-rename" :data-edit-environment="selectedEnvironment.id" :disabled="busy" :aria-label="`Renomear ambiente ${selectedEnvironment.name}`" @click="editEnvironment(selectedEnvironment)">Renomear ambiente</button>
          <form v-if="canWrite && editingEnvironment" :aria-busy="busy" class="edit-form add-form" novalidate @submit.prevent="saveEnvironment(editingEnvironment.id)">
            <label class="edit-name">Nome do ambiente {{ editingEnvironment.name }}<input id="environment-edit-name" v-model="environmentEditName" :aria-label="`Nome do ambiente ${editingEnvironment.name}`" maxlength="120" required :disabled="busy" :aria-invalid="Boolean(fieldErrors.environmentEdit)" :aria-describedby="fieldErrors.environmentEdit ? 'environment-edit-name-error' : undefined" @input="clearFieldError('environmentEdit')" /></label>
            <p v-if="fieldErrors.environmentEdit" id="environment-edit-name-error" class="field-error">{{ fieldErrors.environmentEdit }}</p>
            <button type="submit" :aria-label="`${busy ? 'Salvando' : 'Salvar'} ambiente ${editingEnvironment.name}`" :disabled="busy">{{ busy ? 'Salvando…' : 'Salvar' }}</button><button type="button" :aria-label="`Cancelar edição do ambiente ${editingEnvironment.name}`" :disabled="busy" @click="cancelEnvironmentEdit">Cancelar</button>
          </form>
          <button v-if="canWrite && !showEnvironmentForm" ref="environmentOpenButton" data-test="open-environment-form" class="add-action" type="button" :disabled="busy" @click="openEnvironmentForm">Adicionar ambiente</button>
          <form :aria-busy="busy" v-if="canWrite && showEnvironmentForm" class="inline-form add-form" novalidate @submit.prevent="addEnvironment">
            <label for="environment-name">Nome do novo ambiente</label>
            <input id="environment-name" ref="environmentNameInput" v-model="environmentName" maxlength="120" required placeholder="Ex.: Câmara fria 1" :disabled="busy" :aria-invalid="Boolean(fieldErrors.environment)" :aria-describedby="fieldErrors.environment ? 'environment-name-error' : undefined" @input="clearFieldError('environment')" />
            <p v-if="fieldErrors.environment" id="environment-name-error" class="field-error">{{ fieldErrors.environment }}</p>
            <div class="actions"><button class="primary" type="submit" :disabled="busy || !canWrite">{{ busy ? 'Adicionando…' : 'Adicionar ambiente' }}</button><button data-test="cancel-environment-form" type="button" aria-label="Cancelar inclusão de ambiente" :disabled="busy || !canWrite" @click="cancelEnvironmentForm">Cancelar</button></div>
          </form>
        </section>

        <div v-if="selectedEnvironment" class="detail">
          <section class="panel" aria-labelledby="devices-title" :aria-busy="loading">
            <div class="panel-heading"><h2 id="devices-title" ref="devicesTitle" tabindex="-1">Dispositivos de {{ selectedEnvironment.name }}</h2>
            <button v-if="canWrite && !showDeviceForm" ref="deviceOpenButton" data-test="open-device-form" class="primary" :disabled="busy || loading || selectionFailed" type="button" @click="openDeviceForm">Adicionar dispositivo</button></div>
            <p v-if="selectionFailed" class="joint-error" role="status">A carga conjunta de dispositivos e limites não foi confirmada. Não é possível concluir que o ambiente esteja vazio.</p>
            <button v-if="selectionFailed" ref="selectionRetryButton" data-test="retry-selection" type="button" :disabled="loading || busy" @click="retrySelection">Consultar dispositivos e limites novamente</button>
            <p v-if="!loading && !selectionFailed && devices.length === 0">Nenhum dispositivo cadastrado neste ambiente. {{ canWrite ? 'Adicione um dispositivo para começar a monitorar.' : 'Um operador ou administrador precisa cadastrar um dispositivo.' }}</p>
            <ul class="item-list">
              <li v-for="device in devices" :key="device.id">
                <div class="device-info"><strong>{{ device.name }}</strong><span>MQTT ID: {{ device.mqtt_device_id }}</span><span class="device-state" :class="{ active: device.is_active }">{{ device.is_active ? 'Cadastro ativo' : 'Cadastro desativado' }}</span></div>
                <form :aria-busy="busy" v-if="canWrite && editingDeviceId === device.id" class="edit-form" novalidate @submit.prevent="saveDevice(device.id)"><label class="edit-name">Nome do dispositivo<input id="device-edit-name" v-model="deviceEditName" :aria-label="`Nome do dispositivo ${device.name}`" maxlength="120" required :disabled="busy" :aria-invalid="Boolean(fieldErrors.deviceEdit)" :aria-describedby="fieldErrors.deviceEdit ? 'device-edit-name-error' : undefined" @input="clearFieldError('deviceEdit')" /></label><p v-if="fieldErrors.deviceEdit" id="device-edit-name-error" class="field-error">{{ fieldErrors.deviceEdit }}</p><button type="submit" :aria-label="`${busy ? 'Salvando' : 'Salvar'} dispositivo ${device.name}`" :disabled="busy">{{ busy ? 'Salvando…' : 'Salvar' }}</button><button type="button" :aria-label="`Cancelar edição do dispositivo ${device.name}`" :disabled="busy" @click="cancelDeviceEdit">Cancelar</button></form>
                <div v-else-if="canWrite" class="actions">
                  <button type="button" :disabled="busy" :data-edit-device="device.id" :aria-label="`Renomear dispositivo ${device.name}`" @click="editDevice(device)">Renomear dispositivo</button>
                  <button v-if="device.is_active" type="button" class="danger" :aria-label="`Desativar cadastro de ${device.name}`" :disabled="busy" @click="disableDevice(device, $event)">Desativar cadastro</button>
                </div>
              </li>
            </ul>
            <p class="section-note">O MQTT ID permanece imutável após o cadastro.</p>
            <form :aria-busy="busy" v-if="canWrite && showDeviceForm" class="fields add-form" novalidate @submit.prevent="addDevice">
              <h3>Adicionar dispositivo em {{ selectedEnvironment.name }}</h3>
              <label for="device-name">Nome do dispositivo</label>
              <input id="device-name" ref="deviceNameInput" v-model="deviceName" maxlength="120" required placeholder="Ex.: Sensor principal" :disabled="busy" :aria-invalid="Boolean(fieldErrors.device)" :aria-describedby="fieldErrors.device ? 'device-name-error' : undefined" @input="clearFieldError('device')" />
              <p v-if="fieldErrors.device" id="device-name-error" class="field-error">{{ fieldErrors.device }}</p>
              <label for="mqtt-id">Identificador MQTT</label>
              <input id="mqtt-id" :aria-describedby="`mqtt-id-hint${fieldErrors.mqtt ? ' mqtt-id-error' : ''}`" v-model="mqttDeviceId" maxlength="64" pattern="[A-Za-z0-9._-]+" required placeholder="Ex.: esp32-camara-1" :disabled="busy" :aria-invalid="Boolean(fieldErrors.mqtt)" @input="clearFieldError('mqtt')" />
              <p v-if="fieldErrors.mqtt" id="mqtt-id-error" class="field-error">{{ fieldErrors.mqtt }}</p>
              <p id="mqtt-id-hint" class="hint">Use o mesmo identificador configurado no ESP32. Ele não pode ser alterado depois.</p>
              <div class="actions"><button class="primary" type="submit" :disabled="busy || !canWrite">{{ busy ? 'Cadastrando…' : 'Cadastrar dispositivo' }}</button><button data-test="cancel-device-form" type="button" aria-label="Cancelar inclusão de dispositivo" :disabled="busy || !canWrite" @click="cancelDeviceForm">Cancelar</button></div>
            </form>
          </section>

          <section v-if="rulesBaseline" class="panel" aria-labelledby="rules-title">
            <h2 id="rules-title">Limites de temperatura de {{ selectedEnvironment.name }}</h2>
            <div class="rules-summary" role="group" aria-labelledby="rules-applied-title">
              <h3 id="rules-applied-title">Faixa em vigor</h3>
              <dl>
                <div><dt>Temperatura</dt><dd>{{ temperatureFormat.format(rulesBaseline.min_c) }}–{{ temperatureFormat.format(rulesBaseline.max_c) }} °C</dd></div>
                <div><dt>Margem de atenção</dt><dd>{{ temperatureFormat.format(rulesBaseline.attention_margin_c) }} °C</dd></div>
              </dl>
              <p v-if="selectionFailed" class="hint">Valores da última consulta ou gravação confirmada.</p>
            </div>
            <form v-if="canWrite && rules" aria-labelledby="rules-edit-title" :aria-busy="busy" class="fields" novalidate @submit.prevent="saveRules">
              <h3 id="rules-edit-title">Editar limites</h3>
              <p v-if="selectionFailed && rulesDirty" class="joint-error">Rascunho dos limites preservado. A nova consulta falhou.</p>
              <p v-if="Object.values(ruleErrors).some(Boolean)" role="alert" class="error">Revise os limites destacados abaixo.</p>
              <div class="rule-grid"><div>
              <label for="min-c">Mínimo (°C)</label><input id="min-c" v-model.number="rules.min_c" type="number" step="0.01" required :disabled="busy || !canWrite" :aria-invalid="Boolean(ruleErrors.min_c)" :aria-describedby="ruleErrors.min_c ? 'min-c-error' : undefined" @input="clearRuleError('min_c')" />
              <p v-if="ruleErrors.min_c" id="min-c-error" class="field-error">{{ ruleErrors.min_c }}</p>
              </div><div>
              <label for="max-c">Máximo (°C)</label><input id="max-c" v-model.number="rules.max_c" type="number" step="0.01" required :disabled="busy || !canWrite" :aria-invalid="Boolean(ruleErrors.max_c)" :aria-describedby="ruleErrors.max_c ? 'max-c-error' : undefined" @input="clearRuleError('max_c')" />
              <p v-if="ruleErrors.max_c" id="max-c-error" class="field-error">{{ ruleErrors.max_c }}</p>
              </div><div>
              <label for="margin-c">Margem de atenção (°C)</label><input id="margin-c" v-model.number="rules.attention_margin_c" type="number" step="0.01" min="0" required :disabled="busy || !canWrite" :aria-invalid="Boolean(ruleErrors.attention_margin_c)" :aria-describedby="`margin-c-hint${ruleErrors.attention_margin_c ? ' margin-c-error' : ''}`" @input="clearRuleError('attention_margin_c')" />
              <p v-if="ruleErrors.attention_margin_c" id="margin-c-error" class="field-error">{{ ruleErrors.attention_margin_c }}</p>
              </div></div>
              <p id="margin-c-hint" class="hint">Em uma faixa de 2 a 8 °C com margem de 0,5 °C, há Atenção de 2 a 2,5 °C e de 7,5 a 8 °C, dentro da faixa. A margem deve ser menor que metade da faixa.</p>
              <p v-if="rulesDirty" class="hint" role="status">Alterações pendentes de salvamento.</p>
              <p v-if="rulesSaveError" id="rules-save-error" role="alert" class="field-error">{{ rulesSaveError }}</p>
              <button class="primary" type="submit" :disabled="busy || loading">{{ busy ? 'Salvando…' : 'Salvar limites' }}</button>
            </form>
          </section>
        </div>
      </div>
    </div>
    <Teleport to="body">
      <dialog ref="deactivationDialog" class="deactivation-dialog cs-controls" aria-labelledby="deactivation-title" aria-describedby="deactivation-description" @cancel.prevent="!busy && closeDeactivation()">
        <template v-if="deactivation">
        <h2 id="deactivation-title">Desativar cadastro de {{ deactivation.name }}?</h2>
        <p id="deactivation-description">O dispositivo sai das opções ativas do Monitoramento e o cadastro fica preservado. O equipamento mantém seu estado físico atual.</p>
        <p>MQTT ID: <strong>{{ deactivation?.mqtt_device_id }}</strong></p>
        <div class="actions"><button ref="deactivationCancel" data-test="cancel-deactivation" type="button" autofocus :disabled="busy" @click="closeDeactivation()">Cancelar</button><button data-test="confirm-deactivation" type="button" class="danger" :disabled="busy" @click="confirmDeactivation">{{ busy ? 'Desativando…' : 'Desativar cadastro' }}</button></div>
        </template>
      </dialog>
    </Teleport>
  </main>
</template>

<style scoped>
.manage { padding: var(--cs-space-48); }
.shell { max-width: 1200px; margin-inline: auto; }

.heading { margin-bottom: var(--cs-space-32); }
.heading p { color: var(--cs-color-ink-muted); }
h1 { margin: var(--cs-space-8) 0; font-size: var(--cs-type-32); }
h2 { margin: 0 0 var(--cs-space-24); font-size: var(--cs-type-20); }
.grid { display: grid; grid-template-columns: minmax(240px, 300px) minmax(0, 1fr); gap: var(--cs-space-24); align-items: start; }
.detail { display: grid; min-width: 0; gap: var(--cs-space-24); }
.panel { min-width: 0; padding: var(--cs-space-24); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); overflow-wrap: anywhere; }
.panel-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: start; gap: var(--cs-space-16); }.panel-heading h2 { flex: 1 1 240px; }.panel-heading button { flex: 0 1 auto; }
.section-note { margin-top: var(--cs-space-16); font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }.panel > .section-note:first-of-type { margin-top: 0; }.joint-error { margin-block: var(--cs-space-16); color: var(--cs-color-status-stale); }
.environment-picker, .mobile-rename { display: none; }
.fields, .inline-form { display: grid; gap: var(--cs-space-8); }
.fields label:not(:first-child) { margin-top: var(--cs-space-8); }
.rule-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cs-space-16); }.rule-grid > div { min-width: 0; display: grid; gap: var(--cs-space-8); align-content: start; }.fields > .primary { justify-self: start; margin-top: var(--cs-space-16); }
.add-action, .add-form { margin-top: var(--cs-space-24); }
.add-form { padding-top: var(--cs-space-24); border-top: 1px solid var(--cs-color-line); }
h3 { margin: 0; font-size: var(--cs-type-16); }
.item-list { padding: 0; margin: var(--cs-space-24) 0 0; list-style: none; }
.item-list li { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--cs-space-12); padding: var(--cs-space-12); border-top: 1px solid var(--cs-color-line); }
.desktop-environments li { display: grid; justify-content: stretch; gap: var(--cs-space-4); padding-inline: 0; }
.item-name { min-width: 0; text-align: left; }
.item-name[aria-pressed='true'] { border-color: var(--cs-color-accent); background: var(--cs-color-surface-muted); color: var(--cs-color-accent); font-weight: 650; }
.small-action { justify-self: start; border-color: transparent; color: var(--cs-color-ink-muted); }
.device-info { display: grid; min-width: 0; gap: var(--cs-space-4); overflow-wrap: anywhere; }
.device-info span { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.device-info .device-state { justify-self: start; padding: var(--cs-space-4) var(--cs-space-8); border-radius: var(--cs-radius-4); background: var(--cs-color-stale-surface); color: var(--cs-color-status-stale); }.device-info .device-state.active { background: var(--cs-color-normal-surface); color: var(--cs-color-status-normal); }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--cs-space-16); }
.edit-form { display: flex; flex-wrap: wrap; align-items: end; gap: var(--cs-space-8); width: 100%; }
.edit-name { display: grid; gap: var(--cs-space-8); flex: 1 1 12rem; min-width: 0; }
.rules-summary { display: grid; gap: var(--cs-space-8); margin-bottom: var(--cs-space-24); padding: var(--cs-space-16); border-radius: var(--cs-radius-8); background: var(--cs-color-surface-muted); }
.rules-summary dl { display: flex; flex-wrap: wrap; gap: var(--cs-space-8) var(--cs-space-32); }
.rules-summary dt { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.rules-summary dd { font-weight: 650; font-variant-numeric: tabular-nums; }
.deactivation-dialog { width: min(100% - 32px, 540px); max-width: none; max-height: calc(100dvh - 32px); margin: auto; padding: var(--cs-space-24); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-panel); background: var(--cs-color-surface); color: var(--cs-color-ink); overflow-y: auto; overflow-wrap: anywhere; }.deactivation-dialog::backdrop { background: rgb(8 27 32 / .55); }.deactivation-dialog h2 { margin-bottom: var(--cs-space-16); }.deactivation-dialog p { margin-top: var(--cs-space-12); }.deactivation-dialog .actions { margin-top: var(--cs-space-24); }.deactivation-dialog button { flex: 1 1 180px; }
@media (max-width: 1100px) { .manage { padding: var(--cs-space-16); } .grid { grid-template-columns: minmax(0, 1fr); } h1 { font-size: var(--cs-type-24); line-height: 1.3333; }
.desktop-environments { display: none; }.environment-picker { display: grid; gap: var(--cs-space-8); }.environment-picker select { min-height: var(--cs-control-min-height); min-width: 0; width: 100%; border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); padding: var(--cs-space-8); }.mobile-rename { display: block; margin-top: var(--cs-space-12); }
.panel { padding: var(--cs-space-16); } }
@media (max-width: 600px) { .rule-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
