// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import LandingView from './LandingView.vue'

it('apresenta a arquitetura e identifica claramente a demonstração simulada', () => {
  const wrapper = mount(LandingView, { global: { stubs: ['RouterLink'] } })

  expect(wrapper.get('h1').text()).toContain('Da leitura do sensor')
  expect(wrapper.findAll('.architecture-step')).toHaveLength(3)
  expect(wrapper.get('video').attributes('controls')).toBeDefined()
  expect(wrapper.get('track').attributes('src')).toBe('/media/coldsafe-demo.vtt')
  expect(wrapper.get('.demo-video figcaption').text()).toContain('Demonstração simulada')
  expect(wrapper.get('a.skip-link').attributes('href')).toBe('#conteudo')
  wrapper.unmount()
})

it('recupera falha de vídeo sem autoplay e oferece alternativa fora do player', async () => {
  const wrapper = mount(LandingView, { global: { stubs: ['RouterLink'] } })
  const video = wrapper.get<HTMLVideoElement>('video')
  const reload = vi.spyOn(video.element, 'load').mockImplementation(() => {})
  await video.trigger('error')
  expect(wrapper.get('[role="status"]').text()).toContain('Vídeo indisponível')
  const retry = wrapper.get('button[data-testid="retry-video"]')
  expect(wrapper.find('a[download][href="/media/coldsafe-demo.webm"]').exists()).toBe(true)
  await retry.trigger('click')
  expect(reload).toHaveBeenCalledOnce()
  expect(wrapper.find('[role="status"]').exists()).toBe(false)
  expect(video.attributes('autoplay')).toBeUndefined()
  await video.trigger('error')
  expect(wrapper.get('[role="status"]').text()).toContain('Vídeo indisponível')
  await video.trigger('loadedmetadata')
  expect(wrapper.find('[role="status"]').exists()).toBe(false)
  wrapper.unmount()
})

it('identifica gravação anterior e oferece transcrição quando legendas falham', async () => {
  const wrapper = mount(LandingView, { global: { stubs: ['RouterLink'] } })
  expect(wrapper.get('.hero-preview figcaption').text()).toContain('imagem gerada por IA')
  expect(wrapper.get('.demo-video figcaption').text()).toContain('setembro de 2026')
  expect(wrapper.get('#transcript').text()).toContain('LED')
  await wrapper.get('track').trigger('error')
  expect(wrapper.text()).toContain('As legendas não puderam ser carregadas')
  expect(wrapper.find('a[href="#transcript"]').exists()).toBe(true)
  wrapper.unmount()
})

it('fecha menu ao navegar e remove aviso de legenda após recuperação', async () => {
  const wrapper = mount(LandingView, { global: { stubs: ['RouterLink'] } })
  const menu = wrapper.get<HTMLDetailsElement>('.mobile-nav')
  menu.element.open = true
  await menu.get('a[href="#como-funciona"]').trigger('click')
  expect(menu.element.open).toBe(false)
  await wrapper.get('track').trigger('error')
  expect(wrapper.find('.caption-error').exists()).toBe(true)
  await wrapper.get('track').trigger('load')
  expect(wrapper.find('.caption-error').exists()).toBe(false)
  wrapper.unmount()
})
