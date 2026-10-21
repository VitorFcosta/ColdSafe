import { onUnmounted, ref, watch, type Ref } from 'vue'
import { canWrite } from '../account/session'
import { fetchActuators, fetchCommand, isCommand, requestLed, type ActuatorCommand } from './actuators'
import { aiotEnabled } from './monitoring-version'
import type { MonitoringEvent } from './use-monitoring-summary'

export type ActuatorPhase = 'idle' | 'loading' | 'ready' | 'error'

export function actuatorLabel(command: ActuatorCommand | null): string {
  if (command === null) return 'Sem confirmação registrada'
  if (command.status === 'confirmed') return command.confirmed_state ? 'Ligado' : 'Desligado'
  if (command.status === 'pending') return 'Aguardando confirmação'
  return command.status === 'rejected' ? 'Comando rejeitado' : 'Sem confirmação'
}

export function useActuators(
  token: Ref<string | null>, deviceId: Ref<string | null>, refreshRevision: Ref<number>,
  connectionState: Ref<string>, legacyEvent?: Ref<MonitoringEvent | null>,
) {
  const led = ref<ActuatorCommand | null>(null)
  const buzzer = ref<ActuatorCommand | null>(null)
  const actuatorPhase = ref<ActuatorPhase>('idle')
  const commandError = ref('')
  const commandSubmitting = ref(false)
  let latestActuatorRequest = 0
  let commandRevision = 0
  let pendingTimer: ReturnType<typeof setInterval> | null = null
  let pendingChecks = 0
  let disposed = false

  function stopPendingCheck() {
    if (pendingTimer !== null) clearInterval(pendingTimer)
    pendingTimer = null
    pendingChecks = 0
  }

  function startPendingCheck(commandId: string, id: string) {
    stopPendingCheck()
    pendingTimer = setInterval(async () => {
      const currentToken = token.value
      if (!currentToken || deviceId.value !== id || pendingChecks++ >= 35) {
        stopPendingCheck()
        return
      }
      const current = () => !disposed && deviceId.value === id && token.value === currentToken &&
        led.value?.command_id === commandId && led.value.status === 'pending'
      try {
        const result = await fetchCommand(currentToken, commandId)
        if (!current()) return
        led.value = result
        if (result.status !== 'pending') stopPendingCheck()
      } catch {
        if (current()) commandError.value = 'Confirmação indisponível. Consulte o estado novamente.'
      }
    }, 1000)
  }

  async function loadActuators(id: string) {
    const currentToken = token.value
    if (disposed || !currentToken || deviceId.value !== id || commandSubmitting.value) return
    const requestId = ++latestActuatorRequest
    actuatorPhase.value = 'loading'
    try {
      const result = await fetchActuators(currentToken, id)
      if (requestId !== latestActuatorRequest || deviceId.value !== id || token.value !== currentToken) return
      led.value = result.led
      buzzer.value = result.buzzer
      actuatorPhase.value = 'ready'
      if (result.led?.status === 'pending') startPendingCheck(result.led.command_id, id)
      else stopPendingCheck()
    } catch {
      if (requestId === latestActuatorRequest) actuatorPhase.value = 'error'
    }
  }

  async function toggleLed() {
    const currentToken = token.value
    const id = deviceId.value
    if (disposed || !canWrite.value || !currentToken || !id || commandSubmitting.value || led.value?.status === 'pending') return
    const requestId = ++commandRevision
    latestActuatorRequest += 1
    commandSubmitting.value = true
    commandError.value = ''
    try {
      const result = await requestLed(currentToken, id, led.value?.confirmed_state !== true)
      if (requestId !== commandRevision || deviceId.value !== id || token.value !== currentToken) return
      led.value = result
      actuatorPhase.value = 'ready'
      if (result.status === 'pending') startPendingCheck(result.command_id, id)
    } catch {
      if (requestId === commandRevision) commandError.value = 'Não foi possível enviar o comando. Tente novamente.'
    } finally {
      if (requestId === commandRevision) commandSubmitting.value = false
    }
  }

  watch([token, deviceId], ([currentToken, id]) => {
    latestActuatorRequest += 1
    commandRevision += 1
    led.value = null; buzzer.value = null
    commandError.value = ''; commandSubmitting.value = false
    stopPendingCheck()
    actuatorPhase.value = 'idle'
    if (currentToken && id) void loadActuators(id)
  }, { immediate: true, flush: 'sync' })

  watch(connectionState, (state, previous) => {
    if (state === 'connected' && previous !== 'connected' && deviceId.value) void loadActuators(deviceId.value)
  })
  watch(refreshRevision, () => {
    if (aiotEnabled && deviceId.value) void loadActuators(deviceId.value)
  })
  if (legacyEvent) watch(legacyEvent, (event) => {
    // v3 events invalidate REST state; a redelivery must not overwrite a newer ACK.
    if (!event || event.schema_version === 3 || event.type !== 'command_status' || !isCommand(event.data)) return
    if (event.data.actuator === 'led') led.value = event.data
    else buzzer.value = event.data
    if (event.data.actuator === 'led' && event.data.status !== 'pending') stopPendingCheck()
  }, { flush: 'sync' })
  onUnmounted(() => {
    disposed = true
    latestActuatorRequest += 1; commandRevision += 1
    stopPendingCheck()
  })
  return { led, buzzer, actuatorPhase, commandError, commandSubmitting, loadActuators, toggleLed }
}
