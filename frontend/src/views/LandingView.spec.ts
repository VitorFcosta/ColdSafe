// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import LandingView from './LandingView.vue'

vi.mock('motion-v', async () => {
  const { ref } = await import('vue')
  return { motion: { section: 'section', div: 'div', li: 'li' }, useReducedMotion: () => ref(false) }
})

it('apresenta a arquitetura e identifica claramente a demonstração simulada', () => {
  const wrapper = mount(LandingView, { global: { stubs: ['RouterLink'] } })

  expect(wrapper.get('h1').text()).toContain('Cada grau')
  expect(wrapper.findAll('.architecture-step')).toHaveLength(4)
  expect(wrapper.get('video').attributes('controls')).toBeDefined()
  expect(wrapper.get('track').attributes('src')).toBe('/media/coldsafe-demo.vtt')
  expect(wrapper.get('.demo-video figcaption').text()).toContain('Demonstração simulada')
  expect(wrapper.get('a.skip-link').attributes('href')).toBe('#conteudo')
  wrapper.unmount()
})
