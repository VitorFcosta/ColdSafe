import { clearSession, sessionToken } from './session'

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

export type Environment = Readonly<{ id: string; name: string }>
export type Device = Readonly<{
  id: string
  environment_id: string
  mqtt_device_id: string
  name: string
  is_active: boolean
}>
export type Rules = { min_c: number; max_c: number; attention_margin_c: number }

export class CatalogAccessError extends Error {
  constructor(readonly status: number, message = 'Acesso ao catálogo indisponível.') { super(message) }
}

export async function catalogRequest<T>(token: string, path: string, method = 'GET', body?: object): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}/api/v1${path}`, {
      method,
      headers: { accept: 'application/json', authorization: `Bearer ${token}`, ...(body ? { 'content-type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
  } catch {
    throw new Error('Não foi possível conectar à API. Tente novamente.')
  }
  if (response.status === 401 && sessionToken.value === token) clearSession()
  const accessDenied = [401, 403, 404].includes(response.status)
  let payload: { success?: boolean; data?: T; error?: { message?: string } }
  try { payload = await response.json() } catch {
    if (accessDenied) throw new CatalogAccessError(response.status, 'A API retornou uma resposta inválida.')
    throw new Error('A API retornou uma resposta inválida.')
  }
  if (!response.ok || payload.success !== true || payload.data === undefined) {
    const message = payload.error?.message ?? 'Não foi possível concluir a operação.'
    if (accessDenied) throw new CatalogAccessError(response.status, message)
    throw new Error(message)
  }
  return payload.data
}

export async function listEnvironments(token: string): Promise<Environment[]> {
  const data = await catalogRequest<Environment[]>(token, '/environments')
  if (!Array.isArray(data)) throw new Error('A API retornou ambientes inválidos.')
  return data
}

export const createEnvironment = (token: string, name: string) =>
  catalogRequest<Environment>(token, '/environments', 'POST', { name })
export const updateEnvironment = (token: string, id: string, name: string) =>
  catalogRequest<Environment>(token, `/environments/${encodeURIComponent(id)}`, 'PATCH', { name })

export async function listDevices(token: string, environmentId: string): Promise<Device[]> {
  const data = await catalogRequest<Device[]>(token, `/environments/${encodeURIComponent(environmentId)}/devices`)
  if (!Array.isArray(data)) throw new Error('A API retornou dispositivos inválidos.')
  return data
}

export const createDevice = (token: string, environmentId: string, name: string, mqttDeviceId: string) =>
  catalogRequest<Device>(token, `/environments/${encodeURIComponent(environmentId)}/devices`, 'POST', { name, mqtt_device_id: mqttDeviceId })
export const updateDevice = (token: string, id: string, name: string) =>
  catalogRequest<Device>(token, `/devices/${encodeURIComponent(id)}`, 'PATCH', { name })
export const deactivateDevice = (token: string, id: string) =>
  catalogRequest<Device>(token, `/devices/${encodeURIComponent(id)}`, 'DELETE')
export const getRules = (token: string, environmentId: string) =>
  catalogRequest<Rules>(token, `/environments/${encodeURIComponent(environmentId)}/rules`)
export const updateRules = (token: string, environmentId: string, rules: Rules) =>
  catalogRequest<Rules>(token, `/environments/${encodeURIComponent(environmentId)}/rules`, 'PUT', rules)
