import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchActuators, isCommand, requestLed } from './actuators'

const command = {
  schema_version: 2, command_id: 'command-1', device_id: 'esp32-1', actuator: 'led',
  desired_state: true, confirmed_state: null, status: 'pending',
}

afterEach(() => vi.unstubAllGlobals())

describe('actuators API', () => {
  it('não interpreta comando sem confirmação como LED ligado', () => {
    expect(isCommand(command)).toBe(true)
    expect(isCommand({ ...command, status: 'confirmed' })).toBe(false)
    expect(isCommand({ ...command, status: 'confirmed', confirmed_state: false })).toBe(false)
    expect(isCommand({ ...command, status: 'confirmed', confirmed_state: true })).toBe(true)
  })

  it('envia token e estado desejado e valida o retorno', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data: command }), { status: 200 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(requestLed('token', 'uuid-1', true)).resolves.toEqual(command)
    expect(fetcher).toHaveBeenCalledWith('http://localhost:8000/api/v1/devices/uuid-1/led/commands', {
      method: 'POST', body: '{"desired_state":true}',
      headers: { accept: 'application/json', authorization: 'Bearer token', 'content-type': 'application/json' },
    })
    fetcher.mockResolvedValue(new Response(JSON.stringify({ success: true, data: { led: { ...command, status: 'confirmed' }, buzzer: null } }), { status: 200 }))
    await expect(fetchActuators('token', 'uuid-1')).rejects.toThrow('Estado inválido')
  })
})
