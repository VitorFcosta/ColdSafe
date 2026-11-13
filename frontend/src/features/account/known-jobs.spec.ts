// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const generation = '00000000-0000-4000-8000-000000000001'
const training = '00000000-0000-4000-8000-000000000002'
const dataset = '00000000-0000-4000-8000-000000000003'
const nextJob = '00000000-0000-4000-8000-000000000004'
beforeEach(() => {
  sessionStorage.clear(); vi.resetModules()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200,
    json: async () => ({ success: true, data: { user_id: generation, email: 'admin@example.invalid', role: 'admin' } }) }))
})
afterEach(async () => { (await import('./session')).clearSession(); vi.unstubAllGlobals() })
async function setup() {
  const session = await import('./session')
  session.setSession('current', '2099-01-01T00:00:00Z')
  await session.refreshSessionIdentity()
  return session
}
it('guarda no máximo uma referência mínima por tipo e substitui somente o tipo confirmado', async () => {
  const session = await setup()
  session.rememberKnownJob('current', 'generation', { jobId: generation })
  session.rememberKnownJob('current', 'training', { jobId: training, datasetId: dataset })
  session.rememberKnownJob('current', 'generation', { jobId: nextJob, datasetId: dataset, result: 'private' } as { jobId: string })
  const saved = JSON.parse(sessionStorage.getItem('coldsafe-session')!).known_jobs
  expect(saved).toEqual({ generation: { jobId: nextJob }, training: { jobId: training, datasetId: dataset } })
  expect(session.knownJobs.value).toEqual(saved)
})
it('recarrega referências da aba sem consultar ou reenviar jobs', async () => {
  const session = await setup()
  session.rememberKnownJob('current', 'training', { jobId: training, datasetId: dataset })
  vi.resetModules()
  const restored = await import('./session'); await restored.refreshSessionIdentity()
  expect(restored.knownJobs.value.training).toEqual({ jobId: training, datasetId: dataset })
  expect(vi.mocked(fetch).mock.calls.every(([url]) => String(url).endsWith('/auth/me'))).toBe(true)
})
it('sem storage disponível preserva apenas estado em memória da aba', async () => {
  const session = await setup()
  const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  session.rememberKnownJob('current', 'generation', { jobId: generation })
  expect(session.knownJobs.value.generation).toEqual({ jobId: generation })
  spy.mockRestore()
})
it.each(['logout', 'conta', 'papel'] as const)('%s limpa referências privadas e resposta antiga não as restaura', async (reason) => {
  const session = await setup()
  session.rememberKnownJob('current', 'generation', { jobId: generation })
  if (reason === 'logout') session.clearSession()
  else if (reason === 'conta') session.setSession('other', '2099-01-01T00:00:00Z')
  else session.sessionRole.value = 'viewer'
  session.rememberKnownJob('current', 'training', { jobId: training, datasetId: dataset })
  expect(session.knownJobs.value).toEqual({})
})
it('restauração expirada remove a sessão e suas referências', async () => {
  sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'expired', expires_at: '2000-01-01T00:00:00Z', known_jobs: { generation: { jobId: generation } } }))
  const session = await import('./session')
  expect(session.sessionToken.value).toBeNull(); expect(session.knownJobs.value).toEqual({})
  expect(sessionStorage.getItem('coldsafe-session')).toBeNull()
})
it('remove referência malformada, conserva a outra e explica sem reproduzir o valor externo', async () => {
  sessionStorage.setItem('coldsafe-session', JSON.stringify({ token: 'current', expires_at: '2099-01-01T00:00:00Z',
    known_jobs: { generation: { jobId: 'https://third-party.invalid/private' }, training: { jobId: training, datasetId: dataset, token: 'must-disappear' } } }))
  const session = await import('./session'); await session.refreshSessionIdentity()
  expect(session.knownJobs.value).toEqual({ training: { jobId: training, datasetId: dataset } })
  expect(session.knownJobsNotice.value).not.toBe('')
  expect(session.knownJobsNotice.value).not.toContain('third-party')
  const stored = sessionStorage.getItem('coldsafe-session')!
  expect(stored).not.toContain('third-party'); expect(stored).not.toContain('must-disappear')
})
it('falha temporária não remove referência; remoção atrasada só atinge o job correspondente', async () => {
  const session = await setup()
  session.rememberKnownJob('current', 'generation', { jobId: generation })
  session.rememberKnownJob('current', 'generation', { jobId: nextJob })
  session.forgetKnownJob('current', 'generation', generation)
  expect(session.knownJobs.value.generation?.jobId).toBe(nextJob)
  session.forgetKnownJob('old-token', 'generation', nextJob)
  expect(session.knownJobs.value.generation?.jobId).toBe(nextJob)
  session.forgetKnownJob('current', 'generation', nextJob)
  expect(session.knownJobs.value).toEqual({}); expect(session.knownJobsNotice.value).not.toBe('')
})
it('rejeita IDs e treinamento sem dataset válidos sem guardar URLs ou valores extras', async () => {
  const session = await setup()
  session.rememberKnownJob('current', 'generation', { jobId: 'invalid' })
  session.rememberKnownJob('current', 'training', { jobId: training })
  expect(session.knownJobs.value).toEqual({})
})
it('identidade temporariamente indisponível oculta acesso sem apagar referências como se fossem revogadas', async () => {
  const session = await setup()
  session.rememberKnownJob('current', 'generation', { jobId: generation })
  vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
  await expect(session.refreshSessionIdentity()).rejects.toThrow()
  expect(session.isIdentityVerified.value).toBe(false)
  expect(session.knownJobs.value.generation?.jobId).toBe(generation)
  await session.refreshSessionIdentity()
  expect(session.isIdentityVerified.value).toBe(true)
  expect(session.knownJobs.value.generation?.jobId).toBe(generation)
})
