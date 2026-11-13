import { computed, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import { listDevices, listEnvironments, type Device, type Environment } from '../account/catalog'
import { clearMonitoringSelection, monitoringSelection, saveMonitoringSelection, sessionToken, validatedMonitoringSelection } from '../account/session'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const invalidNotice = 'Acesso ao equipamento indisponível: ambiente ou dispositivo inválido, inativo ou indisponível para esta conta. Selecione um ambiente e um dispositivo autorizado.'

export function monitoringLocation(path: string) {
  const pair = validatedMonitoringSelection.value
  return pair && ['/dashboard', '/insights', '/digital-twin'].includes(path)
    ? { path, query: { environment: pair.environmentId, device: pair.deviceUuid } } : { path }
}

export function useMonitoringContext(enabled = true) {
  const route = useRoute(), router = useRouter()
  const environments = ref<Environment[]>([]), devices = ref<Device[]>([])
  const selectedEnvironmentId = ref(''), selectedDeviceUuid = ref('')
  const selectionNotice = ref('')
  const catalogPhase = ref<'loading' | 'ready' | 'error'>('loading')
  const selectedDevice = computed(() => devices.value.find((device) => device.id === selectedDeviceUuid.value &&
    device.environment_id === selectedEnvironmentId.value && device.is_active))
  let revision = 0
  let retryTimer: ReturnType<typeof setTimeout> | undefined

  function reset() {
    selectedDeviceUuid.value = ''
    devices.value = []
    validatedMonitoringSelection.value = null
    clearTimeout(retryTimer)
  }

  async function resolve(query: LocationQuery, chosenEnvironment?: string) {
    const request = ++revision, token = sessionToken.value
    reset()
    selectedEnvironmentId.value = ''
    environments.value = []
    selectionNotice.value = ''
    catalogPhase.value = 'loading'
    if (!token || !enabled) { catalogPhase.value = 'ready'; return }
    const explicit = 'environment' in query || 'device' in query
    const candidate = explicit ? { environmentId: query.environment, deviceUuid: query.device } : monitoringSelection.value
    const validShape = candidate && typeof candidate.environmentId === 'string' && uuid.test(candidate.environmentId) &&
      typeof candidate.deviceUuid === 'string' && uuid.test(candidate.deviceUuid)
    const current = () => request === revision && token === sessionToken.value
    try {
      const catalog = await listEnvironments(token)
      if (!current()) return
      environments.value = catalog
      const environment = chosenEnvironment ?? (candidate ? candidate.environmentId : catalog[0]?.id ?? '')
      if (typeof environment !== 'string' || (candidate && !chosenEnvironment && !uuid.test(environment)) ||
        !catalog.some((item) => item.id === environment)) {
        if (candidate || chosenEnvironment) selectionNotice.value = invalidNotice
        catalogPhase.value = 'ready'
        return
      }
      selectedEnvironmentId.value = environment
      const result = await listDevices(token, environment)
      if (!current()) return
      devices.value = result.filter((device) => device.environment_id === environment && device.is_active)
      const device = candidate && !chosenEnvironment
        ? validShape ? devices.value.find((item) => item.id === candidate.deviceUuid) : undefined : devices.value[0]
      if (device) {
        selectedDeviceUuid.value = device.id
        const pair = { environmentId: environment, deviceUuid: device.id }
        validatedMonitoringSelection.value = pair
        saveMonitoringSelection(pair)
        catalogPhase.value = 'ready'
        const target = { path: route.path, query: { ...route.query, environment, device: device.id }, hash: route.hash }
        if (chosenEnvironment) await router.push(target)
        else if (route.query.environment !== environment || route.query.device !== device.id) await router.replace(target)
      } else {
        if (candidate && !chosenEnvironment) selectionNotice.value = invalidNotice
        catalogPhase.value = 'ready'
        if (chosenEnvironment) {
          clearMonitoringSelection()
          const { device: _device, ...queryWithoutDevice } = route.query
          await router.push({ path: route.path, query: { ...queryWithoutDevice, environment }, hash: route.hash })
        }
      }
    } catch {
      if (!current()) return
      catalogPhase.value = 'error'
      // Preserve the dashboard's transient catalog recovery without adding history entries.
      retryTimer = setTimeout(() => { if (current()) void resolve(query, chosenEnvironment) }, 2000)
    }
  }

  const environmentId = computed({ get: () => selectedEnvironmentId.value,
    set: (id: string) => { void resolve(route.query, id) } })
  const deviceUuid = computed({ get: () => selectedDeviceUuid.value, set: (id: string) => {
    if (!devices.value.some((device) => device.id === id)) return
    void router.push({ path: route.path, query: { ...route.query, environment: selectedEnvironmentId.value, device: id }, hash: route.hash })
  } })
  function revokeSelection() {
    revision += 1
    reset()
    clearMonitoringSelection()
    selectionNotice.value = 'Acesso ao equipamento indisponível. Selecione outro ambiente ou dispositivo autorizado.'
    catalogPhase.value = 'ready'
    const { device: _device, ...queryWithoutDevice } = route.query
    return router.replace({ path: route.path, query: queryWithoutDevice, hash: route.hash })
  }
  watch([sessionToken, () => route.query.environment, () => route.query.device], ([token], [oldToken]) => {
    if (token === oldToken && catalogPhase.value === 'ready' && selectedDevice.value && route.query.environment === selectedEnvironmentId.value &&
      route.query.device === selectedDeviceUuid.value) return
    void resolve(route.query)
  }, { immediate: true, flush: 'sync' })
  onScopeDispose(() => { revision += 1; reset() })
  return { environments, devices, environmentId, deviceUuid, selectedDevice, selectionNotice, catalogPhase,
    catalogLoading: computed(() => catalogPhase.value === 'loading'), catalogFailed: computed(() => catalogPhase.value === 'error'),
    loadEnvironments: () => resolve(route.query), monitoringLocation, revokeSelection }
}
