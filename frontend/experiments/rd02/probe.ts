import { Scene, type Camera, type WebGLRenderer, type WebGLRenderTarget } from 'three'

type SceneHooks = {
  onBeforeRender(renderer: WebGLRenderer, scene: Scene, camera: Camera, target: WebGLRenderTarget | null): void
  onAfterRender(renderer: WebGLRenderer, scene: Scene, camera: Camera): void
}

export function summarizeFrames(timestamps: readonly number[], durationMs: number) {
  const intervals = timestamps.slice(1).map((time, index) => time - timestamps[index]!).sort((a, b) => a - b)
  return { frames: timestamps.length, durationMs, fps: durationMs > 0 ? timestamps.length * 1000 / durationMs : 0,
    p95IntervalMs: intervals.length ? intervals[Math.ceil(intervals.length * .95) - 1]! : null }
}

function resources(renderer: WebGLRenderer) {
  return { geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures, programs: renderer.info.programs?.length ?? 0 }
}

// Scene callbacks receive the renderer; r186 defines render/dispose on instances, not their prototype.
export function installProbe() {
  const hooks = Scene.prototype as unknown as SceneHooks
  const before = hooks.onBeforeRender, after = hooks.onAfterRender
  type Entry = { renderer: WeakRef<WebGLRenderer>; context: WeakRef<ReturnType<WebGLRenderer['getContext']>>; renders: number; disposed: boolean }
  const entries: Entry[] = []
  const known = new WeakMap<WebGLRenderer, Entry>()
  const resetValues = new WeakMap<Scene, boolean>()
  let latest: Entry | undefined
  let totalRenders = 0, sampling = false, startedAt = 0, maxCalls = 0, maxTriangles = 0
  let timestamps: number[] = []
  let truncated = false

  hooks.onBeforeRender = function (renderer, scene, camera, target) {
    before.call(this, renderer, scene, camera, target)
    let entry = known.get(renderer)
    if (!entry) {
      entry = { renderer: new WeakRef(renderer), context: new WeakRef(renderer.getContext()), renders: 0, disposed: false }
      known.set(renderer, entry)
      entries.push(entry)
      if (entries.length > 32) { entries.shift(); truncated = true }
      const dispose = renderer.dispose
      renderer.dispose = function () {
        try { dispose.call(this) } finally { entry!.disposed = true }
      }
    }
    latest = entry
    resetValues.set(this as unknown as Scene, renderer.info.autoReset)
    renderer.info.autoReset = false
    renderer.info.reset()
  }
  hooks.onAfterRender = function (renderer, scene, camera) {
    renderer.info.autoReset = resetValues.get(this as unknown as Scene) ?? true
    const entry = known.get(renderer)!
    entry.renders++
    totalRenders++
    if (sampling) {
      timestamps.push(performance.now())
      maxCalls = Math.max(maxCalls, renderer.info.render.calls)
      maxTriangles = Math.max(maxTriangles, renderer.info.render.triangles)
    }
    after.call(this, renderer, scene, camera)
  }

  function snapshot() {
    const renderer = latest?.renderer.deref()
    const context = latest?.context.deref()
    const extension = context?.getExtension('WEBGL_debug_renderer_info')
    return {
      renders: latest?.renders ?? 0, totalRenders, resources: renderer ? resources(renderer) : null,
      render: renderer ? { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles } : null,
      dpr: renderer?.getPixelRatio() ?? null,
      gpu: context ? { renderer: extension ? context.getParameter(extension.UNMASKED_RENDERER_WEBGL) as string : null,
        vendor: extension ? context.getParameter(extension.UNMASKED_VENDOR_WEBGL) as string : null,
        version: context.getParameter(context.VERSION) as string } : null,
      liveContexts: entries.filter((entry) => entry.context.deref()?.isContextLost() === false).length,
      trackingTruncated: truncated,
      disposed: entries.filter((entry) => entry.disposed).map((entry) => {
        const value = entry.renderer.deref()
        return { resources: value ? resources(value) : null, contextLost: entry.context.deref()?.isContextLost() ?? null }
      }),
    }
  }
  return {
    snapshot,
    start() { timestamps = []; maxCalls = 0; maxTriangles = 0; startedAt = performance.now(); sampling = true },
    stop() { sampling = false; return { ...summarizeFrames(timestamps, performance.now() - startedAt), maxCalls, maxTriangles, ...snapshot() } },
    uninstall() { hooks.onBeforeRender = before; hooks.onAfterRender = after; sampling = false },
  }
}
