import { isRecord, isUtcTime, isUuid } from '../monitoring/aiot-api'

export const sensorChoices = [
  ['ambient_temperature_c', 'Temperatura ambiente (°C)'], ['humidity_percent', 'Umidade (%)'],
  ['light_percent', 'Luminosidade (%)'], ['vibration_rms_mm_s', 'Vibração RMS (mm/s)'],
  ['motor_current_a', 'Corrente do motor (A)'], ['motor_temperature_c', 'Temperatura do motor (°C)'],
] as const
export const failureChoices = [['bearing_wear', 'Desgaste do rolamento'], ['imbalance', 'Desbalanceamento']] as const
export const operatingChoices = [['normal', 'Normal'], ['heavy', 'Carga pesada'], ['cycling', 'Cíclico']] as const
export type SensorType = typeof sensorChoices[number][0]
export type GenerationInput = {
  job_type: 'generation'; total_units: number; seed: number; environment_id: string | null
  equipment_count: number; days: number; sensor_types: SensorType[]; failure_fraction: number
  failure_modes: (typeof failureChoices[number][0])[]; operating_modes: (typeof operatingChoices[number][0])[]
  noise_scale: number; missing_rate: number; outlier_rate: number
}
export function defaultGeneration(): GenerationInput {
  return { job_type: 'generation', total_units: 1000000, seed: 42, environment_id: null,
    equipment_count: 100, days: 30, sensor_types: sensorChoices.map(([key]) => key), failure_fraction: 0.6,
    failure_modes: failureChoices.map(([key]) => key), operating_modes: operatingChoices.map(([key]) => key),
    noise_scale: 1, missing_rate: 0.01, outlier_rate: 0.002 }
}
const inRange = (value: unknown, min: number, max: number): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
const integer = (value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is number =>
  inRange(value, min, max) && Number.isSafeInteger(value)
function choices(value: unknown, allowed: readonly string[]): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.length <= allowed.length &&
    value.every((item) => typeof item === 'string' && allowed.includes(item)) && new Set(value).size === value.length
}
export function isGenerationInput(value: unknown): value is GenerationInput {
  return isRecord(value) && value.job_type === 'generation' && integer(value.total_units, 1000000, 2000000) &&
    integer(value.seed, 0, 4294967295) && (value.environment_id === null || isUuid(value.environment_id)) &&
    integer(value.equipment_count, 1, 10000) && inRange(value.days, Number.MIN_VALUE, 3650) &&
    choices(value.sensor_types, sensorChoices.map(([key]) => key)) && inRange(value.failure_fraction, 0, 1) &&
    choices(value.failure_modes, failureChoices.map(([key]) => key)) &&
    choices(value.operating_modes, operatingChoices.map(([key]) => key)) && inRange(value.noise_scale, 0, 10) &&
    inRange(value.missing_rate, 0, 1) && inRange(value.outlier_rate, 0, 1)
}
export type GenerationJob = {
  id: string; owner_user_id: string; job_type: 'generation'
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  completed_units: number; total_units: number; result_id: string | null; error_code: string | null
  environment_id: string | null; dataset_id: string | null; config: GenerationInput
  created_at: string; updated_at: string
}
export type Dataset = {
  id: string; owner_user_id: string; generation_job_id: string; created_at: string
  row_count: number; config: GenerationInput; storage_version: 'offline-numpy-v1'; units: Record<string, string>
  quality: { missing_by_sensor: Record<string, number>; range_by_sensor: Record<string, { min: number | null; max: number | null }>
    rul_observed_rows: number; rul_censored_rows: number }
}
export type DatasetSample = { dataset_id: string; rows: {
  equipment_id: string; observed_at: string; measurements: Record<string, number | null>
  degradation_true: number; health_score_true: number; rul_hours_true: number | null; rul_observed: boolean
}[] }
export class LaboratoryAccessError extends Error {
  constructor(readonly status: 401 | 403) { super('Acesso ao laboratório indisponível.') }
}
export class LaboratoryRequestError extends Error {
  constructor(readonly status: number) { super('Não foi possível consultar o laboratório.') }
}
const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const optionalUuid = (value: unknown) => value === null || isUuid(value)
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 255
function isJob(value: unknown): value is GenerationJob {
  return isRecord(value) && isUuid(value.id) && isUuid(value.owner_user_id) && value.job_type === 'generation' &&
    typeof value.status === 'string' && ['queued', 'running', 'completed', 'failed', 'cancelled'].includes(value.status) &&
    integer(value.total_units, 1000000, 2000000) && integer(value.completed_units, 0, value.total_units) &&
    optionalUuid(value.result_id) && (value.error_code === null || text(value.error_code)) &&
    optionalUuid(value.environment_id) && optionalUuid(value.dataset_id) && isGenerationInput(value.config) &&
    value.config.total_units === value.total_units && isUtcTime(value.created_at) && isUtcTime(value.updated_at) &&
    (value.status !== 'completed' || (isUuid(value.result_id) && value.completed_units === value.total_units))
}
function sameKeys(value: Record<string, unknown>, sensors: readonly string[]) {
  return Object.keys(value).length === sensors.length && sensors.every((sensor) => Object.hasOwn(value, sensor))
}
function isDataset(value: unknown): value is Dataset {
  if (!isRecord(value) || !isUuid(value.id) || !isUuid(value.owner_user_id) || !isUuid(value.generation_job_id) ||
    !isUtcTime(value.created_at) || !isGenerationInput(value.config) ||
    !integer(value.row_count, 1000000, 2000000) || value.row_count !== value.config.total_units ||
    value.storage_version !== 'offline-numpy-v1' || !isRecord(value.units) || !isRecord(value.quality)) return false
  const { sensor_types } = value.config
  const quality = value.quality
  return sameKeys(value.units, sensor_types) && Object.values(value.units).every(text) &&
    isRecord(quality.missing_by_sensor) && sameKeys(quality.missing_by_sensor, sensor_types) &&
    Object.values(quality.missing_by_sensor).every((count) => integer(count, 0, value.row_count as number)) &&
    isRecord(quality.range_by_sensor) && sameKeys(quality.range_by_sensor, sensor_types) &&
    Object.values(quality.range_by_sensor).every((range) => isRecord(range) &&
      ((range.min === null && range.max === null) || (finite(range.min) && finite(range.max) && range.min <= range.max))) &&
    integer(quality.rul_observed_rows, 0, value.row_count) && integer(quality.rul_censored_rows, 0, value.row_count) &&
    quality.rul_observed_rows + quality.rul_censored_rows === value.row_count
}
function isSample(value: unknown): value is DatasetSample {
  return isRecord(value) && isUuid(value.dataset_id) && Array.isArray(value.rows) && value.rows.length <= 10 &&
    value.rows.every((row) => isRecord(row) && isUuid(row.equipment_id) && isUtcTime(row.observed_at) &&
      isRecord(row.measurements) && choices(Object.keys(row.measurements), sensorChoices.map(([key]) => key)) &&
      Object.values(row.measurements).every((number) => number === null || finite(number)) &&
      inRange(row.degradation_true, 0, 1) && inRange(row.health_score_true, 0, 100) &&
      (row.rul_hours_true === null || inRange(row.rul_hours_true, 0, Number.MAX_VALUE)) && typeof row.rul_observed === 'boolean')
}
async function request<T>(token: string, path: string, validate: (value: unknown) => value is T,
  signal?: AbortSignal, body?: GenerationInput): Promise<T> {
  const response = await fetch(`${baseUrl}/api/v3${path}`, {
    signal, method: body ? 'POST' : 'GET', cache: 'no-store',
    headers: { accept: 'application/json', authorization: `Bearer ${token}`, ...(body ? { 'content-type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  if (response.status === 401 || response.status === 403) throw new LaboratoryAccessError(response.status)
  if (!response.ok || (body && response.status !== 202)) throw new LaboratoryRequestError(response.status)
  const payload: unknown = await response.json()
  if (!isRecord(payload) || payload.success !== true || !isRecord(payload.meta) || payload.meta.schema_version !== 3 || !validate(payload.data)) {
    throw new Error('Resposta inválida da API do laboratório.')
  }
  return payload.data
}
export function createGeneration(token: string, config: GenerationInput, signal?: AbortSignal): Promise<GenerationJob> {
  if (!isGenerationInput(config)) return Promise.reject(new Error('Parâmetros de geração inválidos.'))
  return request(token, '/jobs', isJob, signal, config)
}
export async function fetchJob(token: string, id: string, signal?: AbortSignal): Promise<GenerationJob> {
  if (!isUuid(id)) throw new Error('Identificador do job inválido.')
  const result = await request(token, `/jobs/${id}`, isJob, signal)
  if (result.id !== id) throw new Error('Job divergente da consulta.')
  return result
}
export async function fetchDataset(token: string, id: string, signal?: AbortSignal): Promise<Dataset> {
  if (!isUuid(id)) throw new Error('Identificador do dataset inválido.')
  const result = await request(token, `/datasets/${id}`, isDataset, signal)
  if (result.id !== id) throw new Error('Dataset divergente da consulta.')
  return result
}
export async function fetchSample(token: string, id: string, signal?: AbortSignal): Promise<DatasetSample> {
  if (!isUuid(id)) throw new Error('Identificador do dataset inválido.')
  const result = await request(token, `/datasets/${id}/sample`, isSample, signal)
  if (result.dataset_id !== id) throw new Error('Amostra divergente da consulta.')
  return result
}
