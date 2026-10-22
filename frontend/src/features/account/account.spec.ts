// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearSession, login, logout, register, sessionToken, sessionRole, canWrite, refreshSessionIdentity, setSession } from './session'
import {
  createDevice, createEnvironment, deactivateDevice, getRules, listDevices, listEnvironments,
  updateDevice, updateEnvironment, updateRules,
} from './catalog'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

const ok = (data: unknown) => ({ ok: true, status: 200, json: async () => ({ success: true, data }) })
const identity = { user_id: 'user-1', email: 'a@b.com', role: 'operator' }

describe('conta e catálogo', () => {
  beforeEach(() => { fetchMock.mockReset(); clearSession() })

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
})
