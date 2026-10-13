import { computed, ref } from 'vue'

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const storageKey = 'coldsafe-session'

export type DashboardSelection = { environmentId: string; deviceUuid: string; period: string }
type StoredSession = { token: string; expires_at: string; dashboard_selection?: DashboardSelection }

function restoreSession(): StoredSession | null {
  try {
    const stored = sessionStorage.getItem(storageKey)
    if (!stored) return null
    const session: StoredSession = JSON.parse(stored)
    if (typeof session.token === 'string' && Date.parse(session.expires_at) > Date.now()) return session
    sessionStorage.removeItem(storageKey)
  } catch {
    // Storage may be unavailable (privacy settings or server rendering).
  }
  return null
}

let currentSession = restoreSession()
export const sessionToken = ref<string | null>(currentSession?.token ?? null)
export const sessionRole = ref<'viewer' | 'operator' | 'admin' | null>(null)
export const canWrite = computed(() => Boolean(sessionToken.value) && (sessionRole.value === 'operator' || sessionRole.value === 'admin'))
export const dashboardSelection = ref<DashboardSelection | null>(
  currentSession?.dashboard_selection &&
  typeof currentSession.dashboard_selection.environmentId === 'string' &&
  typeof currentSession.dashboard_selection.deviceUuid === 'string' &&
  typeof currentSession.dashboard_selection.period === 'string'
    ? currentSession.dashboard_selection : null,
)

export function saveDashboardSelection(selection: DashboardSelection): void {
  if (!currentSession || currentSession.token !== sessionToken.value) return
  dashboardSelection.value = selection
  currentSession = { ...currentSession, dashboard_selection: selection }
  try { sessionStorage.setItem(storageKey, JSON.stringify(currentSession)) } catch { /* In-memory session only. */ }
}

export function setSession(token: string, expiresAt: string): void {
  currentSession = { token, expires_at: expiresAt }
  sessionToken.value = token
  sessionRole.value = null
  dashboardSelection.value = null
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(currentSession))
  } catch {
    // The current tab can still use its in-memory session.
  }
}

export function clearSession(): void {
  currentSession = null
  sessionToken.value = null
  sessionRole.value = null
  dashboardSelection.value = null
  try { sessionStorage.removeItem(storageKey) } catch { /* Storage unavailable. */ }
}

export async function logout(): Promise<void> {
  const token = sessionToken.value
  if (!token) return
  let response: Response
  try {
    response = await fetch(`${baseUrl}/api/v1/auth/logout`, {
      method: 'POST', headers: { authorization: `Bearer ${token}` },
    })
  } catch {
    throw new Error('Não foi possível encerrar a sessão na API. Tente novamente.')
  }
  if (response.status === 401) { clearSession(); return }
  if (!response.ok) throw new Error('Não foi possível encerrar a sessão na API. Tente novamente.')
  clearSession()
}

export async function login(email: string, password: string): Promise<void> {
  const data = await accountRequest<{ token: string; expires_at: string }>('/auth/login', { email, password })
  if (typeof data.token !== 'string' || !data.token || !Number.isFinite(Date.parse(data.expires_at))) {
    throw new Error('A API retornou uma sessão inválida.')
  }
  setSession(data.token, data.expires_at)
  await refreshSessionIdentity()
}

export async function register(email: string, password: string): Promise<void> {
  if (new TextEncoder().encode(password).length > 72) throw new Error('A senha de cadastro deve ter até 72 bytes UTF-8.')
  await accountRequest('/auth/register', { email, password })
}

export async function refreshSessionIdentity(): Promise<void> {
  const token = sessionToken.value
  if (!token) return
  sessionRole.value = null
  let response: Response
  try {
    response = await fetch(`${baseUrl}/api/v1/auth/me`, { headers: { authorization: `Bearer ${token}` } })
  } catch {
    throw new Error('Não foi possível consultar as permissões da conta. Tente novamente.')
  }
  if (sessionToken.value !== token) return
  if (response.status === 401) { clearSession(); throw new Error('Sessão inválida. Entre novamente.') }
  const payload = await response.json()
  if (sessionToken.value !== token) return
  if (!response.ok || payload?.success !== true || typeof payload.data?.user_id !== 'string' ||
    typeof payload.data.email !== 'string' || !['viewer', 'operator', 'admin'].includes(payload.data.role)) {
    throw new Error('A API retornou uma identidade inválida.')
  }
  sessionRole.value = payload.data.role
}

if (sessionToken.value) {
  void refreshSessionIdentity().catch(() => { /* Unknown permissions keep this tab read-only. */ })
}

async function accountRequest<T>(path: string, body: object): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}/api/v1${path}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
    })
  } catch {
    throw new Error('Não foi possível conectar à API. Tente novamente.')
  }
  const payload = await response.json()
  if (!response.ok || payload?.success !== true) {
    throw new Error(payload?.error?.message ?? 'Não foi possível concluir a operação.')
  }
  return payload.data as T
}
