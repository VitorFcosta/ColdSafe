// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { watch } from 'vue'
import { clearSession, login, logout, register, sessionToken, sessionRole, canWrite, refreshSessionIdentity, setSession, sessionIdentityState, sessionIdentityError, sessionUser, isIdentityVerified } from './session'
import {
  createDevice, createEnvironment, deactivateDevice, getRules, listDevices, listEnvironments,
  updateDevice, updateEnvironment, updateRules,
  CatalogAccessError,
} from './catalog'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

const ok = (data: unknown) => ({ ok: true, status: 200, json: async () => ({ success: true, data }) })
const identity = { user_id: 'user-1', email: 'a@b.com', role: 'operator' }

describe('conta e catálogo', () => {
  beforeEach(() => { fetchMock.mockReset(); clearSession() })
  afterEach(() => { clearSession(); vi.useRealTimers() })

  it.each([401, 403, 404])('preserva status %s para revogação, inclusive com corpo inválido', async (status) => {
    setSession('token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => ({ success: false, error: { message: 'Indisponível.' } }) })
    await expect(listDevices('token', 'env')).rejects.toMatchObject({ status, message: 'Indisponível.' })
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => { throw new Error('invalid JSON') } })
    await expect(listDevices('token', 'env')).rejects.toBeInstanceOf(CatalogAccessError)
    if (status === 401) expect(sessionToken.value).toBeNull()
  })

  it('entra com token e revoga a sessão ao sair', async () => {
    fetchMock.mockResolvedValueOnce(ok({ token: 'token-1', expires_at: '2099-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(ok(identity))
      .mockResolvedValueOnce(ok({ revoked: true }))
    await login('a@b.com', 'password123')
    expect(sessionToken.value).toBe('token-1')
    await logout()
    expect(sessionToken.value).toBeNull()
    expect(fetchMock.mock.calls[1]?.[0]).toContain('/auth/me')
    expect(fetchMock.mock.calls[2]?.[1]?.headers.authorization).toBe('Bearer token-1')
  })

  it.each([200, 401])('logout atrasado %s não apaga a nova conta', async (status) => {
    let finish!: (value: { ok: boolean; status: number }) => void
    setSession('old-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const pending = logout()
    setSession('new-token', '2099-01-01T00:00:00Z')
    finish({ ok: status === 200, status })
    await pending
    expect(sessionToken.value).toBe('new-token')
  })

  it('mostra erro de credenciais sem criar sessão', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401, json: async () => ({ success: false, error: { message: 'Email ou senha inválidos.' } }) })
    await expect(login('a@b.com', 'wrong')).rejects.toThrow('Email ou senha inválidos.')
    expect(sessionToken.value).toBeNull()
  })

  it('consulta catálogos autorizados e salva limites', async () => {
    fetchMock.mockResolvedValueOnce(ok([{ id: 'env-1', name: 'Câmara 1' }]))
      .mockResolvedValueOnce(ok([{ id: 'dev-1', environment_id: 'env-1', name: 'ESP32', mqtt_device_id: 'esp32-1', is_active: true }]))
      .mockResolvedValueOnce(ok({ min_c: 2, max_c: 8, attention_margin_c: 0.5 }))
    expect(await listEnvironments('token-1')).toHaveLength(1)
    expect(await listDevices('token-1', 'env-1')).toHaveLength(1)
    await updateRules('token-1', 'env-1', { min_c: 2, max_c: 8, attention_margin_c: 0.5 })
    expect(fetchMock.mock.calls[2]?.[0]).toContain('/environments/env-1/rules')
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe('PUT')
    expect(fetchMock.mock.calls[2]?.[1]?.headers.authorization).toBe('Bearer token-1')
  })

  it('limpa sessão rejeitada pela API', async () => {
    fetchMock.mockResolvedValueOnce(ok({ token: 'token-1', expires_at: '2099-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(ok(identity))
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({ success: false, error: { message: 'Sessão inválida.' } }) })
    await login('a@b.com', 'password123')
    await expect(listEnvironments('token-1')).rejects.toThrow('Sessão inválida.')
    expect(sessionToken.value).toBeNull()
  })

  it('envia operações do catálogo à rota e ao método corretos, codificando IDs', async () => {
    fetchMock.mockResolvedValue(ok({ id: 'saved' }))
    await createEnvironment('token-1', 'Câmara 2')
    await updateEnvironment('token-1', 'env/1', 'Câmara fria')
    await createDevice('token-1', 'env/1', 'Sensor', 'esp32-1')
    await updateDevice('token-1', 'dev/1', 'Sensor principal')
    await deactivateDevice('token-1', 'dev/1')
    await getRules('token-1', 'env/1')

    expect(fetchMock.mock.calls.map(([url, options]) => [new URL(url).pathname, options.method])).toEqual([
      ['/api/v1/environments', 'POST'],
      ['/api/v1/environments/env%2F1', 'PATCH'],
      ['/api/v1/environments/env%2F1/devices', 'POST'],
      ['/api/v1/devices/dev%2F1', 'PATCH'],
      ['/api/v1/devices/dev%2F1', 'DELETE'],
      ['/api/v1/environments/env%2F1/rules', 'GET'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[2]?.[1]?.body)).toEqual({ name: 'Sensor', mqtt_device_id: 'esp32-1' })
  })

  it('rejeita falha de rede, resposta inválida e catálogos malformados', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => { throw new Error('invalid JSON') } })
      .mockResolvedValueOnce(ok({ id: 'not-an-array' }))
      .mockResolvedValueOnce(ok({ id: 'not-an-array' }))
    await expect(listEnvironments('token-1')).rejects.toThrow('Não foi possível conectar')
    await expect(listEnvironments('token-1')).rejects.toThrow('resposta inválida')
    await expect(listEnvironments('token-1')).rejects.toThrow('ambientes inválidos')
    await expect(listDevices('token-1', 'env-1')).rejects.toThrow('dispositivos inválidos')
  })

  it('recusa sessão malformada e mantém a sessão se o logout não foi confirmado', async () => {
    fetchMock.mockResolvedValueOnce(ok({ token: '', expires_at: 'invalid' }))
      .mockResolvedValueOnce(ok({ token: 'token-1', expires_at: '2099-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(ok(identity))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ ok: false, status: 500 })
      .mockResolvedValueOnce({ ok: false, status: 401 })
    await expect(login('a@b.com', 'password123')).rejects.toThrow('sessão inválida')
    await login('a@b.com', 'password123')
    await expect(logout()).rejects.toThrow('Não foi possível encerrar')
    expect(sessionToken.value).toBe('token-1')
    await expect(logout()).rejects.toThrow('Não foi possível encerrar')
    expect(sessionToken.value).toBe('token-1')
    await logout()
    expect(sessionToken.value).toBeNull()
  })

  it('cadastra conta e repassa o erro da API', async () => {
    fetchMock.mockResolvedValueOnce(ok({ id: 'user-1' }))
      .mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ success: false, error: { message: 'Conta já existe.' } }) })
    await register('a@b.com', 'password123')
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/auth/register')
    await expect(register('a@b.com', 'password123')).rejects.toThrow('Conta já existe.')
  })

  it.each(['viewer', 'operator', 'admin'] as const)('usa o papel %s informado pela API, sem extrair claims locais', async (role) => {
    fetchMock.mockResolvedValueOnce(ok({ token: 'fake-token', expires_at: '2099-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(ok({ ...identity, role }))
    await login('a@b.com', 'password123')
    expect(sessionRole.value).toBe(role)
    expect(canWrite.value).toBe(role !== 'viewer')
    clearSession()
    expect(sessionRole.value).toBeNull()
    expect(canWrite.value).toBe(false)
  })

  it('não permite escrita até a identidade ser resolvida, nem aceita resposta da sessão anterior', async () => {
    let release: ((value: unknown) => void) | undefined
    setSession('old-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))
    const loading = refreshSessionIdentity()
    expect(canWrite.value).toBe(false)
    setSession('new-token', '2099-01-01T00:00:00Z')
    release?.(ok(identity))
    await loading
    expect(sessionRole.value).toBeNull()
  })

  it('limpa identidade revogada e recusa papel desconhecido', async () => {
    setSession('token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce(ok({ ...identity, role: 'super-admin' }))
      .mockResolvedValueOnce({ ok: false, status: 401 })
    await expect(refreshSessionIdentity()).rejects.toThrow('identidade inválida')
    expect(canWrite.value).toBe(false)
    await expect(refreshSessionIdentity()).rejects.toThrow('Sessão inválida')
    expect(sessionToken.value).toBeNull()
  })

  it('limita só o cadastro a 72 bytes UTF-8, preservando login legado longo', async () => {
    await expect(register('a@b.com', 'é'.repeat(37))).rejects.toThrow('72 bytes')
    expect(fetchMock).not.toHaveBeenCalled()
    fetchMock.mockResolvedValueOnce(ok({ token: 'token', expires_at: '2099-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(ok(identity))
    await login('a@b.com', 'é'.repeat(37))
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body).password).toHaveLength(37)
  })

  it('deduplica verificação pendente e só confirma identidade validada para a sessão atual', async () => {
    let release!: (value: unknown) => void
    setSession('identity-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))
    const first = refreshSessionIdentity()
    const second = refreshSessionIdentity()
    expect(first).toBe(second)
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(sessionIdentityState.value).toBe('pending')
    expect(sessionUser.value).toBeNull()
    expect(sessionRole.value).toBeNull()
    expect(isIdentityVerified.value).toBe(false)
    release(ok(identity))
    await first
    expect(sessionIdentityState.value).toBe('verified')
    expect(sessionIdentityError.value).toBe('')
    expect(sessionUser.value).toEqual({ id: 'user-1', email: 'a@b.com' })
    expect(isIdentityVerified.value).toBe(true)
  })

  it('falha de identidade conserva token sem assumir viewer e permite nova consulta', async () => {
    setSession('identity-token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce(ok(identity)).mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(ok({ ...identity, role: 'viewer' }))
    await refreshSessionIdentity()
    await expect(refreshSessionIdentity()).rejects.toThrow('consultar as permissões')
    expect(sessionToken.value).toBe('identity-token')
    expect(sessionIdentityState.value).toBe('error')
    expect(sessionIdentityError.value).toContain('consultar as permissões')
    expect(sessionRole.value).toBeNull()
    expect(sessionUser.value).toBeNull()
    expect(isIdentityVerified.value).toBe(false)
    await refreshSessionIdentity()
    expect(sessionIdentityState.value).toBe('verified')
    expect(sessionIdentityError.value).toBe('')
    expect(sessionRole.value).toBe('viewer')
    expect(canWrite.value).toBe(false)
  })

  it.each(['invalid-json', 'empty-user'])('identidade malformada %s gera erro recuperável e mensagem segura', async (kind) => {
    setSession('identity-token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce(kind === 'invalid-json'
      ? { ok: true, status: 200, json: async () => { throw new Error('internal parser detail') } }
      : ok({ ...identity, user_id: '' }))
    await expect(refreshSessionIdentity()).rejects.toThrow('identidade inválida')
    expect(sessionIdentityState.value).toBe('error')
    expect(sessionIdentityError.value).toContain('identidade inválida')
    expect(sessionIdentityError.value).not.toContain('parser')
    expect(isIdentityVerified.value).toBe(false)
  })

  it.each(['401', 'network'])('resposta atrasada %s da identidade anterior não afeta conta verificada', async (kind) => {
    let release!: (value: unknown) => void
    let reject!: (reason: unknown) => void
    setSession('old-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce(() => new Promise((resolve, fail) => { release = resolve; reject = fail }))
    const old = refreshSessionIdentity()
    setSession('new-token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce(ok({ ...identity, user_id: 'user-2', role: 'admin' }))
    await refreshSessionIdentity()
    if (kind === '401') release({ ok: false, status: 401 })
    else reject(new Error('offline'))
    await old
    expect(sessionToken.value).toBe('new-token')
    expect(sessionRole.value).toBe('admin')
    expect(sessionUser.value?.id).toBe('user-2')
    expect(sessionIdentityState.value).toBe('verified')
    expect(isIdentityVerified.value).toBe(true)
  })

  it.each([200, 401])('reestabelecer o mesmo token invalida a revisão da identidade atrasada %s', async (status) => {
    let release!: (value: unknown) => void
    setSession('same-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))
    const old = refreshSessionIdentity()
    setSession('same-token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce(ok({ ...identity, user_id: 'user-2', role: 'viewer' }))
    await refreshSessionIdentity()
    release(status === 200 ? ok(identity) : { ok: false, status })
    await old
    expect(sessionToken.value).toBe('same-token')
    expect(sessionUser.value?.id).toBe('user-2')
    expect(sessionRole.value).toBe('viewer')
    expect(isIdentityVerified.value).toBe(true)
  })

  it('corpo JSON atrasado não troca a identidade depois de mudar a sessão', async () => {
    let release!: (value: unknown) => void
    setSession('old-token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: () => new Promise((resolve) => { release = resolve }) })
    const old = refreshSessionIdentity()
    await Promise.resolve()
    setSession('new-token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce(ok({ ...identity, user_id: 'user-2', role: 'viewer' }))
    await refreshSessionIdentity()
    release({ success: true, data: identity })
    await old
    expect(sessionUser.value?.id).toBe('user-2')
    expect(sessionRole.value).toBe('viewer')
    expect(isIdentityVerified.value).toBe(true)
  })

  it.each([200, 401])('logout atrasado %s não encerra sessão reestabelecida com o mesmo token', async (status) => {
    let release!: (value: unknown) => void
    setSession('same-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))
    const old = logout()
    setSession('same-token', '2099-01-01T00:00:00Z')
    release({ ok: status === 200, status })
    await old
    expect(sessionToken.value).toBe('same-token')
  })

  it('invalida identidade antes de observadores verem o token de outra conta', async () => {
    setSession('old-token', '2099-01-01T00:00:00Z')
    fetchMock.mockResolvedValueOnce(ok(identity))
    await refreshSessionIdentity()
    const seen: unknown[] = []
    const stop = watch(sessionToken, () => seen.push({ role: sessionRole.value, user: sessionUser.value, verified: isIdentityVerified.value }), { flush: 'sync' })
    setSession('new-token', '2099-01-01T00:00:00Z')
    stop()
    expect(seen).toEqual([{ role: null, user: null, verified: false }])
  })


  it.each(['fetch', 'body'])('encerra identidade com %s pendente em 8 s e ignora sua resposta depois do retry', async (stage) => {
    vi.useFakeTimers()
    let release!: (value: unknown) => void
    let signal!: AbortSignal
    setSession('identity-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce((_url, options: RequestInit) => {
      signal = options.signal as AbortSignal
      const pending = new Promise((resolve) => { release = resolve })
      return stage === 'fetch' ? pending : Promise.resolve({ ok: true, status: 200, json: () => pending })
    })
    const pending = refreshSessionIdentity()
    expect(refreshSessionIdentity()).toBe(pending)
    const failed = expect(pending).rejects.toThrow('demorou demais')
    await vi.advanceTimersByTimeAsync(7999)
    expect(sessionIdentityState.value).toBe('pending')
    expect(signal.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    await failed
    expect(signal.aborted).toBe(true)
    expect(sessionIdentityState.value).toBe('error')
    expect(sessionIdentityError.value).toContain('demorou demais')
    expect(sessionToken.value).toBe('identity-token')
    expect(isIdentityVerified.value).toBe(false)
    fetchMock.mockResolvedValueOnce(ok({ ...identity, user_id: 'retry-user', role: 'viewer' }))
    await refreshSessionIdentity()
    release(stage === 'fetch' ? ok(identity) : { success: true, data: identity })
    await Promise.resolve()
    await Promise.resolve()
    expect(sessionIdentityState.value).toBe('verified')
    expect(sessionUser.value?.id).toBe('retry-user')
    expect(sessionRole.value).toBe('viewer')
  })

  it.each(['same-token', 'different-token'])('troca de sessão %s cancela a consulta anterior sem cancelar nova identidade', async (nextToken) => {
    vi.useFakeTimers()
    let release!: (value: unknown) => void
    let oldSignal!: AbortSignal
    setSession('same-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce((_url, options: RequestInit) => {
      oldSignal = options.signal as AbortSignal
      return new Promise((resolve) => { release = resolve })
    })
    const old = refreshSessionIdentity()
    setSession(nextToken, '2099-01-01T00:00:00Z')
    expect(oldSignal.aborted).toBe(true)
    fetchMock.mockResolvedValueOnce(ok({ ...identity, user_id: 'new-user', role: 'admin' }))
    const current = refreshSessionIdentity()
    const newSignal = (fetchMock.mock.calls[1]![1] as RequestInit).signal!
    await old
    await current
    await vi.advanceTimersByTimeAsync(8000)
    expect(newSignal.aborted).toBe(false)
    expect(sessionIdentityState.value).toBe('verified')
    expect(sessionUser.value?.id).toBe('new-user')
    release({ ok: false, status: 401 })
    await Promise.resolve()
    expect(sessionToken.value).toBe(nextToken)
    expect(isIdentityVerified.value).toBe(true)
  })


  it('o prazo de 8 s inclui tempo de conexão e não reinicia ao começar o JSON', async () => {
    vi.useFakeTimers()
    let release!: (value: unknown) => void
    setSession('identity-token', '2099-01-01T00:00:00Z')
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))
    const pending = refreshSessionIdentity()
    const failed = expect(pending).rejects.toThrow('demorou demais')
    await vi.advanceTimersByTimeAsync(7000)
    release({ ok: true, status: 200, json: () => new Promise(() => {}) })
    await vi.advanceTimersByTimeAsync(999)
    expect(sessionIdentityState.value).toBe('pending')
    await vi.advanceTimersByTimeAsync(1)
    await failed
    expect(sessionIdentityState.value).toBe('error')
    expect(sessionToken.value).toBe('identity-token')
  })

})

it.each([
  { status: 503, body: '<html>offline</html>', message: 'O serviço de acesso está indisponível. Tente novamente em instantes.' },
  { status: 500, body: JSON.stringify({ error: { message: 'database internal detail' } }), message: 'O serviço de acesso está indisponível. Tente novamente em instantes.' },
  { status: 429, body: '', message: 'Muitas tentativas de acesso. Aguarde antes de tentar novamente.' },
  { status: 401, body: '', message: 'Email ou senha inválidos.' },
  { status: 200, body: '<html>proxy</html>', message: 'O serviço de acesso retornou uma resposta inválida. Tente novamente.' },
])('distingue falha de acesso $status de credenciais inválidas, inclusive sem JSON', async ({ status, body, message }) => {
  clearSession()
  fetchMock.mockReset().mockResolvedValueOnce(new Response(body, { status }))
  await expect(login('user@example.invalid', 'password123')).rejects.toThrow(message)
  expect(sessionToken.value).toBeNull()
})
