// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import * as THREE from 'three'
import DigitalTwinScene from './DigitalTwinScene.vue'
import type { TwinItem } from './twin-state'

const renderer = vi.hoisted(() => ({ render: vi.fn(), setSize: vi.fn(), setPixelRatio: vi.fn(), dispose: vi.fn(), forceContextLoss: vi.fn(), fail: false }))
vi.mock('three', async (original) => ({ ...await original<typeof THREE>(), WebGLRenderer: class {
  domElement = document.createElement('canvas')
  render = renderer.render; setSize = renderer.setSize; setPixelRatio = renderer.setPixelRatio
  dispose = renderer.dispose; forceContextLoss = renderer.forceContextLoss
  constructor() { if (renderer.fail) throw new Error('no gpu') }
} }))
const item: TwinItem = { id: 'sensor-id', key: 'temperature_c', label: 'Temperatura ambiente', kind: 'sensor', value: '5 °C', status: 'normal', position: [0, 0, 0] }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); renderer.fail = false })
function mountScene(items = [item]) {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect })
  return mount(DigitalTwinScene, { props: { items, selectedId: null } })
}
const disconnect = vi.fn()

it('atualiza cor/seleção por props e libera geometria, material, observer e contexto ao desmontar', async () => {
  const geometry = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose')
  const material = vi.spyOn(THREE.Material.prototype, 'dispose')
  const wrapper = mountScene()
  expect(wrapper.find('canvas').exists()).toBe(true)
  await wrapper.setProps({ items: [{ ...item, status: 'critical' }], selectedId: item.id })
  expect(renderer.render).toHaveBeenCalled()
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const sensor = scene.children.find((object) => object.userData.key === item.key) as THREE.Mesh
  expect(sensor.userData.id).toBe('sensor-id')
  expect((sensor.material as THREE.MeshStandardMaterial).color.getHex()).toBe(0xc3353c)
  expect(sensor.scale.x).toBeGreaterThan(1)
  wrapper.unmount()
  expect(geometry).toHaveBeenCalled()
  expect(material).toHaveBeenCalled()
  expect(disconnect).toHaveBeenCalledOnce()
  expect(renderer.dispose).toHaveBeenCalledOnce()
  expect(renderer.forceContextLoss).toHaveBeenCalledOnce()
})
it('raycast seleciona o ID recebido e ignora peça sem cadastro', async () => {
  const wrapper = mountScene()
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const sensor = scene.children.find((object) => object.userData.key === item.key)!
  vi.spyOn(THREE.Raycaster.prototype, 'intersectObjects').mockReturnValue([{ object: sensor } as THREE.Intersection])
  vi.spyOn(wrapper.get('canvas').element, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect)
  await wrapper.get('canvas').trigger('click', { clientX: 50, clientY: 50 })
  expect(wrapper.emitted('select')).toEqual([['sensor-id']])
  await wrapper.setProps({ items: [{ ...item, id: null }] })
  await wrapper.get('canvas').trigger('click', { clientX: 50, clientY: 50 })
  expect(wrapper.emitted('select')).toHaveLength(1)
  wrapper.unmount()
})
it('libera uma vez o material compartilhado pelas hélices e preserva câmera no resize', async () => {
  const material = vi.spyOn(THREE.Material.prototype, 'dispose')
  const geometry = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose')
  let resized!: () => void
  vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { resized = callback } observe() {} disconnect() {} })
  const wrapper = mount(DigitalTwinScene, { props: { items: [{ ...item, kind: 'equipment', key: 'fan' }, { ...item, key: 'led', kind: 'actuator', id: 'led' }], selectedId: null } })
  resized()
  expect(renderer.setSize).toHaveBeenCalled()
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  expect(scene.children.find((object) => object.userData.key === 'fan')?.children).toHaveLength(5)
  wrapper.unmount()
  expect(geometry).toHaveBeenCalledTimes(6)
  expect(material).toHaveBeenCalledTimes(2)
})
it('falha WebGL conserva mensagem e perda de contexto pede reabertura', async () => {
  renderer.fail = true
  const failed = mountScene()
  await nextTick()
  expect(failed.text()).toContain('3D indisponível')
  expect(failed.find('canvas').exists()).toBe(false)
  failed.unmount()
  renderer.fail = false
  const wrapper = mountScene()
  await wrapper.get('canvas').trigger('webglcontextlost')
  expect(wrapper.text()).toContain('3D indisponível')
  wrapper.unmount()
})
