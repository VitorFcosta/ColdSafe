import { Box3, Group, Mesh, MeshStandardMaterial, Vector3 } from 'three'
import { describe, expect, it, vi } from 'vitest'
import { createFanModel } from './fan-model'

const keys = ['fan', 'temperature_c', 'humidity_percent', 'light_percent', 'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c', 'led', 'buzzer']

describe('geometria própria candidata RD-02', () => {
  it('expõe nove raízes e âncoras com volume 3D e orçamento geométrico limitado', () => {
    const model = createFanModel()
    expect(model.root).toBeInstanceOf(Group)
    expect([...model.items.keys()].sort()).toEqual([...keys].sort())
    expect([...model.anchors.keys()].sort()).toEqual([...keys].sort())
    for (const [key, item] of model.items) {
      expect(item.parent === model.root || key === 'fan').toBe(true)
      expect(model.anchors.get(key)).toBeInstanceOf(Vector3)
      expect(new Box3().setFromObject(item).isEmpty()).toBe(false)
    }
    const size = new Box3().setFromObject(model.root).getSize(new Vector3())
    expect(size.x).toBeGreaterThan(4)
    expect(size.y).toBeGreaterThan(4)
    expect(size.z).toBeGreaterThan(2)
    let triangles = 0, calls = 0
    model.root.traverse((object) => {
      if (object instanceof Mesh) {
        triangles += (object.geometry.index?.count ?? object.geometry.attributes.position.count) / 3
        calls += Array.isArray(object.material) ? object.material.length : 1
      }
    })
    expect(triangles).toBeLessThanOrEqual(50_000)
    expect(calls).toBeLessThanOrEqual(100)
    model.dispose()
  })

  it('separa hélices do motor, grade e base e mantém materiais de itens independentes', () => {
    const model = createFanModel()
    const fan = model.items.get('fan')!
    const fixed = ['guard', 'motor', 'base'].map((name) => fan.getObjectByName(name)!)
    expect(fixed.every(Boolean)).toBe(true)
    expect(model.rotor.parent).toBe(fan)
    expect(model.rotor.getObjectByName('blades')).toBeDefined()
    const before = fixed.map((part) => part.getWorldPosition(new Vector3()))
    model.rotor.rotation.z = Math.PI / 2
    model.root.updateMatrixWorld(true)
    fixed.forEach((part, index) => expect(part.getWorldPosition(new Vector3())).toEqual(before[index]))
    const owners = new Map<MeshStandardMaterial, string>()
    for (const [key, item] of model.items) {
      item.traverse((object) => {
        if (object instanceof Mesh) {
          for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
            expect(material).toBeInstanceOf(MeshStandardMaterial)
            expect(owners.get(material) ?? key).toBe(key)
            owners.set(material, key)
          }
        }
      })
    }
    model.dispose()
  })

  it('descarta todos os recursos próprios uma única vez, mesmo ao repetir limpeza', () => {
    const model = createFanModel()
    const resources = new Set<{ dispose: () => void }>()
    model.root.traverse((object) => {
      if (object instanceof Mesh) {
        resources.add(object.geometry)
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) resources.add(material)
      }
    })
    const disposals = [...resources].map((resource) => vi.spyOn(resource, 'dispose'))
    model.dispose()
    model.dispose()
    disposals.forEach((dispose) => expect(dispose).toHaveBeenCalledOnce())
    expect(model.root.children).toHaveLength(0)
  })
})
