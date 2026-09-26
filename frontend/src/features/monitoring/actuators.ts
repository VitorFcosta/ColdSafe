export type ActuatorCommand = Readonly<{
  schema_version: 2
  command_id: string
  device_id: string
  actuator: 'led' | 'buzzer'
  desired_state: boolean
  confirmed_state: boolean | null
  status: 'pending' | 'confirmed' | 'rejected' | 'unconfirmed'
}>

export type ActuatorState = Readonly<{
  led: ActuatorCommand | null
  buzzer: ActuatorCommand | null
}>

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function isCommand(value: unknown): value is ActuatorCommand {
  if (!isRecord(value)) return false
  return value.schema_version === 2 && typeof value.command_id === 'string' &&
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
  const data = await readData(`/api/v1/devices/${encodeURIComponent(deviceUuid)}/actuators`, token)
  if (!isRecord(data) || !(data.led === null || isCommand(data.led)) ||
      !(data.buzzer === null || isCommand(data.buzzer))) {
    throw new Error('Estado inválido dos atuadores.')
  }
  return { led: data.led, buzzer: data.buzzer }
}

export async function requestLed(token: string, deviceUuid: string, desiredState: boolean): Promise<ActuatorCommand> {
  const data = await readData(`/api/v1/devices/${encodeURIComponent(deviceUuid)}/led/commands`, token, {
    method: 'POST', body: JSON.stringify({ desired_state: desiredState }),
  })
  if (!isCommand(data) || data.actuator !== 'led') throw new Error('Comando inválido da API.')
  return data
}

export async function fetchCommand(token: string, commandId: string): Promise<ActuatorCommand> {
  const data = await readData(`/api/v1/commands/${encodeURIComponent(commandId)}`, token)
  if (!isCommand(data)) throw new Error('Comando inválido da API.')
  return data
}
