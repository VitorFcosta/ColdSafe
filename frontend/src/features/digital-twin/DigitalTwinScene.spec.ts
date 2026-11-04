// @vitest-environment happy-dom
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as THREE from 'three'
import DigitalTwinScene from './DigitalTwinScene.vue'
import type { TwinItem } from './twin-state'

enableAutoUnmount(afterEach)

const renderer = vi.hoisted(() => ({ render: vi.fn(), setAnimationLoop: vi.fn(), setSize: vi.fn(), setPixelRatio: vi.fn(), dispose: vi.fn(), forceContextLoss: vi.fn(), fail: false }))
vi.mock('three', async (original) => ({ ...await original<typeof THREE>(), WebGLRenderer: class {
  domElement = document.createElement('canvas')
  shadowMap = { enabled: false, autoUpdate: true, needsUpdate: false }
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

it('seleciona por contorno sem pintar outros materiais e libera recursos ao desmontar', async () => {
  const geometry = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose')
  const material = vi.spyOn(THREE.Material.prototype, 'dispose')
  const wrapper = mountScene()
  expect(wrapper.find('canvas').exists()).toBe(true)
  await wrapper.setProps({ items: [{ ...item, status: 'critical' }], selectedId: item.id })
  expect(renderer.render).toHaveBeenCalled()
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const sensor = scene.getObjectByName(item.key)!
  const housing = sensor.getObjectByName('housing') as THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>
  expect(sensor.userData.id).toBe('sensor-id')
  expect(housing.material.color.getHex()).toBe(0x8d9695)
  expect(sensor.scale.x).toBe(1)
  expect(scene.children.find((object) => object instanceof THREE.Box3Helper)?.visible).toBe(true)
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
  const sensor = scene.getObjectByName(item.key)!
  vi.spyOn(THREE.Raycaster.prototype, 'intersectObjects').mockReturnValue([{ object: sensor } as THREE.Intersection])
  vi.spyOn(wrapper.get('canvas').element, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect)
  await wrapper.get('canvas').trigger('click', { clientX: 50, clientY: 50 })
  expect(wrapper.emitted('select')).toEqual([['sensor-id']])
  await wrapper.setProps({ items: [{ ...item, id: null }] })
  await wrapper.get('canvas').trigger('click', { clientX: 50, clientY: 50 })
  expect(wrapper.emitted('select')).toHaveLength(1)
  wrapper.unmount()
})
it('libera uma vez geometria/material compartilhados pelas hélices e preserva câmera no resize', async () => {
  let resized!: () => void
  vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { resized = callback } observe() {} disconnect() {} })
  const wrapper = mount(DigitalTwinScene, { props: { items: [{ ...item, kind: 'equipment', key: 'fan' }], selectedId: null, visual: null } })
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const camera = renderer.render.mock.calls.at(-1)![1] as THREE.OrthographicCamera
  const position = camera.position.clone()
  const blade = scene.getObjectByName('blade-1') as THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>
  const geometry = vi.spyOn(blade.geometry, 'dispose'), material = vi.spyOn(blade.material, 'dispose')
  resized()
  expect(renderer.setSize).toHaveBeenCalled()
  expect(camera.position).toEqual(position)
  expect(scene.getObjectByName('blades')?.children).toHaveLength(4)
  expect(scene.getObjectByName('guard')).toBeDefined()
  wrapper.unmount()
  expect(geometry).toHaveBeenCalledOnce()
  expect(material).toHaveBeenCalledOnce()
})
it('reutiliza cena, anima por telemetria e congela pose/luz após freshness sem inventar movimento', async () => {
  const wrapper = mountScene([{ ...item, kind: 'equipment', key: 'fan' }, { ...item, key: 'led', kind: 'actuator' }, { ...item, key: 'buzzer', kind: 'actuator' }])
  await wrapper.setProps({ visual })
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const fan = scene.getObjectByName('rotor')!
  const led = scene.getObjectByName('led-lens') as THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>
  const buzzer = scene.getObjectByName('buzzer-body') as typeof led
  const ambient = scene.children.find((object) => object instanceof THREE.HemisphereLight) as THREE.HemisphereLight
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
  expect(scene.getObjectByName('rotor')).toBe(fan)
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
  const fan = scene.getObjectByName('rotor')!
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

it('pausa manual persiste com novas leituras e seleção sem retomar o relógio antigo', async () => {
  const wrapper = mountScene([{ ...item, key: 'fan', kind: 'equipment' }])
  await wrapper.setProps({ visual })
  const scene = renderer.render.mock.calls.at(-1)![0] as THREE.Scene
  const rotor = scene.getObjectByName('rotor')!
  expect(rotor).toBeDefined()
  const animate = renderer.setAnimationLoop.mock.calls.at(-1)![0] as (time: number) => void
  animate(0); animate(50)
  const angle = rotor.rotation.z
  await wrapper.get('button').trigger('click')
  expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
  expect(wrapper.emitted('update:paused')).toEqual([[true]])
  await wrapper.setProps({ selectedId: item.id, visual: { ...visual, temperature: 40 } })
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  animate(90_000)
  expect(rotor.rotation.z).toBe(angle)
  await wrapper.get('button').trigger('click')
  const resumed = renderer.setAnimationLoop.mock.calls.at(-1)![0] as (time: number) => void
  resumed(90_000)
  expect(rotor.rotation.z).toBe(angle)
  wrapper.unmount()
})

it('não desenha consultas em aba oculta e aplica DPR atualizado no resize', async () => {
  const wrapper = mountScene()
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
  document.dispatchEvent(new Event('visibilitychange'))
  const calls = renderer.render.mock.calls.length
  await wrapper.setProps({ visual })
  expect(renderer.render).toHaveBeenCalledTimes(calls)
  vi.spyOn(window, 'devicePixelRatio', 'get').mockReturnValue(1.5)
  window.dispatchEvent(new Event('resize'))
  expect(renderer.setPixelRatio).toHaveBeenLastCalledWith(1.5)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  document.dispatchEvent(new Event('visibilitychange'))
  expect(renderer.render.mock.calls.length).toBeGreaterThan(calls)
  wrapper.unmount()
})

it('pausa fornecida pela view já suspende a primeira montagem e aceita retomada externa', async () => {
  const wrapper = mount(DigitalTwinScene, { props: { items: [{ ...item, key: 'fan', kind: 'equipment' }], selectedId: null, visual, paused: true } })
  expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
  expect(renderer.setAnimationLoop.mock.calls.every(([callback]) => callback === null)).toBe(true)
  expect(wrapper.text()).toContain('Animação pausada')
  await wrapper.setProps({ paused: false })
  expect(renderer.setAnimationLoop.mock.calls.at(-1)![0]).toBeTypeOf('function')
  wrapper.unmount()
})

it('falha inicial libera GPU, recursos e listeners imediatamente e não repete descarte ao desmontar', async () => {
  const material = vi.spyOn(THREE.Material.prototype, 'dispose')
  const geometry = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose')
  renderer.render.mockImplementationOnce(() => { throw new Error('render failed') })
  const wrapper = mountScene()
  await nextTick()
  expect(wrapper.find('canvas').exists()).toBe(false)
  expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  expect(renderer.dispose).toHaveBeenCalledOnce()
  expect(renderer.forceContextLoss).toHaveBeenCalledOnce()
  expect(disconnect).toHaveBeenCalledOnce()
  expect(removeMotionListener).toHaveBeenCalledOnce()
  expect(geometry).toHaveBeenCalled()
  const materials = material.mock.calls.length
  const ratios = renderer.setPixelRatio.mock.calls.length
  wrapper.unmount()
  window.dispatchEvent(new Event('resize'))
  expect(material).toHaveBeenCalledTimes(materials)
  expect(renderer.setPixelRatio).toHaveBeenCalledTimes(ratios)
})

it('DPR acima de2 é limitado em todo resize e ausência de movimento atual impede retomada', async () => {
  const wrapper = mountScene()
  await wrapper.setProps({ visual })
  vi.spyOn(window, 'devicePixelRatio', 'get').mockReturnValue(3)
  window.dispatchEvent(new Event('resize'))
  expect(renderer.setPixelRatio).toHaveBeenLastCalledWith(2)
  await wrapper.setProps({ visual: { ...visual, running: false, vibration: 0, buzzer: false } })
  await wrapper.get('button').trigger('click')
  await wrapper.get('button').trigger('click')
  expect(renderer.setAnimationLoop).toHaveBeenLastCalledWith(null)
  expect(wrapper.text()).toContain('Sem movimento observado na telemetria')
  wrapper.unmount()
})
