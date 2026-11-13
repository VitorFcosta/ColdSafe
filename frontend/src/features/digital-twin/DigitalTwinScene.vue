<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Box3, Box3Helper, BoxGeometry, Color, DirectionalLight, HemisphereLight, Mesh, MeshBasicMaterial, MeshStandardMaterial, OrthographicCamera, PCFShadowMap, PlaneGeometry, Raycaster, Scene, ShadowMaterial, SphereGeometry, Vector2, type Object3D } from 'three'
import type { TwinItem, TwinVisualState } from './twin-state'
import { WebGLRenderer } from 'three'
import { createFanModel } from './fan-model'

const props = defineProps<{ items: readonly TwinItem[]; selectedId: string | null; visual: TwinVisualState | null }>()
const emit = defineEmits<{ select: [id: string] }>()
const host = ref<HTMLElement | null>(null)
const unavailable = ref(false), reducedMotion = ref(false), hidden = ref(document.hidden)
const paused = defineModel<boolean>('paused', { default: false })
const labelPoint = ref({ x: 0, y: 0, height: 320 })
const selected = computed(() => props.items.find((item) => item.id !== null && item.id === props.selectedId))
const reason = computed(() => unavailable.value ? '3D indisponível neste navegador. Use a lista de componentes; reabra a página para tentar novamente.'
  : !props.visual ? 'Cena congelada: sem telemetria atual confirmada.'
    : reducedMotion.value ? 'Movimento reduzido. Animação suspensa.'
      : hidden.value ? 'Aba oculta: animação suspensa.'
        : !hasMotion() ? 'Sem movimento observado na telemetria atual.'
          : paused.value ? 'Animação pausada. Dados e seleção continuam disponíveis.' : 'Movimento ilustrativo ativo; não representa RPM medido.')
const scene = new Scene()
scene.background = new Color(0xf3f6f5)
const model = createFanModel()
scene.add(model.root)
const camera = new OrthographicCamera(-4, 4, 2.7, -2.7, .1, 60)
camera.position.set(6, 4, 8)
camera.lookAt(0, .5, 0)
const ambient = new HemisphereLight(0xffffff, 0x838e89, 1.5)
const keyLight = new DirectionalLight(0xffffff, 3.4)
keyLight.position.set(-3, 9, 4)
keyLight.castShadow = true
keyLight.shadow.mapSize.set(1024, 1024)
keyLight.shadow.camera.left = -4; keyLight.shadow.camera.right = 4
keyLight.shadow.camera.top = 4; keyLight.shadow.camera.bottom = -4
keyLight.shadow.normalBias = .035
keyLight.shadow.radius = 4
const fill = new DirectionalLight(0xe3eeef, 1.4)
fill.position.set(4, 3, -4)
const floor = new Mesh(new PlaneGeometry(200, 200), new ShadowMaterial({ opacity: .10 }))
floor.rotation.x = -Math.PI / 2
floor.position.y = -1.57
floor.receiveShadow = true
const thermal = new Mesh(new BoxGeometry(1.4, .06, .04), new MeshBasicMaterial({ color: 0x667681 }))
thermal.name = 'thermal-marker'
thermal.position.set(0, -1.13, 1.46)
scene.add(ambient, keyLight, fill, floor, thermal)
const box = new Box3()
const outline = new Box3Helper(box, 0x0c6d65)
outline.visible = false
scene.add(outline)
const markerGeometry = new SphereGeometry(.065, 10, 6)
const markerMaterial = new MeshBasicMaterial({ color: 0x0c6d65, depthTest: false })
const markers = new Map<string, Mesh>()
for (const [key, anchor] of model.anchors) {
  const marker = new Mesh(markerGeometry, markerMaterial)
  marker.position.copy(anchor)
  marker.renderOrder = 2
  marker.userData = { key, id: null }
  markers.set(key, marker)
  scene.add(marker)
}
const raycaster = new Raycaster()
let renderer: WebGLRenderer | null = null
let observer: ResizeObserver | null = null
let preference: MediaQueryList | null = null
let animating = false, previousTime: number | null = null, elapsed = 0
let disposed = false
let size = { width: 640, height: 400 }

function hasMotion() { return Boolean(props.visual && (props.visual.running || (props.visual.vibration ?? 0) > 0 || props.visual.buzzer)) }
function render() {
  if (!renderer || unavailable.value || hidden.value || disposed) return
  try { renderer.render(scene, camera) }
  catch { unavailable.value = true; releaseResources() }
}
function animate(time: number) {
  if (!animating || !props.visual) return
  const delta = previousTime === null ? 0 : Math.min(Math.max(0, time - previousTime) / 1000, .1)
  previousTime = time
  elapsed += delta
  if (props.visual.running) model.rotor.rotation.z = (model.rotor.rotation.z + delta * 4) % (Math.PI * 2)
  // shortcut: tremor do rotor ilustrativo e limitado a 10 mm/s; substituir apenas com calibração física.
  model.rotor.position.x = Math.sin(elapsed * 24) * Math.min(props.visual.vibration ?? 0, 10) * .012
  const buzzer = model.root.getObjectByName('buzzer-body') as Mesh<PlaneGeometry, MeshStandardMaterial>
  if (props.visual.buzzer) buzzer.material.emissiveIntensity = .3 + .15 * Math.sin(elapsed * Math.PI * 2)
  render()
}
function syncAnimation() {
  const next = Boolean(renderer && !unavailable.value && !paused.value && !reducedMotion.value && !hidden.value && hasMotion())
  if (next === animating) return
  animating = next
  previousTime = null
  renderer?.setAnimationLoop(next ? animate : null)
}
function projected() {
  scene.updateMatrixWorld(true)
  camera.updateMatrixWorld(true)
  return props.items.filter((item) => item.id && model.anchors.has(item.key)).map((item) => {
    const point = model.anchors.get(item.key)!.clone().project(camera)
    return { id: item.id!, key: item.key, x: (point.x + 1) / 2 * size.width, y: (1 - point.y) / 2 * size.height }
  })
}
function update() {
  if (!renderer || disposed) return
  for (const [key, object] of model.items) {
    const item = props.items.find((item) => item.key === key)
    object.userData = { key, id: item?.id ?? null }
    const marker = markers.get(key)!
    marker.userData = { key, id: item?.id ?? null }
    marker.visible = Boolean(item?.id)
  }
  const object = selected.value && model.items.get(selected.value.key)
  outline.visible = Boolean(object)
  if (object) box.setFromObject(object)
  const point = projected().find((point) => point.id === props.selectedId)
  if (point) labelPoint.value = { x: point.x, y: point.y, height: size.height }
  if (props.visual) {
    // shortcut: escala azul→vermelho de −20 a 60 °C, sem equivalência a risco físico.
    thermal.material.color.setHSL((1 - Math.max(0, Math.min(1, (props.visual.temperature + 20) / 80))) * .65, .8, .45)
    ambient.intensity = props.visual.light === null ? 1.5 : .9 + props.visual.light / 100 * 1.2
    const led = model.root.getObjectByName('led-lens') as Mesh<PlaneGeometry, MeshStandardMaterial>
    led.material.emissiveIntensity = props.visual.led ? 1.6 : 0
    const buzzer = model.root.getObjectByName('buzzer-body') as Mesh<PlaneGeometry, MeshStandardMaterial>
    buzzer.material.emissive.setHex(props.visual.buzzer ? 0x8b4c0c : 0)
    buzzer.material.emissiveIntensity = props.visual.buzzer ? .3 : 0
    if (!props.visual.vibration || reducedMotion.value) model.rotor.position.x = 0
  }
  syncAnimation()
  render()
}
function resize() {
  size = { width: host.value?.clientWidth || 640, height: host.value?.clientHeight || 400 }
  const halfHeight = Math.max(2.7, 3.2 * size.height / size.width)
  camera.left = -halfHeight * size.width / size.height; camera.right = -camera.left
  camera.top = halfHeight; camera.bottom = -halfHeight
  camera.updateProjectionMatrix()
  renderer?.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer?.setSize(size.width, size.height)
  update()
}
function select(event: MouseEvent) {
  if (!renderer || unavailable.value) return
  const bounds = renderer.domElement.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return
  raycaster.setFromCamera(new Vector2((event.clientX - bounds.left) / bounds.width * 2 - 1, 1 - (event.clientY - bounds.top) / bounds.height * 2), camera)
  // Marcadores são a alternativa visível para peças pequenas/ocultas; a malha também aceita seleção.
  const markerHit = raycaster.intersectObjects([...markers.values()].filter((marker) => marker.visible), false)[0]
  let object: Object3D | undefined = markerHit?.object ?? raycaster.intersectObjects([...model.items.values()], true)[0]?.object
  while (object && !object.userData.key) object = object.parent ?? undefined
  if (typeof object?.userData.id === 'string') emit('select', object.userData.id)
}
function motionChanged(event: MediaQueryListEvent) { reducedMotion.value = event.matches; update() }
function visibilityChanged() {
  hidden.value = document.hidden
  if (hidden.value) syncAnimation()
  else resize()
}
function contextLost(event: Event) { event.preventDefault(); unavailable.value = true; releaseResources() }
function togglePause() { paused.value = !paused.value }
function releaseRenderer() {
  if (!renderer) return
  renderer.setAnimationLoop(null)
  renderer.domElement.removeEventListener('click', select)
  renderer.domElement.removeEventListener('webglcontextlost', contextLost)
  renderer.dispose()
  renderer.forceContextLoss()
  renderer.domElement.remove()
  renderer = null
}
onMounted(() => {
  preference = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = preference.matches
  preference.addEventListener('change', motionChanged)
  document.addEventListener('visibilitychange', visibilityChanged)
  window.addEventListener('resize', resize)
  try {
    renderer = new WebGLRenderer({ antialias: true })
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = PCFShadowMap
    // Sombra de contato cacheada; não é simulação física do rotor.
    renderer.shadowMap.autoUpdate = false
    renderer.shadowMap.needsUpdate = true
    renderer.domElement.setAttribute('aria-hidden', 'true')
    renderer.domElement.addEventListener('click', select)
    renderer.domElement.addEventListener('webglcontextlost', contextLost)
    host.value!.append(renderer.domElement)
    observer = new ResizeObserver(resize)
    observer.observe(host.value!)
    resize()
  } catch {
    unavailable.value = true
    releaseResources()
  }
})
watch([() => props.items, () => props.selectedId, () => props.visual, paused], update)
function releaseResources() {
  if (disposed) return
  disposed = true
  animating = false
  previousTime = null
  preference?.removeEventListener('change', motionChanged)
  document.removeEventListener('visibilitychange', visibilityChanged)
  window.removeEventListener('resize', resize)
  observer?.disconnect()
  observer = null
  model.dispose()
  floor.geometry.dispose(); floor.material.dispose()
  outline.geometry.dispose()
  for (const material of Array.isArray(outline.material) ? outline.material : [outline.material]) material.dispose()
  thermal.geometry.dispose(); thermal.material.dispose()
  markerGeometry.dispose(); markerMaterial.dispose()
  keyLight.shadow.dispose()
  releaseRenderer()
  markers.clear()
  scene.clear()
}
onUnmounted(releaseResources)

defineExpose({ projected, snapshot: () => ({ animating, paused: paused.value, reducedMotion: reducedMotion.value, hidden: hidden.value, unavailable: unavailable.value, angle: model.rotor.rotation.z, rotorX: model.rotor.position.x }) })
</script>

<template>
  <figure>
    <div class="scene-wrap">
      <div ref="host" class="scene" :class="{ unavailable }" data-testid="twin-scene" />
      <template v-if="selected && !unavailable">
        <svg class="leader" aria-hidden="true"><line :x1="labelPoint.x" :y1="labelPoint.y" x2="24" :y2="labelPoint.height - 34" /></svg>
        <p class="piece-label" aria-hidden="true">{{ selected.label }}</p>
      </template>
    </div>
    <button type="button" :aria-pressed="paused" aria-describedby="twin-animation-reason" :disabled="unavailable" @click="togglePause">{{ paused ? 'Retomar animação' : 'Pausar animação' }}</button>
    <p id="twin-animation-reason" role="status">{{ reason }}</p>
    <figcaption>
      <p v-if="!unavailable">Escolha uma peça ou um marcador. No teclado, use a lista.</p>
      <details>
        <summary>Sobre a cena 3D</summary>
        <p>A câmera é fixa. Posição, giro, tremor e sombra são ilustrativos. A faixa na base representa temperaturas de −20 a 60 °C em uma escala visual.</p>
        <p>Uma leitura recente atualiza a luz e o som de aviso na cena. Uma leitura antiga deixa o estado atual sem confirmação.</p>
      </details>
    </figcaption>
  </figure>
</template>

<style scoped>
figure { margin: 0; min-width: 0; }
.scene-wrap { position: relative; }
.scene { height: clamp(320px, 42vw, 560px); border-radius: var(--cs-radius-8); overflow: hidden; }
.scene :deep(canvas) { display: block; width: 100%; height: 100%; }
.unavailable { display: none; }
.leader { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.leader line { stroke: var(--cs-color-accent); stroke-width: 1; }
.piece-label { position: absolute; left: var(--cs-space-16); bottom: var(--cs-space-16); max-width: calc(100% - 32px); padding: var(--cs-space-8); margin: 0; background: var(--cs-color-surface); color: var(--cs-color-ink); border: 1px solid var(--cs-color-accent); border-radius: var(--cs-radius-4); font-size: var(--cs-type-14); pointer-events: none; }
button { margin-top: var(--cs-space-12); min-height: var(--cs-control-min-height); padding: var(--cs-space-8) var(--cs-space-12); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); color: var(--cs-color-accent); font-size: var(--cs-type-14); font-weight: 600; cursor: pointer; }
button:hover:enabled { background: var(--cs-color-surface-muted); }
button:disabled { color: var(--cs-color-ink-muted); background: var(--cs-color-surface-muted); cursor: not-allowed; }
button:focus-visible { outline: 3px solid var(--cs-focus-ring); outline-offset: 3px; }
#twin-animation-reason, figcaption p { margin-top: var(--cs-space-8); font-size: var(--cs-type-14); line-height: 1.6; }
figcaption { color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
summary { min-height: var(--cs-control-min-height); display: list-item; align-content: center; cursor: pointer; color: var(--cs-color-accent); }
</style>
