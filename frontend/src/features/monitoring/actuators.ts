import { isDeviceId, isRecord, isUtcTime, isUuid, parseAiotCommand } from './aiot-api'
import { aiotEnabled } from './monitoring-version'

export type ActuatorCommand = Readonly<{
  schema_version: 2 | 3
  command_id: string
  device_id: string
  actuator: 'led' | 'buzzer'
  desired_state: boolean
  confirmed_state: boolean | null
  status: 'pending' | 'confirmed' | 'rejected' | 'unconfirmed'
  actuator_id?: string
  event_id?: string
  occurred_at?: string
  received_at?: string
}>

export type ActuatorState = Readonly<{
  led: ActuatorCommand | null
  buzzer: ActuatorCommand | null
}>

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function isCommand(value: unknown): value is ActuatorCommand {
  if (!isRecord(value)) return false
  const versionValid = value.schema_version === 2 || (value.schema_version === 3 &&
    isUuid(value.command_id) && isDeviceId(value.device_id) &&
    (value.actuator_id === undefined || isUuid(value.actuator_id)) &&
    (value.event_id === undefined || isUuid(value.event_id)) &&
    (value.occurred_at === undefined || isUtcTime(value.occurred_at)) &&
    (value.received_at === undefined || isUtcTime(value.received_at)))
  return versionValid && typeof value.command_id === 'string' &&
    typeof value.device_id === 'string' &&
    (value.actuator === 'led' || value.actuator === 'buzzer') &&
    typeof value.desired_state === 'boolean' &&
    ((value.status === 'confirmed' && value.confirmed_state === value.desired_state) ||
      ((value.status === 'pending' || value.status === 'rejected' || value.status === 'unconfirmed') && value.confirmed_state === null))
}

async function readData(url: string, token: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${baseUrl.replace(/\/+$/, '')}${url}`, {
    ...init,
    headers: {
      accept: 'application/json',
      authorization: `Bearer ${token}`,
      ...(init?.body ? { 'content-type': 'application/json' } : {}),
    },
  })
  if (!response.ok) throw new Error('Não foi possível consultar o estado do atuador.')
  const body: unknown = await response.json()
  if (!isRecord(body) || body.success !== true) throw new Error('Resposta inválida da API.')
  return body.data
}

export async function fetchActuators(token: string, deviceUuid: string): Promise<ActuatorState> {
  if (aiotEnabled) {
    const data = await readData(`/api/v3/monitoring/summary?${new URLSearchParams({ device_id: deviceUuid })}`, token)
    if (!isRecord(data) || !isRecord(data.commands) || !isRecord(data.device) || data.device.id !== deviceUuid ||
      !isRecord(data.environment) || !isUuid(data.environment.id)) throw new Error('Estado inválido dos atuadores.')
    const led = data.commands.led === null ? null : parseAiotCommand(data.commands.led, deviceUuid, data.environment.id)
    const buzzer = data.commands.buzzer === null ? null : parseAiotCommand(data.commands.buzzer, deviceUuid, data.environment.id)
    if ((data.commands.led !== null && led?.actuator !== 'led') ||
      (data.commands.buzzer !== null && buzzer?.actuator !== 'buzzer')) throw new Error('Estado inválido dos atuadores.')
    return { led, buzzer }
  }
  const data = await readData(`/api/v1/devices/${encodeURIComponent(deviceUuid)}/actuators`, token)
  if (!isRecord(data) || !(data.led === null || isCommand(data.led)) ||
      !(data.buzzer === null || isCommand(data.buzzer))) {
    throw new Error('Estado inválido dos atuadores.')
  }
  return { led: data.led, buzzer: data.buzzer }
}

export async function requestLed(token: string, deviceUuid: string, desiredState: boolean): Promise<ActuatorCommand> {
  const data = await readData(`/api/${aiotEnabled ? 'v3' : 'v1'}/devices/${encodeURIComponent(deviceUuid)}/led/commands`, token, {
    method: 'POST', body: JSON.stringify({ desired_state: desiredState }),
  })
  const command = aiotEnabled ? parseAiotCommand(data, deviceUuid) : data
  if (!isCommand(command) || command.actuator !== 'led' || command.desired_state !== desiredState) throw new Error('Comando inválido da API.')
  return command
}

export async function fetchCommand(token: string, commandId: string): Promise<ActuatorCommand> {
  const data = await readData(`/api/${aiotEnabled ? 'v3' : 'v1'}/commands/${encodeURIComponent(commandId)}`, token)
  const command = aiotEnabled ? parseAiotCommand(data) : data
  if (!isCommand(command) || command.command_id !== commandId) throw new Error('Comando inválido da API.')
  return command
}
