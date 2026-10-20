// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as THREE from 'three'
import DigitalTwinScene from './DigitalTwinScene.vue'
import type { TwinItem } from './twin-state'

const renderer = vi.hoisted(() => ({ render: vi.fn(), setAnimationLoop: vi.fn(), setSize: vi.fn(), setPixelRatio: vi.fn(), dispose: vi.fn(), forceContextLoss: vi.fn(), fail: false }))
vi.mock('three', async (original) => ({ ...await original<typeof THREE>(), WebGLRenderer: class {
  domElement = document.createElement('canvas')
  render = renderer.render; setSize = renderer.setSize; setPixelRatio = renderer.setPixelRatio
  setAnimationLoop = renderer.setAnimationLoop
  dispose = renderer.dispose; forceContextLoss = renderer.forceContextLoss
  constructor() { if (renderer.fail) throw new Error('no gpu') }
} }))
const item: TwinItem = { id: 'sensor-id', key: 'temperature_c', label: 'Temperatura ambiente', kind: 'sensor', value: '5 °C', status: 'normal', position: [0, 0, 0] }
const visual = { running: true, vibration: 2, temperature: 5, light: 20, led: true, buzzer: true }
let motionChanged: (event: { matches: boolean }) => void
const removeMotionListener = vi.fn()
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: (_type: string, listener: typeof motionChanged) => { motionChanged = listener }, removeEventListener: removeMotionListener }))
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); renderer.fail = false })
function mountScene(items = [item]) {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect })
  return mount(DigitalTwinScene, { props: { items, selectedId: null, visual: null } })
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
  const wrapper = mount(DigitalTwinScene, { props: { items: [{ ...item, kind: 'equipment', key: 'fan' }, { ...item, key: 'led', kind: 'actuator', id: 'led' }], selectedId: null, visual: null } })
  resized()
  expect(renderer.setSize).toHaveBeenCalled()
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  expect(scene.children.find((object) => object.userData.key === 'fan')?.children).toHaveLength(5)
  wrapper.unmount()
  expect(geometry).toHaveBeenCalledTimes(7)
  expect(material).toHaveBeenCalledTimes(3)
})
it('reutiliza cena, anima por telemetria e congela pose/luz após freshness sem inventar movimento', async () => {
  const wrapper = mountScene([{ ...item, kind: 'equipment', key: 'fan' }, { ...item, key: 'led', kind: 'actuator' }, { ...item, key: 'buzzer', kind: 'actuator' }])
  await wrapper.setProps({ visual })
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const fan = scene.children.find((object) => object.userData.key === 'fan')!
  const led = scene.children.find((object) => object.userData.key === 'led') as THREE.Mesh<THREE.SphereGeometry, THREE.MeshStandardMaterial>
  const buzzer = scene.children.find((object) => object.userData.key === 'buzzer') as typeof led
  const ambient = scene.children.find((object) => object instanceof THREE.AmbientLight) as THREE.AmbientLight
  const marker = scene.getObjectByName('thermal-marker') as typeof led
  const light = ambient.intensity
  const color = marker.material.color.getHex()
  const animate = renderer.setAnimationLoop.mock.calls.at(-1)![0] as (time: number) => void
  animate(0); animate(50)
  expect(fan.rotation.z).toBeGreaterThan(0)
  const shake = Math.abs(fan.position.x)
  expect(shake).toBeGreaterThan(0)
  expect(led.material.emissiveIntensity).toBeGreaterThan(0)
  expect(buzzer.material.emissiveIntensity).toBeGreaterThan(0)
  await wrapper.setProps({ visual: { ...visual, light: 100, temperature: 40, vibration: 4, led: false } })
  expect(scene.children.find((object) => object.userData.key === 'fan')).toBe(fan)
  expect(ambient.intensity).toBeGreaterThan(light)
  expect(marker.material.color.getHex()).not.toBe(color)
  expect(led.material.emissiveIntensity).toBe(0)
  animate(50)
  expect(Math.abs(fan.position.x)).toBeCloseTo(shake * 2)
  await wrapper.setProps({ visual: { ...visual, running: false, vibration: 0, buzzer: false } })
  const angle = fan.rotation.z
  animate(100)
  expect(fan.rotation.z).toBe(angle)
  await wrapper.setProps({ visual })
  animate(150); animate(200)
  await wrapper.setProps({ visual: null })
  const frozen = [fan.rotation.z, fan.position.x, ambient.intensity, marker.material.color.getHex(), buzzer.material.emissiveIntensity]
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  animate(20_000)
  expect([fan.rotation.z, fan.position.x, ambient.intensity, marker.material.color.getHex(), buzzer.material.emissiveIntensity]).toEqual(frozen)
  expect(wrapper.text()).toContain('Cena congelada')
  wrapper.unmount()
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  expect(removeMotionListener).toHaveBeenCalled()
})
it('movimento reduzido e aba oculta suspendem o loop; nova preferência retoma sem salto', async () => {
  const wrapper = mountScene([{ ...item, key: 'fan', kind: 'equipment' }])
  await wrapper.setProps({ visual })
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const fan = scene.children.find((object) => object.userData.key === 'fan')!
  motionChanged({ matches: true }); await nextTick()
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  expect(wrapper.text()).toContain('Movimento reduzido')
  motionChanged({ matches: false }); await nextTick()
  const animate = renderer.setAnimationLoop.mock.calls.at(-1)![0] as (time: number) => void
  animate(0); animate(50)
  const angle = fan.rotation.z
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
  document.dispatchEvent(new Event('visibilitychange'))
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  document.dispatchEvent(new Event('visibilitychange'))
  animate(80_000)
  expect(fan.rotation.z).toBe(angle)
  await wrapper.get('canvas').trigger('webglcontextlost')
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  wrapper.unmount()
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
it('falha no primeiro render interrompe o loop já iniciado e conserva fallback', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  renderer.render.mockImplementationOnce(() => { throw new Error('render failed') })
  const wrapper = mount(DigitalTwinScene, { props: { items: [item], selectedId: null, visual } })
  await nextTick()
  expect(wrapper.text()).toContain('3D indisponível')
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  wrapper.unmount()
})
