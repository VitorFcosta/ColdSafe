import { afterEach, expect, it, vi } from 'vitest'
import { Camera, Scene, type WebGLRenderer } from 'three'
import { installProbe, summarizeFrames } from '../../../experiments/rd02/probe'

afterEach(() => vi.restoreAllMocks())

it('mede FPS e p95 sem alterar amostras e mantém ausência de quadros explícita', () => {
  const times = [0, 16, 32, 48]
  expect(summarizeFrames(times, 64)).toEqual({ frames: 4, durationMs: 64, fps: 62.5, p95IntervalMs: 16 })
  expect(times).toEqual([0, 16, 32, 48])
  expect(summarizeFrames([], 60_000)).toEqual({ frames: 0, durationMs: 60_000, fps: 0, p95IntervalMs: null })
})

it('mede passes, restaura autoReset e registra descarte sem depender de bytes exatos de GPU', () => {
  let lost = false
  const context = { isContextLost: () => lost, getExtension: () => null, getParameter: () => 'WebGL 2', VERSION: 7938 }
  const fake = {
    info: { autoReset: true, reset: vi.fn(), render: { calls: 31, triangles: 3000 }, memory: { geometries: 7, textures: 1 }, programs: [1, 2] },
    getPixelRatio: () => 2, getContext: () => context,
    dispose: vi.fn(() => { fake.info.memory.geometries = 0; fake.info.memory.textures = 0; fake.info.programs = [] }),
  } as unknown as WebGLRenderer
  const probe = installProbe()
  const scene = new Scene()
  probe.start()
  Reflect.apply(scene.onBeforeRender, scene, [fake, scene, new Camera(), null])
  expect(fake.info.autoReset).toBe(false)
  Reflect.apply(scene.onAfterRender, scene, [fake, scene, new Camera()])
  expect(fake.info.autoReset).toBe(true)
  expect(probe.snapshot()).toMatchObject({ renders: 1, totalRenders: 1, resources: { geometries: 7, textures: 1, programs: 2 }, render: { calls: 31, triangles: 3000 }, dpr: 2, liveContexts: 1 })
  fake.dispose()
  lost = true
  expect(probe.snapshot()).toMatchObject({ resources: { geometries: 0, textures: 0, programs: 0 }, liveContexts: 0, disposed: [{ resources: { geometries: 0, textures: 0, programs: 0 }, contextLost: true }] })
  expect(probe.stop()).toMatchObject({ frames: 1, maxCalls: 31, maxTriangles: 3000 })
  probe.uninstall()
})

it('não deixa amostras de uma coleta contaminar a seguinte', () => {
  let time = 0
  vi.spyOn(performance, 'now').mockImplementation(() => time)
  const context = { isContextLost: () => false, getExtension: () => null, getParameter: () => '', VERSION: 7938 }
  const fake = { info: { autoReset: true, reset() {}, render: { calls: 1, triangles: 12 }, memory: { geometries: 1, textures: 0 }, programs: [] }, getPixelRatio: () => 1, getContext: () => context, dispose() {} } as unknown as WebGLRenderer
  const probe = installProbe(), scene = new Scene(), camera = new Camera()
  probe.start()
  for (const value of [0, 20, 40]) { time = value; Reflect.apply(scene.onBeforeRender, scene, [fake, scene, camera, null]); Reflect.apply(scene.onAfterRender, scene, [fake, scene, camera]) }
  time = 60
  expect(probe.stop()).toMatchObject({ frames: 3, durationMs: 60, fps: 50, p95IntervalMs: 20 })
  probe.start(); time = 100
  expect(probe.stop()).toMatchObject({ frames: 0, durationMs: 40, fps: 0, p95IntervalMs: null, maxCalls: 0, maxTriangles: 0 })
  probe.uninstall()
})
