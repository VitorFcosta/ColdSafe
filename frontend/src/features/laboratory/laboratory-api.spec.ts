import { afterEach, describe, expect, it, vi } from 'vitest'
import { createGeneration, fetchDataset, fetchJob, fetchSample, isGenerationInput, defaultGeneration, LaboratoryAccessError } from './laboratory-api'

const id = '0d4f2e34-f5c7-4125-8fb0-800b0ebdcf6c'
const config = () => defaultGeneration()
const job = () => ({ id, owner_user_id: id, job_type: 'generation', status: 'queued', completed_units: 0,
  total_units: 1_000_000, result_id: null, error_code: null, environment_id: null, dataset_id: null,
  config: config(), created_at: '2026-10-17T12:00:00Z', updated_at: '2026-10-17T12:00:00Z' })
const envelope = (data: unknown) => ({ success: true, data, meta: { schema_version: 3 } })
function response(data: unknown, status = 200) { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope(data)), { status }))) }
afterEach(() => vi.unstubAllGlobals())

describe('parâmetros do laboratório', () => {
  it('aceita padrão, teto e seed máximo', () => {
    expect(isGenerationInput(config())).toBe(true)
    expect(isGenerationInput({ ...config(), total_units: 2_000_000, seed: 4294967295 })).toBe(true)
  })
  it.each([{ total_units: 999999 }, { total_units: 2000001 }, { total_units: 1.5 }, { seed: -1 },
    { seed: 4294967296 }, { days: 0 }, { days: NaN }, { equipment_count: 10001 }, { missing_rate: 1.1 },
    { outlier_rate: -0.1 }, { noise_scale: Infinity }, { failure_fraction: -1 }, { sensor_types: [] },
    { sensor_types: ['humidity_percent', 'humidity_percent'] }, { failure_modes: ['unknown'] },
    { operating_modes: [] }, { environment_id: 'bad' }])('recusa configuração inválida %j', (patch) => {
    expect(isGenerationInput({ ...config(), ...patch })).toBe(false)
  })
})

describe('fronteira HTTP privada do laboratório', () => {
  it('envia todos parâmetros e autenticação e aceita queued 202', async () => {
    response(job(), 202)
    expect(await createGeneration('private', config())).toEqual(job())
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v3/jobs'), expect.objectContaining({
      method: 'POST', body: JSON.stringify(config()), headers: expect.objectContaining({ authorization: 'Bearer private' }),
    }))
  })
  it('não envia configuração inválida', async () => {
    response(job())
    await expect(createGeneration('token', { ...config(), total_units: 2000001 })).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('valida job persistido e rejeita id divergente, progresso e enum inválidos', async () => {
    response(job()); expect(await fetchJob('token', id)).toEqual(job())
    for (const patch of [{ id: 'bad' }, { status: 'done' }, { completed_units: 1000001 }, { owner_user_id: 'bad' }, { config: {} }, { updated_at: 'yesterday' }]) {
      response({ ...job(), ...patch }); await expect(fetchJob('token', id)).rejects.toThrow()
    }
  })
  it.each([401, 403])('preserva HTTP %s para gestão de sessão', async (status) => {
    response({}, status)
    await expect(fetchJob('token', id)).rejects.toBeInstanceOf(LaboratoryAccessError)
  })
  it('não expõe detalhes internos de erros HTTP', async () => {
    response({ password: 'private diagnostic' }, 503)
    await expect(fetchJob('token', id)).rejects.toThrow('Não foi possível')
  })
  it('valida qualidade, contagem e amostra separada', async () => {
    const sensors = config().sensor_types
    const dataset = { id, owner_user_id: id, generation_job_id: id, created_at: job().created_at,
      row_count: 1000000, config: config(), storage_version: 'offline-numpy-v1',
      units: Object.fromEntries(sensors.map((sensor) => [sensor, 'unit'])), quality: {
        missing_by_sensor: Object.fromEntries(sensors.map((sensor) => [sensor, 10])),
        range_by_sensor: Object.fromEntries(sensors.map((sensor) => [sensor, { min: 0, max: 100 }])),
        rul_observed_rows: 600000, rul_censored_rows: 400000,
      } }
    response(dataset); expect(await fetchDataset('token', id)).toEqual(dataset)
    response({ ...dataset, quality: { ...dataset.quality, rul_censored_rows: 9 } })
    await expect(fetchDataset('token', id)).rejects.toThrow()
    response({ dataset_id: id, rows: [{ equipment_id: id, observed_at: job().created_at,
      measurements: { humidity_percent: null }, degradation_true: 0.1, health_score_true: 0.9,
      rul_hours_true: 12, rul_observed: false }] })
    expect((await fetchSample('token', id)).rows).toHaveLength(1)
    response({ dataset_id: id, rows: Array(11).fill({}) })
    await expect(fetchSample('token', id)).rejects.toThrow()
  })
})
