import { ref } from 'vue'

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const storageKey = 'coldsafe-session'

type StoredSession = { token: string; expires_at: string }

function restoreSession(): string | null {
  try {
    const stored = sessionStorage.getItem(storageKey)
    if (!stored) return null
    const session: StoredSession = JSON.parse(stored)
    if (typeof session.token === 'string' && Date.parse(session.expires_at) > Date.now()) return session.token
    sessionStorage.removeItem(storageKey)
  } catch {
    // Storage may be unavailable (privacy settings or server rendering).
  }
  return null
}

export const sessionToken = ref<string | null>(restoreSession())

export function setSession(token: string, expiresAt: string): void {
  sessionToken.value = token
  try {
    sessionStorage.setItem(storageKey, JSON.stringify({ token, expires_at: expiresAt }))
  } catch {
    // The current tab can still use its in-memory session.
  }
}

export function clearSession(): void {
  sessionToken.value = null
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
}

export async function register(email: string, password: string): Promise<void> {
  await accountRequest('/auth/register', { email, password })
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
