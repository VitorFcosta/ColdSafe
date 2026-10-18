import { isRecord, isUtcTime, isUuid } from '../monitoring/aiot-api'

export type Metrics = { mae: number; rmse: number; r2: number | null }
export type Comparison = { baseline: Metrics; candidate: Metrics }
export type PartitionRows = { train: number; validation: number; test: number }
export type Diagnostics = {
  partition: 'test'; total_rows: number; sample_count: number; sample_seed: number; sample_max: 500
  sampling: 'seeded_without_replacement'; scatter: { actual: number; predicted: number; baseline: number; error: number }[]
  permutation: { scoring: 'mae_increase'; repeats: 3; sample_count: number; reference_mae: number; features: { name: string; mean: number; std: number }[] }
}
export type TargetResult = {
  target: 'health_score_true' | 'rul_hours_true'; unit: 'points' | 'hours'; status: 'eligible' | 'rejected'
  metrics: { validation: Comparison; test: Comparison }; partition_rows: PartitionRows; diagnostics: Diagnostics
  near_failure: null | { threshold_hours: 24; validation: { row_count: number; baseline: Metrics | null; candidate: Metrics | null }; test: { row_count: number; baseline: Metrics | null; candidate: Metrics | null } }
}
export type TrainingResult = {
  job_id: string; dataset_id: string; model_id: string; model_version: string; eligible: boolean; features_version: string
  seed: number; split_seed: number; equipment_counts: PartitionRows; versions: Record<string, string>
  health: TargetResult; rul: TargetResult; limitations: string[]
}
export type DatasetChoice = { id: string; name: string; row_count: number; created_at: string; generation_job_id: string }
export type TrainingJob = {
  id: string; owner_user_id: string; job_type: 'training'; status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  completed_units: number; total_units: number; result_id: string | null; error_code: string | null
  environment_id: string | null; dataset_id: string; config: { job_type: 'training'; dataset_id: string; environment_id: string | null }
  created_at: string; updated_at: string
}
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const integer = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): v is number => finite(v) && Number.isSafeInteger(v) && v >= min && v <= max
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 1000
const optionalUuid = (v: unknown) => v === null || isUuid(v)
const metrics = (v: unknown): v is Metrics => isRecord(v) && finite(v.mae) && v.mae >= 0 && finite(v.rmse) && v.rmse >= 0 && (v.r2 === null || (finite(v.r2) && v.r2 <= 1))
const comparison = (v: unknown): v is Comparison => isRecord(v) && metrics(v.baseline) && metrics(v.candidate)
const partitions = (v: unknown): v is PartitionRows => isRecord(v) && integer(v.train, 1) && integer(v.validation, 1) && integer(v.test, 1)
function diagnostics(v: unknown): v is Diagnostics {
  if (!isRecord(v) || v.partition !== 'test' || !integer(v.total_rows, 1) || !integer(v.sample_count, 1, 500) || v.sample_count > v.total_rows ||
    !integer(v.sample_seed, 0, 4294967295) || v.sample_max !== 500 || v.sampling !== 'seeded_without_replacement' ||
    !Array.isArray(v.scatter) || v.scatter.length !== v.sample_count || !v.scatter.every((p) => isRecord(p) &&
      finite(p.actual) && finite(p.predicted) && finite(p.baseline) && finite(p.error) && Math.abs(p.error - (p.predicted - p.actual)) <= 1e-8 * Math.max(1, Math.abs(p.error)))) return false
  const p = v.permutation
  return isRecord(p) && p.scoring === 'mae_increase' && p.repeats === 3 && p.sample_count === v.sample_count && finite(p.reference_mae) && p.reference_mae >= 0 &&
    Array.isArray(p.features) && p.features.length > 0 && p.features.length <= 1000 && p.features.every((f) => isRecord(f) && text(f.name) && finite(f.mean) && finite(f.std) && f.std >= 0) &&
    new Set(p.features.map((f) => (f as Record<string, unknown>).name)).size === p.features.length
}
function nearPartition(v: unknown) {
  return isRecord(v) && integer(v.row_count) && (v.row_count === 0 ? v.baseline === null && v.candidate === null : metrics(v.baseline) && metrics(v.candidate))
}
function target(v: unknown, name: TargetResult['target'], unit: TargetResult['unit']): v is TargetResult {
  if (!isRecord(v) || v.target !== name || v.unit !== unit || !['eligible', 'rejected'].includes(String(v.status)) || !isRecord(v.metrics) ||
    !comparison(v.metrics.validation) || !comparison(v.metrics.test) || !partitions(v.partition_rows) || !diagnostics(v.diagnostics) || v.diagnostics.total_rows !== v.partition_rows.test) return false
  if ((v.metrics.validation.candidate.mae < v.metrics.validation.baseline.mae) !== (v.status === 'eligible')) return false
  if (v.diagnostics.scatter.some((p) => Math.min(p.actual, p.predicted, p.baseline) < 0 || (unit === 'points' && Math.max(p.actual, p.predicted, p.baseline) > 100))) return false
  return name === 'health_score_true' ? v.near_failure === null : isRecord(v.near_failure) && v.near_failure.threshold_hours === 24 && nearPartition(v.near_failure.validation) && nearPartition(v.near_failure.test)
}
export function isTrainingResult(v: unknown): v is TrainingResult {
  return isRecord(v) && isUuid(v.job_id) && isUuid(v.dataset_id) && isUuid(v.model_id) && text(v.model_version) && text(v.features_version) &&
    typeof v.eligible === 'boolean' && integer(v.seed, 0, 4294967295) && integer(v.split_seed, 0, 4294967295) && partitions(v.equipment_counts) &&
    isRecord(v.versions) && Object.keys(v.versions).length > 0 && Object.values(v.versions).every(text) && target(v.health, 'health_score_true', 'points') && target(v.rul, 'rul_hours_true', 'hours') &&
    v.eligible === (v.health.status === 'eligible' && v.rul.status === 'eligible') && Array.isArray(v.limitations) && v.limitations.length <= 100 && v.limitations.every(text)
}
function isTrainingJob(v: unknown): v is TrainingJob {
  return isRecord(v) && isUuid(v.id) && isUuid(v.owner_user_id) && v.job_type === 'training' && ['queued', 'running', 'completed', 'failed', 'cancelled'].includes(String(v.status)) &&
    integer(v.total_units, 1) && integer(v.completed_units, 0, v.total_units) && optionalUuid(v.result_id) && (v.error_code === null || text(v.error_code)) && optionalUuid(v.environment_id) && isUuid(v.dataset_id) &&
    isRecord(v.config) && v.config.job_type === 'training' && v.config.dataset_id === v.dataset_id && v.config.environment_id === v.environment_id && isUtcTime(v.created_at) && isUtcTime(v.updated_at) &&
    (v.status !== 'completed' || (isUuid(v.result_id) && v.completed_units === v.total_units))
}
function datasets(v: unknown): v is DatasetChoice[] {
  return Array.isArray(v) && v.length <= 50 && v.every((d) => isRecord(d) && isUuid(d.id) && text(d.name) && integer(d.row_count, 1000000, 2000000) && isUtcTime(d.created_at) && isUuid(d.generation_job_id)) && new Set(v.map((d) => d.id)).size === v.length
}
export class TrainingAccessError extends Error { constructor(readonly status: 401 | 403) { super('Acesso ao treinamento indisponível.') } }
export class TrainingRequestError extends Error { constructor(readonly status: number) { super('Não foi possível consultar o treinamento.') } }
const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
async function request<T>(token: string, path: string, validate: (v: unknown) => v is T, signal?: AbortSignal, body?: TrainingJob['config']): Promise<T> {
  const response = await fetch(`${baseUrl}/api/v3${path}`, { method: body ? 'POST' : 'GET', signal, cache: 'no-store',
    headers: { accept: 'application/json', authorization: `Bearer ${token}`, ...(body ? { 'content-type': 'application/json' } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
  if (response.status === 401 || response.status === 403) throw new TrainingAccessError(response.status)
  if (!response.ok || (body && response.status !== 202)) throw new TrainingRequestError(response.status)
  const payload: unknown = await response.json()
  if (!isRecord(payload) || payload.success !== true || !isRecord(payload.meta) || payload.meta.schema_version !== 3 || !validate(payload.data)) throw new Error('Resposta inválida da API de treinamento.')
  return payload.data
}
export function fetchDatasets(token: string, signal?: AbortSignal) { return request(token, '/datasets', datasets, signal) }
export async function createTraining(token: string, datasetId: string, signal?: AbortSignal) {
  if (!isUuid(datasetId)) throw new Error('Identificador do dataset inválido.')
  const job = await request(token, '/jobs', isTrainingJob, signal, { job_type: 'training', dataset_id: datasetId, environment_id: null })
  if (job.dataset_id !== datasetId) throw new Error('Dataset divergente do pedido.')
  return job
}
export async function fetchTrainingJob(token: string, id: string, signal?: AbortSignal) {
  if (!isUuid(id)) throw new Error('Identificador do job inválido.')
  const job = await request(token, `/jobs/${id}`, isTrainingJob, signal)
  if (job.id !== id) throw new Error('Job divergente da consulta.')
  return job
}
export async function fetchTrainingResult(token: string, id: string, signal?: AbortSignal) {
  if (!isUuid(id)) throw new Error('Identificador do job inválido.')
  const result = await request(token, `/jobs/${id}/result`, isTrainingResult, signal)
  if (result.job_id !== id) throw new Error('Resultado divergente da consulta.')
  return result
}
