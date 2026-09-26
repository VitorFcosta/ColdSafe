// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearSession, login, logout, sessionToken } from './session'
import { listDevices, listEnvironments, updateRules } from './catalog'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

const ok = (data: unknown) => ({ ok: true, status: 200, json: async () => ({ success: true, data }) })

describe('conta e catálogo', () => {
  beforeEach(() => { fetchMock.mockReset(); clearSession() })

  it('entra com token e revoga a sessão ao sair', async () => {
    fetchMock.mockResolvedValueOnce(ok({ token: 'token-1', expires_at: '2099-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(ok({ revoked: true }))
    await login('a@b.com', 'password123')
    expect(sessionToken.value).toBe('token-1')
    await logout()
    expect(sessionToken.value).toBeNull()
    expect(fetchMock.mock.calls[1]?.[1]?.headers.authorization).toBe('Bearer token-1')
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
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({ success: false, error: { message: 'Sessão inválida.' } }) })
    await login('a@b.com', 'password123')
    await expect(listEnvironments('token-1')).rejects.toThrow('Sessão inválida.')
    expect(sessionToken.value).toBeNull()
  })
})
