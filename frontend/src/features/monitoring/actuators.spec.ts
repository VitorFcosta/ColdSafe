import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchActuators, isCommand, requestLed } from './actuators'
import { readFileSync } from 'node:fs'

const command = {
  schema_version: 2, command_id: 'command-1', device_id: 'esp32-1', actuator: 'led',
  desired_state: true, confirmed_state: null, status: 'pending',
}

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules() })

describe('actuators API', () => {
  it('adapta envelopes v3 pendentes/confirmados sem assumir ACK', async () => {
    vi.stubEnv('VITE_AIOT_ENABLED', 'true')
    vi.resetModules()
    const api = await import('./actuators')
    const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8')) as { name: string; payload: Record<string, unknown> }[]
    const envelope = structuredClone(examples.find((item) => item.payload.type === 'command_status' && (item.payload.data as { status: string }).status === 'pending')!.payload)
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ success: true, data: envelope })))
    vi.stubGlobal('fetch', fetcher)
    const result = await api.requestLed('token', 'esp32.lab-01', true)
    expect(result).toMatchObject({ schema_version: 3, device_id: 'esp32.lab-01', status: 'pending', confirmed_state: null })
    expect(api.isCommand(result)).toBe(true)
    expect(api.isCommand(envelope)).toBe(false)
    expect(fetcher.mock.calls[0]?.[0]).toBe('http://localhost:8000/api/v3/devices/esp32.lab-01/led/commands')
    await expect(api.fetchCommand('token', result.command_id)).resolves.toEqual(result)
    expect(fetcher.mock.calls[1]?.[0]).toBe(`http://localhost:8000/api/v3/commands/${result.command_id}`)
    await expect(api.requestLed('token', 'other', true)).rejects.toThrow('Comando inválido')
  })

  it('recupera comandos v3 pela identidade MQTT e rejeita ator ou comando divergente', async () => {
    vi.stubEnv('VITE_AIOT_ENABLED', 'true')
    vi.resetModules()
    const api = await import('./actuators')
    const examples = JSON.parse(readFileSync(new URL('../../../../contracts/examples/aiot.valid.json', import.meta.url), 'utf8')) as { name: string; payload: Record<string, unknown> }[]
    const envelope = examples.find((item) => item.payload.type === 'command_status' && (item.payload.data as { actuator: string }).actuator === 'led')!.payload
    const commands: { led: unknown; buzzer: unknown } = { led: envelope, buzzer: null }
    const data = { device: { id: 'esp32.lab-01' }, environment: { id: envelope.environment_id }, commands }
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ success: true, data })))
    vi.stubGlobal('fetch', fetcher)
    await expect(api.fetchActuators('token', 'esp32.lab-01')).resolves.toMatchObject({ led: { schema_version: 3 }, buzzer: null })
    expect(fetcher.mock.calls[0]?.[0]).toBe('http://localhost:8000/api/v3/monitoring/summary?device_id=esp32.lab-01')
    data.commands = { led: null, buzzer: envelope }
    await expect(api.fetchActuators('token', 'esp32.lab-01')).rejects.toThrow('Estado inválido')
    fetcher.mockImplementation(async () => new Response(JSON.stringify({ success: true, data: envelope })))
    await expect(api.fetchCommand('token', '00000000-0000-4000-8000-000000000999')).rejects.toThrow('Comando inválido')
  })

  it('aceita o domínio v3 mínimo e valida metadados opcionais quando fornecidos', () => {
    const v3 = { ...command, schema_version: 3, command_id: '00000000-0000-4000-8000-000000000400' }
    expect(isCommand(v3)).toBe(true)
    expect(isCommand({ ...v3, event_id: 'invalid' })).toBe(false)
  })
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
