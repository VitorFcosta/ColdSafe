import { computed, ref, watch } from 'vue'
import { isRecord, isUuid } from '../monitoring/aiot-api'

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const storageKey = 'coldsafe-session'

export type DashboardSelection = { environmentId: string; deviceUuid: string; period: string }
export type MonitoringSelection = Pick<DashboardSelection, 'environmentId' | 'deviceUuid'>
export type KnownJobs = { generation?: { jobId: string }; training?: { jobId: string; datasetId: string } }
type StoredSession = { token: string; expires_at: string; dashboard_selection?: DashboardSelection; monitoring_selection?: MonitoringSelection | null; known_jobs?: unknown }
let invalidKnownJob = false

function readKnownJobs(value: unknown): KnownJobs {
  if (value === undefined) return {}
  if (!isRecord(value)) { invalidKnownJob = true; return {} }
  let result: KnownJobs = {}
  for (const kind of ['generation', 'training'] as const) {
    const reference = value[kind]
    if (reference === undefined) continue
    if (!isRecord(reference) || !isUuid(reference.jobId) || (kind === 'training' && !isUuid(reference.datasetId))) {
      invalidKnownJob = true
      continue
    }
    result = kind === 'generation' ? { ...result, generation: { jobId: reference.jobId } }
      : { ...result, training: { jobId: reference.jobId, datasetId: reference.datasetId as string } }
  }
  return result
}

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
export const sessionIdentityState = ref<'pending' | 'verified' | 'error'>('pending')
export const sessionIdentityError = ref('')
export const sessionUser = ref<{ id: string; email: string } | null>(null)
let sessionRevision = 0
const verifiedIdentity = ref<{ token: string; revision: number } | null>(null)
let identityRequest: { token: string; revision: number; promise: Promise<void>; controller: AbortController } | null = null
export const isIdentityVerified = computed(() => Boolean(sessionToken.value && sessionRole.value &&
  sessionIdentityState.value === 'verified' && verifiedIdentity.value?.token === sessionToken.value &&
  verifiedIdentity.value.revision === sessionRevision))
export const canWrite = computed(() => Boolean(sessionToken.value) && (sessionRole.value === 'operator' || sessionRole.value === 'admin'))
export const knownJobs = ref<KnownJobs>(readKnownJobs(currentSession?.known_jobs))
export const knownJobsNotice = ref(invalidKnownJob ? 'Uma referência salva era inválida e foi removida. Consulte um trabalho autorizado para registrá-lo novamente.' : '')

function persistKnownJobs(value: KnownJobs): void {
  knownJobs.value = value
  if (!currentSession || currentSession.token !== sessionToken.value) return
  currentSession = { ...currentSession, known_jobs: value }
  try { sessionStorage.setItem(storageKey, JSON.stringify(currentSession)) } catch { /* In-memory tab only. */ }
}
if (currentSession?.known_jobs !== undefined) persistKnownJobs(knownJobs.value)

export function rememberKnownJob(token: string, kind: keyof KnownJobs, reference: { jobId: string; datasetId?: string }): void {
  if (!currentSession || currentSession.token !== token || sessionToken.value !== token || sessionRole.value !== 'admin' ||
    Date.parse(currentSession.expires_at) <= Date.now() || !isUuid(reference.jobId) || (kind === 'training' && !isUuid(reference.datasetId))) return
  persistKnownJobs(kind === 'generation' ? { ...knownJobs.value, generation: { jobId: reference.jobId } }
    : { ...knownJobs.value, training: { jobId: reference.jobId, datasetId: reference.datasetId! } })
}

export function forgetKnownJob(token: string, kind: keyof KnownJobs, jobId?: string): void {
  if (token !== sessionToken.value || !knownJobs.value[kind] || (jobId !== undefined && knownJobs.value[kind]?.jobId !== jobId)) return
  const { [kind]: _removed, ...remaining } = knownJobs.value
  persistKnownJobs(remaining)
  knownJobsNotice.value = 'Uma referência de retomada está indisponível e foi removida. Consulte outro trabalho autorizado.'
}

export function clearKnownJobs(): void {
  persistKnownJobs({})
  knownJobsNotice.value = ''
}
watch(sessionRole, (role) => { if (role && role !== 'admin') clearKnownJobs() }, { flush: 'sync' })
export const dashboardSelection = ref<DashboardSelection | null>(
  currentSession?.dashboard_selection &&
  typeof currentSession.dashboard_selection.environmentId === 'string' &&
  typeof currentSession.dashboard_selection.deviceUuid === 'string' &&
  typeof currentSession.dashboard_selection.period === 'string'
    ? currentSession.dashboard_selection : null,
)
export const monitoringSelection = ref<MonitoringSelection | null>(currentSession && 'monitoring_selection' in currentSession
  ? currentSession.monitoring_selection ?? null : dashboardSelection.value)
export const validatedMonitoringSelection = ref<MonitoringSelection | null>(null)

export function saveMonitoringSelection(selection: MonitoringSelection): void {
  if (!currentSession || currentSession.token !== sessionToken.value) return
  monitoringSelection.value = { ...selection }
  currentSession = { ...currentSession, monitoring_selection: { ...selection } }
  try { sessionStorage.setItem(storageKey, JSON.stringify(currentSession)) } catch { /* In-memory session only. */ }
}

export function clearMonitoringSelection(): void {
  monitoringSelection.value = null
  validatedMonitoringSelection.value = null
  if (currentSession) {
    currentSession = { ...currentSession, monitoring_selection: null }
    try { sessionStorage.setItem(storageKey, JSON.stringify(currentSession)) } catch { /* In-memory session only. */ }
  }
}

export function saveDashboardSelection(selection: DashboardSelection): void {
  if (!currentSession || currentSession.token !== sessionToken.value) return
  dashboardSelection.value = selection
  currentSession = { ...currentSession, dashboard_selection: selection }
  try { sessionStorage.setItem(storageKey, JSON.stringify(currentSession)) } catch { /* In-memory session only. */ }
}

function isCurrentSession(token: string, revision: number): boolean {
  return sessionToken.value === token && sessionRevision === revision
}

function invalidateIdentity(): void {
  sessionRevision += 1
  identityRequest?.controller.abort()
  identityRequest = null
  sessionRole.value = null
  sessionUser.value = null
  verifiedIdentity.value = null
  sessionIdentityError.value = ''
  sessionIdentityState.value = 'pending'
}

export function setSession(token: string, expiresAt: string): void {
  invalidateIdentity()
  clearKnownJobs()
  clearMonitoringSelection()
  currentSession = { token, expires_at: expiresAt }
  sessionToken.value = token
  dashboardSelection.value = null
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(currentSession))
  } catch {
    // The current tab can still use its in-memory session.
  }
}

export function clearSession(): void {
  invalidateIdentity()
  clearKnownJobs()
  clearMonitoringSelection()
  currentSession = null
  sessionToken.value = null
  dashboardSelection.value = null
  try { sessionStorage.removeItem(storageKey) } catch { /* Storage unavailable. */ }
}

export async function logout(): Promise<void> {
  const token = sessionToken.value
  const revision = sessionRevision
  if (!token) return
  let response: Response
  try {
    response = await fetch(`${baseUrl}/api/v1/auth/logout`, {
      method: 'POST', headers: { authorization: `Bearer ${token}` },
    })
  } catch {
    if (!isCurrentSession(token, revision)) return
    throw new Error('Não foi possível encerrar a sessão na API. Tente novamente.')
  }
  if (!isCurrentSession(token, revision)) return
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

function identityFailure(message: string): never {
  sessionIdentityError.value = message
  sessionIdentityState.value = 'error'
  throw new Error(message)
}

type SessionIdentity = { user: { id: string; email: string }; role: NonNullable<typeof sessionRole.value> }

async function readSessionIdentity(token: string, signal: AbortSignal): Promise<SessionIdentity | null> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}/api/v1/auth/me`, { headers: { authorization: `Bearer ${token}` }, signal })
  } catch {
    throw new Error('Não foi possível consultar as permissões da conta. Tente novamente.')
  }
  if (response.status === 401) return null
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error('A API retornou uma identidade inválida. Tente verificar novamente.')
  }
  if (!response.ok || payload?.success !== true || typeof payload.data?.user_id !== 'string' || !payload.data.user_id.trim() ||
    typeof payload.data.email !== 'string' || !payload.data.email.trim() || !['viewer', 'operator', 'admin'].includes(payload.data.role)) {
    throw new Error('A API retornou uma identidade inválida. Tente verificar novamente.')
  }
  return { user: { id: payload.data.user_id, email: payload.data.email }, role: payload.data.role }
}

export function refreshSessionIdentity(): Promise<void> {
  const token = sessionToken.value
  const revision = sessionRevision
  if (!token) return Promise.resolve()
  if (identityRequest?.token === token && identityRequest.revision === revision) return identityRequest.promise
  sessionRole.value = null
  sessionUser.value = null
  verifiedIdentity.value = null
  sessionIdentityError.value = ''
  const controller = new AbortController()
  const timeoutMessage = 'A verificação de identidade demorou demais. Tente novamente.'
  let onAbort!: () => void
  const aborted = new Promise<never>((_resolve, reject) => {
    onAbort = () => reject(new Error(timeoutMessage))
    controller.signal.addEventListener('abort', onAbort, { once: true })
  })
  // O mesmo prazo cobre conexão e JSON, mesmo se o transporte não resolver após abort.
  const deadline = setTimeout(() => controller.abort(), 8_000)
  const promise = Promise.race([readSessionIdentity(token, controller.signal), aborted]).catch((cause) => {
    if (!isCurrentSession(token, revision)) return
    identityFailure(controller.signal.aborted ? timeoutMessage : cause instanceof Error ? cause.message : 'Não foi possível verificar a identidade.')
  }).then((identity) => {
    if (!isCurrentSession(token, revision) || controller.signal.aborted || identity === undefined) return
    if (identity === null) { clearSession(); throw new Error('Sessão inválida. Entre novamente.') }
    sessionUser.value = identity.user
    sessionRole.value = identity.role
    verifiedIdentity.value = { token, revision }
    sessionIdentityState.value = 'verified'
  }).finally(() => {
    clearTimeout(deadline)
    controller.signal.removeEventListener('abort', onAbort)
    if (identityRequest?.promise === promise) identityRequest = null
  })
  identityRequest = { token, revision, promise, controller }
  sessionIdentityState.value = 'pending'
  return promise
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
  if (response.status >= 500) throw new Error('O serviço de acesso está indisponível. Tente novamente em instantes.')
  if (response.status === 429) throw new Error('Muitas tentativas de acesso. Aguarde antes de tentar novamente.')
  if (response.status === 401) throw new Error('Email ou senha inválidos.')
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error('O serviço de acesso retornou uma resposta inválida. Tente novamente.')
  }
  if (!response.ok || payload?.success !== true) {
    throw new Error(typeof payload?.error?.message === 'string' ? payload.error.message : 'Não foi possível concluir a operação. Tente novamente.')
  }
  return payload.data as T
}
