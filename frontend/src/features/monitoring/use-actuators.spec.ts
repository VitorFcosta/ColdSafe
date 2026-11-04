// @vitest-environment happy-dom
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionRole, sessionToken } from '../account/session'
import { fetchActuators, fetchCommand, requestLed, type ActuatorCommand } from './actuators'
import { actuatorLabel, useActuators } from './use-actuators'
import type { MonitoringEvent } from './use-monitoring-summary'

enableAutoUnmount(afterEach)

vi.mock('./monitoring-version', () => ({ aiotEnabled: true }))
vi.mock('./actuators', async (original) => ({ ...await original<typeof import('./actuators')>(), fetchActuators: vi.fn(), fetchCommand: vi.fn(), requestLed: vi.fn() }))
const pending: ActuatorCommand = { schema_version: 2, command_id: 'command-a', device_id: 'mqtt-a', actuator: 'led', desired_state: true, confirmed_state: null, status: 'pending' }
beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(fetchActuators).mockReset().mockResolvedValue({ led: null, buzzer: null })
  vi.mocked(fetchCommand).mockReset()
  vi.mocked(requestLed).mockReset().mockResolvedValue(pending)
  sessionToken.value = 'token-a'; sessionRole.value = 'operator'
})
afterEach(() => vi.useRealTimers())
function setup() {
  const device = ref<string | null>('device-a')
  const revision = ref(0)
  const connection = ref('connected')
  const legacyEvent = ref<MonitoringEvent | null>(null)
  let control!: ReturnType<typeof useActuators>
  const wrapper = mount(defineComponent({ setup() { control = useActuators(sessionToken, device, revision, connection, legacyEvent); return () => null } }))
  return { wrapper, device, revision, control, legacyEvent }
}
describe('shared actuator control', () => {
  it.each(['token', 'device'])('does not replay a queued legacy ACK after a synchronous %s reset', async (scope) => {
    const { wrapper, device, control, legacyEvent } = setup(); await flushPromises()
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise(() => {}))
    legacyEvent.value = { schema_version: 2, type: 'command_status', device_id: 'mqtt-a',
      environment_id: 'environment-a', occurred_at: '2026-10-20T18:00:00Z',
      data: { ...pending, status: 'confirmed', confirmed_state: true } }
    if (scope === 'token') sessionToken.value = 'token-b'
    else device.value = 'device-b'
    await flushPromises()
    expect(control.led.value).toBeNull()
    expect(control.actuatorPhase.value).toBe('loading')
    wrapper.unmount()
  })
  it('preserves pending/ACK and blocks viewers and duplicate submissions', async () => {
    const { wrapper, control } = setup(); await flushPromises()
    sessionRole.value = 'viewer'
    await control.toggleLed()
    expect(requestLed).not.toHaveBeenCalled()
    sessionRole.value = 'operator'
    await control.toggleLed(); await control.toggleLed()
    expect(requestLed).toHaveBeenCalledOnce()
    expect(actuatorLabel(control.led.value)).toBe('Aguardando confirmação')
    vi.mocked(fetchCommand).mockResolvedValue({ ...pending, status: 'confirmed', confirmed_state: true })
    await vi.advanceTimersByTimeAsync(1000)
    expect(actuatorLabel(control.led.value)).toBe('Ligado')
    wrapper.unmount()
  })
  it('clears token scope and ignores a delayed confirmation error from the previous session', async () => {
    let reject!: (error: Error) => void
    vi.mocked(fetchActuators).mockResolvedValueOnce({ led: pending, buzzer: null })
    vi.mocked(fetchCommand).mockImplementation(() => new Promise((_resolve, fail) => { reject = fail }))
    const { wrapper, control } = setup(); await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    sessionToken.value = 'token-b'; await flushPromises()
    expect(control.led.value).toBeNull()
    reject(new Error('old-session')); await flushPromises()
    expect(control.commandError.value).toBe('')
    expect(fetchActuators).toHaveBeenLastCalledWith('token-b', 'device-a')
    wrapper.unmount()
  })
  it('does not mutate state after unmount or poll beyond 35 checks', async () => {
    vi.mocked(fetchActuators).mockResolvedValue({ led: pending, buzzer: null })
    vi.mocked(fetchCommand).mockResolvedValue(pending)
    const { wrapper, control } = setup(); await flushPromises()
    await vi.advanceTimersByTimeAsync(40_000)
    expect(fetchCommand).toHaveBeenCalledTimes(35)
    wrapper.unmount()
    await control.loadActuators('device-a')
    expect(fetchActuators).toHaveBeenCalledOnce()
  })
  it('mantém um snapshot vazio pronto durante uma atualização lenta e agrupa eventos concorrentes', async () => {
    const { wrapper, control, revision } = setup(); await flushPromises()
    let resolve!: (result: { led: null; buzzer: null }) => void
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    revision.value++; await flushPromises()
    expect(control.actuatorPhase.value).toBe('ready')
    for (let index = 0; index < 4; index++) {
      revision.value++; await flushPromises()
    }
    expect(fetchActuators).toHaveBeenCalledTimes(2)
    expect(control.led.value).toBeNull()
    resolve({ led: null, buzzer: null }); await flushPromises()
    expect(control.actuatorPhase.value).toBe('ready')
    expect(requestLed).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('mantém o estado e o erro durante novas tentativas, e permite recuperação', async () => {
    const confirmed = { ...pending, status: 'confirmed' as const, confirmed_state: true }
    vi.mocked(fetchActuators).mockResolvedValueOnce({ led: confirmed, buzzer: null })
    const { wrapper, control, revision } = setup(); await flushPromises()
    vi.mocked(fetchActuators).mockRejectedValueOnce(new Error('offline'))
    revision.value++; await flushPromises()
    expect(control.actuatorPhase.value).toBe('error')
    expect(control.led.value).toEqual(confirmed)
    let resolve!: (result: { led: typeof confirmed; buzzer: null }) => void
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    revision.value++; await flushPromises()
    expect(control.actuatorPhase.value).toBe('error')
    expect(control.led.value).toEqual(confirmed)
    resolve({ led: confirmed, buzzer: null }); await flushPromises()
    expect(control.actuatorPhase.value).toBe('ready')
    expect(requestLed).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('não sobrescreve um POST com a consulta iniciada antes dele', async () => {
    const { wrapper, control } = setup(); await flushPromises()
    let resolve!: (result: { led: null; buzzer: null }) => void
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const loading = control.loadActuators('device-a')
    await control.toggleLed()
    resolve({ led: null, buzzer: null }); await loading
    expect(control.led.value).toEqual(pending)
    expect(control.actuatorPhase.value).toBe('ready')
    expect(requestLed).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
  it.each(['poll', 'legacy'])('não sobrescreve um ACK recebido via %s com snapshot anterior', async (source) => {
    vi.mocked(fetchActuators).mockResolvedValueOnce({ led: pending, buzzer: null })
    const { wrapper, control, legacyEvent } = setup(); await flushPromises()
    let resolve!: (result: { led: typeof pending; buzzer: null }) => void
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const loading = control.loadActuators('device-a')
    const confirmed = { ...pending, status: 'confirmed' as const, confirmed_state: true }
    if (source === 'poll') {
      vi.mocked(fetchCommand).mockResolvedValue(confirmed)
      await vi.advanceTimersByTimeAsync(1_000)
    } else {
      legacyEvent.value = { schema_version: 2, type: 'command_status', device_id: 'mqtt-a',
        environment_id: 'environment-a', occurred_at: '2026-10-20T18:00:00Z', data: confirmed }
    }
    resolve({ led: pending, buzzer: null }); await loading
    expect(control.led.value).toEqual(confirmed)
    expect(control.actuatorPhase.value).toBe('ready')
    expect(requestLed).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it.each(['token', 'device', 'unmount'])('descarta respostas tardias e libera a seleção nova em %s', async (scope) => {
    const { wrapper, control, device } = setup(); await flushPromises()
    let resolve!: (result: { led: typeof pending; buzzer: null }) => void
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const loading = control.loadActuators('device-a')
    if (scope === 'token') sessionToken.value = 'token-b'
    else if (scope === 'device') device.value = 'device-b'
    else wrapper.unmount()
    await flushPromises()
    resolve({ led: pending, buzzer: null }); await loading
    expect(control.led.value).toBeNull()
    expect(control.actuatorPhase.value).toBe('ready')
    expect(fetchActuators).toHaveBeenCalledTimes(scope === 'unmount' ? 2 : 3)
    if (scope !== 'unmount') wrapper.unmount()
  })

  it('conclui o primeiro carregamento mesmo recebendo revisões antes da resposta', async () => {
    let resolve!: (result: { led: null; buzzer: null }) => void
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const { wrapper, control, revision } = setup()
    expect(control.actuatorPhase.value).toBe('loading')
    for (let index = 0; index < 4; index++) { revision.value++; await flushPromises() }
    expect(fetchActuators).toHaveBeenCalledOnce()
    resolve({ led: null, buzzer: null }); await flushPromises()
    expect(control.actuatorPhase.value).toBe('ready')
    wrapper.unmount()
  })
  it('permite repetir manualmente uma consulta inicial que falhou', async () => {
    vi.mocked(fetchActuators).mockRejectedValueOnce(new Error('offline'))
    const { wrapper, control } = setup(); await flushPromises()
    expect(control.actuatorPhase.value).toBe('error')
    await control.loadActuators('device-a')
    expect(control.actuatorPhase.value).toBe('ready')
    expect(fetchActuators).toHaveBeenCalledTimes(2)
    expect(requestLed).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('não reinicia a espera do ACK ao receber o mesmo pending em atualizações rápidas', async () => {
    vi.mocked(fetchActuators).mockResolvedValue({ led: pending, buzzer: null })
    vi.mocked(fetchCommand).mockResolvedValue({ ...pending, status: 'confirmed', confirmed_state: true })
    const { wrapper, control, revision } = setup(); await flushPromises()
    await vi.advanceTimersByTimeAsync(500)
    revision.value++; await flushPromises()
    await vi.advanceTimersByTimeAsync(450)
    revision.value++; await flushPromises()
    await vi.advanceTimersByTimeAsync(50)
    expect(fetchCommand).toHaveBeenCalledOnce()
    expect(actuatorLabel(control.led.value)).toBe('Ligado')
    wrapper.unmount()
  })

  it('mostra o ACK legado mesmo quando ele chega antes do primeiro snapshot', async () => {
    let resolve!: (result: { led: null; buzzer: null }) => void
    vi.mocked(fetchActuators).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const { wrapper, control, legacyEvent } = setup()
    const confirmed = { ...pending, status: 'confirmed' as const, confirmed_state: true }
    legacyEvent.value = { schema_version: 2, type: 'command_status', device_id: 'mqtt-a',
      environment_id: 'environment-a', occurred_at: '2026-10-20T18:00:00Z', data: confirmed }
    resolve({ led: null, buzzer: null }); await flushPromises()
    expect(control.led.value).toEqual(confirmed)
    expect(control.actuatorPhase.value).toBe('ready')
    wrapper.unmount()
  })

})
