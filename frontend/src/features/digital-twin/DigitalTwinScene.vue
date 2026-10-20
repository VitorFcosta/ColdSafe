<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { AmbientLight, BoxGeometry, Color, CylinderGeometry, DirectionalLight, Group, Mesh, MeshStandardMaterial, OrthographicCamera, Raycaster, Scene, SphereGeometry, Vector2, WebGLRenderer, type Object3D } from 'three'
import { twinColors, type TwinItem, type TwinVisualState } from './twin-state'

const props = defineProps<{ items: readonly TwinItem[]; selectedId: string | null; visual: TwinVisualState | null }>()
const emit = defineEmits<{ select: [id: string] }>()
const host = ref<HTMLElement | null>(null)
const unavailable = ref(false)
const reducedMotion = ref(false)
const scene = new Scene()
scene.background = new Color(0xe9efed)
const camera = new OrthographicCamera(-5, 5, 3.2, -3.2, 0.1, 50)
camera.position.set(0, 0, 12)
const light = new DirectionalLight(0xffffff, 3)
light.position.set(-3, 5, 8)
const ambient = new AmbientLight(0xffffff, 2)
const thermal = new Mesh(new BoxGeometry(2, 0.16, 0.2), new MeshStandardMaterial({ color: twinColors.no_data }))
thermal.name = 'thermal-marker'
thermal.position.set(0, 2.65, 0)
scene.add(ambient, light, thermal)
let renderer: WebGLRenderer | null = null
let observer: ResizeObserver | null = null
const objects = new Map<string, Mesh | Group>()
const raycaster = new Raycaster()
let motionPreference: MediaQueryList | null = null
let animating = false
let previousTime: number | null = null
let elapsed = 0

function animate(time: number) {
  const visual = props.visual
  if (!animating || !visual) return
  const delta = previousTime === null ? 0 : Math.min(Math.max(0, time - previousTime) / 1000, 0.1)
  previousTime = time
  elapsed += delta
  const fan = objects.get('fan')
  if (fan) {
    if (visual.running) fan.rotation.z = (fan.rotation.z + delta * 4) % (Math.PI * 2)
    const base = props.items.find((item) => item.key === 'fan')!
    // shortcut: illustrative gain capped at 10 mm/s, replace after physical calibration.
    fan.position.x = base.position[0] + Math.sin(elapsed * 24) * Math.min(visual.vibration ?? 0, 10) * 0.012
  }
  const buzzer = objects.get('buzzer')
  if (buzzer instanceof Mesh && buzzer.material instanceof MeshStandardMaterial && visual.buzzer) {
    buzzer.material.emissiveIntensity = 0.7 + 0.3 * Math.sin(elapsed * Math.PI * 2)
  }
  render()
}
function syncAnimation() {
  const visual = props.visual
  const shouldAnimate = Boolean(renderer && !unavailable.value && !reducedMotion.value && !document.hidden && visual &&
    (visual.running || (visual.vibration ?? 0) > 0 || visual.buzzer))
  if (shouldAnimate === animating) return
  animating = shouldAnimate
  previousTime = null
  renderer?.setAnimationLoop(animating ? animate : null)
}
function motionChanged(event: MediaQueryListEvent) {
  reducedMotion.value = event.matches
  update()
}

function render() {
  if (renderer && !unavailable.value) renderer.render(scene, camera)
}
function resize() {
  const width = host.value?.clientWidth || 640
  const height = host.value?.clientHeight || 400
  const halfWidth = Math.max(5, 3.2 * width / height)
  camera.left = -halfWidth; camera.right = halfWidth
  camera.updateProjectionMatrix()
  renderer?.setSize(width, height)
  render()
}
function createObject(item: TwinItem): Mesh | Group {
  const material = new MeshStandardMaterial({ color: twinColors[item.status], roughness: 0.55, metalness: 0.15 })
  if (item.kind === 'equipment') {
    const fan = new Group()
    const hub = new Mesh(new CylinderGeometry(0.75, 0.75, 0.5, 32), material)
    hub.rotation.x = Math.PI / 2
    fan.add(hub)
    for (let index = 0; index < 4; index++) {
      const blade = new Mesh(new BoxGeometry(0.45, 1.25, 0.18), material)
      const angle = index * Math.PI / 2
      blade.position.set(Math.sin(angle) * 0.9, Math.cos(angle) * 0.9, 0.35)
      blade.rotation.z = -angle + 0.25
      fan.add(blade)
    }
    return fan
  }
  return new Mesh(item.kind === 'sensor' ? new BoxGeometry(0.8, 0.65, 0.45) : new SphereGeometry(0.32, 20, 12), material)
}
function update() {
  if (!renderer) return
  for (const item of props.items) {
    let object = objects.get(item.key)
    if (!object) {
      object = createObject(item)
      objects.set(item.key, object)
      scene.add(object)
      object.position.set(...item.position)
    }
    object.userData = { id: item.id, key: item.key }
    const selected = item.id !== null && item.id === props.selectedId
    object.scale.setScalar(selected ? 1.14 : 1)
    object.traverse((part) => {
      if (part instanceof Mesh) {
        part.material.color.setHex(twinColors[item.status])
        part.material.emissive.setHex(selected ? 0x294b63 : 0x000000)
        part.material.emissiveIntensity = 1
        if (item.key === 'led' || item.key === 'buzzer') {
          const on = props.visual?.[item.key] === true
          part.material.emissive.setHex(on ? item.key === 'led' ? 0xffd65c : 0xc3353c : selected ? 0x294b63 : 0x000000)
          part.material.emissiveIntensity = on ? 0.7 : 0
        }
      }
    })
  }
  if (props.visual) {
    ambient.intensity = props.visual.light === null ? 2 : 0.5 + props.visual.light / 100 * 2.5
    // shortcut: illustrative blue→red scale (-20…60 °C), not an operational risk threshold.
    thermal.material.color.setHSL((1 - Math.max(0, Math.min(1, (props.visual.temperature + 20) / 80))) * 0.65, 0.8, 0.45)
    if (reducedMotion.value || !props.visual.vibration) {
      const fan = objects.get('fan')
      const base = props.items.find((item) => item.key === 'fan')
      if (fan && base) fan.position.set(...base.position)
    }
  }
  syncAnimation()
  render()
}
function select(event: MouseEvent) {
  if (!renderer || unavailable.value) return
  const bounds = renderer.domElement.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return
  raycaster.setFromCamera(new Vector2((event.clientX - bounds.left) / bounds.width * 2 - 1, -(event.clientY - bounds.top) / bounds.height * 2 + 1), camera)
  let object: Object3D | undefined = raycaster.intersectObjects([...objects.values()], true)[0]?.object
  while (object && !object.userData.key) object = object.parent ?? undefined
  if (typeof object?.userData.id === 'string') emit('select', object.userData.id)
}
function contextLost(event: Event) {
  event.preventDefault()
  unavailable.value = true
  syncAnimation()
}
onMounted(() => {
  motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = motionPreference.matches
  motionPreference.addEventListener('change', motionChanged)
  document.addEventListener('visibilitychange', syncAnimation)
  try {
    renderer = new WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.domElement.setAttribute('aria-hidden', 'true')
    renderer.domElement.addEventListener('click', select)
    renderer.domElement.addEventListener('webglcontextlost', contextLost)
    host.value!.append(renderer.domElement)
    observer = new ResizeObserver(resize)
    observer.observe(host.value!)
    update()
    resize()
  } catch {
    unavailable.value = true
    syncAnimation()
  }
})
watch([() => props.items, () => props.selectedId, () => props.visual], update)
onUnmounted(() => {
  animating = false
  renderer?.setAnimationLoop(null)
  motionPreference?.removeEventListener('change', motionChanged)
  document.removeEventListener('visibilitychange', syncAnimation)
  observer?.disconnect()
  const materials = new Set<MeshStandardMaterial>()
  scene.traverse((object) => {
    if (object instanceof Mesh) { object.geometry.dispose(); materials.add(object.material) }
  })
  materials.forEach((material) => material.dispose())
  if (renderer) {
    renderer.domElement.removeEventListener('click', select)
    renderer.domElement.removeEventListener('webglcontextlost', contextLost)
    renderer.dispose()
    renderer.forceContextLoss()
    renderer.domElement.remove()
  }
  objects.clear()
  scene.clear()
})
</script>

<template>
  <figure>
    <div ref="host" class="scene" :class="{ unavailable }" data-testid="twin-scene" />
    <p v-if="unavailable" role="status">3D indisponível neste navegador. Use a lista de itens abaixo; reabra a página para tentar novamente.</p>
    <p v-if="!visual" role="status">Cena congelada: sem telemetria atual confirmada. Movimento suspenso; aparência ambiental preservada da última leitura, quando houver.</p>
    <p v-if="reducedMotion" role="status">Movimento reduzido: giro, tremor e pulso suspensos conforme sua preferência. Valores e estados continuam atualizando.</p>
    <figcaption>Ventilador ao centro; seis sensores nas laterais; LED e buzzer abaixo. Iluminação segue a luminosidade (%); barra superior varia de azul a vermelho com a temperatura ambiente (escala ilustrativa de −20 a 60 °C). LED brilha quando ligado; buzzer ligado pulsa suavemente, sem som. Clique em uma peça ou use a lista. Geometria, giro e tremor ilustrativos, sem escala ou calibração física.</figcaption>
  </figure>
</template>

<style scoped>
figure { margin: 0; min-width: 0; }
.scene { width: 100%; height: clamp(240px, 42vw, 420px); border-radius: 12px; overflow: hidden; }
.scene :deep(canvas) { display: block; width: 100%; height: 100%; }
.unavailable { display: none; }
figcaption { margin-top: 12px; line-height: 1.5; }
</style>
