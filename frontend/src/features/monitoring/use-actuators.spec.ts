// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionRole, sessionToken } from '../account/session'
import { fetchActuators, fetchCommand, requestLed, type ActuatorCommand } from './actuators'
import { actuatorLabel, useActuators } from './use-actuators'
import type { MonitoringEvent } from './use-monitoring-summary'

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
})
