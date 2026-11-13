// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, nextTick, onUnmounted, ref } from 'vue'
import { sessionToken } from '../account/session'
import LiveDataRegion from './LiveDataRegion.vue'

afterEach(() => { sessionToken.value = null })

describe('LiveDataRegion', () => {
  it('oculta sem desmontar, conserva foco e mostra os dados recebidos durante a ocultação', async () => {
    const value = ref(10)
    let unmounted = false
    const Child = defineComponent({ setup() {
      onUnmounted(() => { unmounted = true })
      return () => String(value.value)
    } })
    const wrapper = mount(LiveDataRegion, { attachTo: document.body, slots: { default: Child } })
    try {
      const button = wrapper.get('button')
      const region = wrapper.get('[data-live-region]')
      expect(button.attributes('aria-controls')).toBe(region.attributes('id'))
      expect(button.attributes('aria-expanded')).toBe('true')
      ;(button.element as HTMLButtonElement).focus()
      await button.trigger('click')
      expect(button.text()).toBe('Mostrar dados ao vivo')
      expect(button.attributes('aria-expanded')).toBe('false')
      expect(region.attributes('hidden')).toBeDefined()
      expect(document.activeElement).toBe(button.element)
      value.value = 20
      await nextTick()
      expect(unmounted).toBe(false)
      await button.trigger('click')
      expect(region.attributes('hidden')).toBeUndefined()
      expect(region.text()).toBe('20')
      expect(document.activeElement).toBe(button.element)
    } finally { wrapper.unmount() }
    expect(unmounted).toBe(true)
  })

  it('reinicia a ocultação ao mudar de equipamento ou sessão', async () => {
    sessionToken.value = 'first-session'
    const wrapper = mount(LiveDataRegion, { props: { resetKey: 'first-device' } })
    try {
      await wrapper.get('button').trigger('click')
      await wrapper.setProps({ resetKey: 'second-device' })
      expect(wrapper.get('button').attributes('aria-expanded')).toBe('true')
      await wrapper.get('button').trigger('click')
      sessionToken.value = 'second-session'
      await nextTick()
      expect(wrapper.get('button').attributes('aria-expanded')).toBe('true')
    } finally { wrapper.unmount() }
  })
})
