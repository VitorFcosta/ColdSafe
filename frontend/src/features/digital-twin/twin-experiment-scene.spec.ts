// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as THREE from 'three'
import CandidateScene from './DigitalTwinScene.vue'
import type { TwinItem } from './twin-state'

const gpu = vi.hoisted(() => ({ render: vi.fn(), setAnimationLoop: vi.fn(), setSize: vi.fn(), setPixelRatio: vi.fn(), dispose: vi.fn(), forceContextLoss: vi.fn(), fail: false }))
vi.mock('three', async (original) => ({ ...await original<typeof THREE>(), WebGLRenderer: class {
  domElement = document.createElement('canvas')
  shadowMap = { enabled: false, autoUpdate: true, needsUpdate: false }
  render = gpu.render; setSize = gpu.setSize; setPixelRatio = gpu.setPixelRatio
  setAnimationLoop = gpu.setAnimationLoop; dispose = gpu.dispose; forceContextLoss = gpu.forceContextLoss
  constructor() { if (gpu.fail) throw new Error('WebGL indisponível') }
} }))
const items: TwinItem[] = [
  { id: 'fan-1', key: 'fan', kind: 'equipment', label: 'Ventilador', value: 'Em operação', status: 'normal', position: [0,0,0] },
  { id: 'led-1', key: 'led', kind: 'actuator', label: 'LED', value: 'Ligado', status: 'normal', position: [0,0,0] },
]
const visual = { running: true, vibration: 2, temperature: 5, light: 40, led: true, buzzer: true }
let motionChange: (event: { matches: boolean }) => void
const disconnect = vi.fn(), removeMotion = vi.fn()
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: (_: string, callback: typeof motionChange) => { motionChange = callback }, removeEventListener: removeMotion }))
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); gpu.fail = false })
const scene = () => mount(CandidateScene, { props: { items, selectedId: null, visual } })

it('pausa persiste diante de seleção/dados; retoma sem compensar o intervalo parado', async () => {
  const wrapper = scene()
  const root = gpu.render.mock.calls.at(-1)![0] as THREE.Scene
  const rotor = root.getObjectByName('rotor')!
  let loop = gpu.setAnimationLoop.mock.calls.at(-1)![0] as (time: number) => void
  loop(0); loop(50)
  expect(rotor.rotation.z).toBeGreaterThan(0)
  await wrapper.get('button').trigger('click')
  expect(gpu.setAnimationLoop).toHaveBeenLastCalledWith(null)
  const angle = rotor.rotation.z
  await wrapper.setProps({ selectedId: 'led-1', visual: { ...visual, temperature: 10 } })
  expect(wrapper.get('button').text()).toBe('Retomar animação')
  loop(9000)
  expect(rotor.rotation.z).toBe(angle)
  await wrapper.get('button').trigger('click')
  loop = gpu.setAnimationLoop.mock.calls.at(-1)![0]
  loop(9000)
  expect(rotor.rotation.z).toBe(angle)
  loop(9050)
  expect(rotor.rotation.z).toBeGreaterThan(angle)
  wrapper.unmount()
})
it('stale, preferência reduzida, aba oculta e equipamento parado impedem loop contínuo', async () => {
  const wrapper = scene()
  await wrapper.setProps({ visual: null })
  expect(gpu.setAnimationLoop).toHaveBeenLastCalledWith(null)
  expect(wrapper.text()).toContain('sem telemetria atual')
  motionChange({ matches: true }); await nextTick()
  await wrapper.setProps({ visual })
  expect(wrapper.text()).toContain('Movimento reduzido')
  expect(gpu.setAnimationLoop).toHaveBeenLastCalledWith(null)
  motionChange({ matches: false }); await nextTick()
  expect(gpu.setAnimationLoop.mock.calls.at(-1)![0]).toBeTypeOf('function')
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
  document.dispatchEvent(new Event('visibilitychange'))
  expect(gpu.setAnimationLoop).toHaveBeenLastCalledWith(null)
  await wrapper.get('button').trigger('click')
  await wrapper.get('button').trigger('click')
  expect(gpu.setAnimationLoop).toHaveBeenLastCalledWith(null)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  document.dispatchEvent(new Event('visibilitychange'))
  await wrapper.setProps({ visual: { ...visual, running: false, vibration: 0, buzzer: false } })
  expect(gpu.setAnimationLoop).toHaveBeenLastCalledWith(null)
  wrapper.unmount()
})
it('seleção usa ID atual e um item sem ID não emite seleção', async () => {
  const wrapper = scene()
  const root = gpu.render.mock.calls.at(-1)![0] as THREE.Scene
  const led = root.getObjectByName('led')!
  vi.spyOn(THREE.Raycaster.prototype, 'intersectObjects').mockReturnValue([{ object: led } as THREE.Intersection])
  vi.spyOn(wrapper.get('canvas').element, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect)
  await wrapper.get('canvas').trigger('click', { clientX: 50, clientY: 50 })
  expect(wrapper.emitted('select')).toEqual([['led-1']])
  await wrapper.setProps({ items: [{ ...items[1]!, id: null }] })
  await wrapper.get('canvas').trigger('click', { clientX: 50, clientY: 50 })
  expect(wrapper.emitted('select')).toHaveLength(1)
  wrapper.unmount()
})
it('perda WebGL mantém fallback e cleanup libera contexto/listeners/recursos', async () => {
  const geometry = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose')
  const material = vi.spyOn(THREE.Material.prototype, 'dispose')
  const wrapper = scene()
  await wrapper.get('canvas').trigger('webglcontextlost')
  expect(wrapper.text()).toContain('3D indisponível')
  expect(gpu.setAnimationLoop).toHaveBeenLastCalledWith(null)
  wrapper.unmount()
  expect(gpu.dispose).toHaveBeenCalledOnce()
  expect(gpu.forceContextLoss).toHaveBeenCalledOnce()
  expect(disconnect).toHaveBeenCalledOnce()
  expect(removeMotion).toHaveBeenCalledOnce()
  expect(geometry).toHaveBeenCalled()
  expect(material).toHaveBeenCalled()
  gpu.fail = true
  const failed = scene()
  await nextTick()
  expect(failed.text()).toContain('3D indisponível')
  failed.unmount()
})
