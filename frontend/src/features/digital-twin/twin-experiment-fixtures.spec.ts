// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import Experiment from '../../../experiments/rd02/Experiment.vue'
import { expect, it } from 'vitest'
import { buildTwinItems, buildTwinVisualState } from './twin-state'
import { controlledSummary } from '../../../experiments/rd02/fixtures'

it('cenários controlados conservam nove IDs e não transformam ausência em zero', () => {
  const base = controlledSummary('active')
  const ids = buildTwinItems(base, true, null).map((item) => item.id)
  for (const state of ['stale', 'empty'] as const) {
    const summary = controlledSummary(state)
    const items = buildTwinItems(summary, false, null)
    expect(items.map((item) => item.id)).toEqual(ids)
    expect(items.every((item) => item.value === 'Sem dados atuais')).toBe(true)
    expect(buildTwinVisualState(summary, false)).toBeNull()
  }
  const zero = buildTwinItems(controlledSummary('zero'), true, null)
  expect(zero.find((item) => item.key === 'temperature_c')?.value).toBe('0 °C')
  expect(zero.find((item) => item.key === 'light_percent')?.value).toBe('0 %')
  expect(buildTwinVisualState(controlledSummary('stopped'), true)).toMatchObject({ running: false, vibration: 0, buzzer: false })
  expect(buildTwinVisualState(controlledSummary('changed'), true)).toMatchObject({ temperature: 7.5, led: true, buzzer: true })
  expect(buildTwinVisualState(base, true)).toMatchObject({ temperature: 6.5, running: true, led: false })
})


it('harness limpa seleção ao comparar cenas e mantém inspeção sem leitura', async () => {
  const wrapper = mount(Experiment, { global: { stubs: { CandidateScene: true, OriginalScene: true } } })
  await wrapper.get('li button').trigger('click')
  expect(wrapper.get('.inspector').attributes('data-selected-id')).not.toBe('')
  await wrapper.get('select[name="state"]').setValue('empty')
  expect(wrapper.get('.inspector').text()).toContain('Sem dados atuais')
  expect(wrapper.findAll('li button')).toHaveLength(9)
  await wrapper.get('select[name="scene"]').setValue('baseline')
  expect(wrapper.get('.inspector').attributes('data-selected-id')).toBe('')
  wrapper.unmount()
  expect(Reflect.has(window, 'rd02')).toBe(false)
})
