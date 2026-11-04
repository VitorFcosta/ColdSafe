import {
  BoxGeometry, BufferGeometry, CatmullRomCurve3, CylinderGeometry, ExtrudeGeometry,
  Group, Mesh, MeshStandardMaterial, Shape, TorusGeometry, TubeGeometry, Vector3,
  type Object3D,
} from 'three'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'

export function createFanModel() {
  const root = new Group()
  root.name = 'fan-model'
  const fan = new Group()
  fan.name = 'fan'
  root.add(fan)
  const items = new Map<string, Object3D>([['fan', fan]])
  const anchors = new Map<string, Vector3>([['fan', new Vector3(0, 1.25, 0.65)]])
  const graphite = new MeshStandardMaterial({ color: 0x303b3d, roughness: 0.43, metalness: 0.72 })
  const steel = new MeshStandardMaterial({ color: 0x788183, roughness: 0.46, metalness: 0.75 })
  const rubber = new MeshStandardMaterial({ color: 0x20292b, roughness: 0.8, metalness: 0.05 })

  function mesh(parent: Group, name: string, geometry: BufferGeometry, material: MeshStandardMaterial, position: readonly [number, number, number]) {
    const object = new Mesh(geometry, material)
    object.name = name
    object.position.set(...position)
    object.castShadow = true
    object.receiveShadow = true
    parent.add(object)
    return object
  }
  function merged(parts: BufferGeometry[]) {
    const geometry = mergeGeometries(parts)
    parts.forEach((part) => part.dispose())
    if (!geometry) throw new Error('Não foi possível compor a geometria da grade.')
    return geometry
  }

  mesh(fan, 'base', new RoundedBoxGeometry(4.8, 0.18, 2.9, 2, 0.08), steel, [0, -1.25, 0])
  for (const x of [-2.1, 2.1]) {
    for (const z of [-1.15, 1.15]) {
      mesh(fan, 'foot', new CylinderGeometry(0.16, 0.18, 0.22, 12), rubber, [x, -1.45, z])
      mesh(fan, 'base-fastener', new CylinderGeometry(0.055, 0.055, 0.035, 10), steel, [x, -1.14, z])
    }
  }
  mesh(fan, 'mount', new RoundedBoxGeometry(1.85, 0.13, 1.35, 2, 0.04), graphite, [0, -1.09, -0.2])
  const stand = mesh(fan, 'stand', new BoxGeometry(0.32, 1.65, 0.58), graphite, [0, -0.25, -0.5])
  stand.rotation.x = -0.18
  const motor = mesh(fan, 'motor', new CylinderGeometry(0.75, 0.75, 1.15, 48), graphite, [0, 1.25, -0.72])
  motor.rotation.x = Math.PI / 2
  const fins: BufferGeometry[] = []
  for (let index = 0; index < 7; index++) {
    fins.push(new TorusGeometry(0.765, 0.025, 5, 48).translate(0, 1.25, -1.2 + index * 0.16))
  }
  mesh(fan, 'motor-fins', merged(fins), graphite, [0, 0, 0])

  const rotor = new Group()
  rotor.name = 'rotor'
  rotor.position.set(0, 1.25, 0.08)
  fan.add(rotor)
  const blades = new Group()
  blades.name = 'blades'
  rotor.add(blades)
  const blade = new Shape()
  blade.moveTo(-0.10, 0.27)
  blade.bezierCurveTo(-0.30, 0.62, -0.83, 0.85, -0.64, 1.24)
  blade.bezierCurveTo(-0.50, 1.54, 0.20, 1.48, 0.44, 1.18)
  blade.bezierCurveTo(0.59, 0.92, 0.26, 0.48, 0.16, 0.27)
  blade.closePath()
  const bladeGeometry = new ExtrudeGeometry(blade, { depth: 0.045, bevelEnabled: true, bevelSegments: 2, steps: 1, bevelSize: 0.025, bevelThickness: 0.02, curveSegments: 10 })
  for (let index = 0; index < 4; index++) {
    const part = mesh(blades, `blade-${index + 1}`, bladeGeometry, graphite, [0, 0, 0])
    part.rotation.z = index * Math.PI / 2
  }
  const hub = mesh(rotor, 'hub', new CylinderGeometry(0.33, 0.36, 0.24, 40), graphite, [0, 0, 0.13])
  hub.rotation.x = Math.PI / 2

  const wires: BufferGeometry[] = []
  for (const z of [-0.32, 0.02]) wires.push(new TorusGeometry(1.64, 0.045, 6, 96).translate(0, 0, z))
  for (let index = 0; index < 7; index++) {
    const radius = 0.44 + index * 0.19
    const z = 0.48 * (1 - (radius / 1.65) ** 2)
    wires.push(new TorusGeometry(radius, 0.014, 5, 96).translate(0, 0, z))
  }
  for (let index = 0; index < 40; index++) {
    const angle = index * Math.PI * 2 / 40
    const points = [0.30, 0.7, 1.15, 1.64].map((radius) => new Vector3(
      Math.cos(angle) * radius, Math.sin(angle) * radius, 0.48 * (1 - (radius / 1.65) ** 2),
    ))
    wires.push(new TubeGeometry(new CatmullRomCurve3(points), 10, 0.013, 5, false))
  }
  mesh(fan, 'guard', merged(wires), graphite, [0, 1.25, 0.18])
  for (let index = 0; index < 4; index++) {
    const angle = Math.PI / 4 + index * Math.PI / 2
    mesh(fan, 'guard-clip', new RoundedBoxGeometry(0.10, 0.10, 0.45, 1, 0.02), steel,
      [Math.cos(angle) * 1.64, 1.25 + Math.sin(angle) * 1.64, 0.03])
  }

  const sensors = [
    ['temperature_c', -2.02, -0.52, 0.55], ['humidity_percent', -1.42, -0.91, 1.04],
    ['light_percent', -2.00, -0.63, -0.82], ['vibration_rms_mm_s', 0.95, -0.91, 0.86],
    ['motor_current_a', 1.98, -0.53, -0.68], ['motor_temperature_c', 0.86, 1.30, -0.70],
  ] as const
  for (const [key, x, y, z] of sensors) {
    const sensor = new Group()
    sensor.name = key
    sensor.position.set(x, y, z)
    root.add(sensor)
    const housing = new MeshStandardMaterial({ color: key === 'motor_temperature_c' ? 0x2d6868 : 0x8d9695, roughness: 0.5, metalness: 0.5 })
    mesh(sensor, 'housing', new RoundedBoxGeometry(0.42, 0.43, 0.30, 2, 0.045), housing, [0, 0, 0])
    mesh(sensor, 'sensor-face', new CylinderGeometry(0.105, 0.105, 0.025, 20), housing, [0.22, 0, 0]).rotation.z = Math.PI / 2
    if (y < 0) mesh(sensor, 'sensor-mount', new CylinderGeometry(0.065, 0.065, Math.max(0.08, y + 0.95), 10), housing, [0, -(y + 1.375) / 2, 0])
    items.set(key, sensor)
    anchors.set(key, new Vector3(x, y + 0.25, z + 0.12))
  }

  const led = new Group()
  led.name = 'led'
  led.position.set(1.78, -1.04, 1.05)
  const ledBase = new MeshStandardMaterial({ color: 0x3e4546, roughness: 0.6, metalness: 0.3 })
  const lens = new MeshStandardMaterial({ color: 0xffce55, roughness: 0.3, metalness: 0.12, emissive: 0xffbe36, emissiveIntensity: 0 })
  mesh(led, 'led-base', new CylinderGeometry(0.14, 0.15, 0.1, 20), ledBase, [0, 0, 0])
  mesh(led, 'led-lens', new CylinderGeometry(0.095, 0.095, 0.26, 24), lens, [0, 0.16, 0])
  root.add(led)
  items.set('led', led)
  anchors.set('led', new Vector3(1.78, -0.70, 1.05))
  const buzzer = new Group()
  buzzer.name = 'buzzer'
  buzzer.position.set(2.03, -1.00, 0.13)
  const buzzerMaterial = new MeshStandardMaterial({ color: 0x272d2e, roughness: 0.5, metalness: 0.25 })
  mesh(buzzer, 'buzzer-body', new CylinderGeometry(0.25, 0.25, 0.31, 28), buzzerMaterial, [0, 0, 0])
  mesh(buzzer, 'buzzer-opening', new CylinderGeometry(0.055, 0.055, 0.012, 12), buzzerMaterial, [0, 0.16, 0])
  root.add(buzzer)
  items.set('buzzer', buzzer)
  anchors.set('buzzer', new Vector3(2.03, -0.71, 0.13))

  let disposed = false
  function dispose() {
    if (disposed) return
    disposed = true
    const geometries = new Set<BufferGeometry>()
    const materials = new Set<MeshStandardMaterial>()
    root.traverse((object) => {
      if (object instanceof Mesh) {
        geometries.add(object.geometry)
        materials.add(object.material)
      }
    })
    geometries.forEach((geometry) => geometry.dispose())
    materials.forEach((material) => material.dispose())
    root.clear()
    items.clear()
    anchors.clear()
  }
  return { root, rotor, items, anchors, dispose }
}
