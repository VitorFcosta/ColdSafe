// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from 'vitest'
import { listEnvironments } from './catalog'
import { clearSession, sessionToken } from './session'

afterEach(() => { clearSession(); vi.unstubAllGlobals() })

it('uma resposta 401 atrasada do catálogo não encerra a nova sessão', async () => {
  let resolve!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise((done) => { resolve = done })))
  sessionToken.value = 'old-token'
  const request = listEnvironments('old-token')
  sessionToken.value = 'new-token'
  resolve(new Response(JSON.stringify({ success: false }), { status: 401 }))
  await expect(request).rejects.toThrow()
  expect(sessionToken.value).toBe('new-token')
})

it('401 da sessão atual continua encerrando o acesso', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: false }), { status: 401 })))
  sessionToken.value = 'current-token'
  await expect(listEnvironments('current-token')).rejects.toThrow()
  expect(sessionToken.value).toBeNull()
})
