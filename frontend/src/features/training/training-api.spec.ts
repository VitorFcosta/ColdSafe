import { afterEach, describe, expect, it, vi } from 'vitest'
import { createTraining, fetchTrainingJob, fetchTrainingResult, fetchDatasets, isTrainingResult } from './training-api'
import fixture from './training.fixture.json'
const id = fixture.job_id
const job = () => ({ id, owner_user_id: id, job_type: 'training', status: 'queued', completed_units: 0, total_units: 2,
  result_id: null, dataset_id: fixture.dataset_id, environment_id: null, error_code: null,
  config: { job_type: 'training', dataset_id: fixture.dataset_id, environment_id: null }, created_at: '2026-10-17T12:00:00Z', updated_at: '2026-10-17T12:00:00Z' })
function respond(data: unknown, status = 200) { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data, meta: { schema_version: 3 } }), { status }))) }
afterEach(() => vi.unstubAllGlobals())
describe('contrato de treinamento', () => {
  it('aceita R² e importância negativos e valores de regressão', () => { expect(isTrainingResult(fixture)).toBe(true) })
  it('recusa unidade trocada, amostras excessivas e números não finitos', () => {
    for (const patch of [{ unit: 'hours' }, { metrics: { validation: { baseline: { mae: NaN, rmse: 2, r2: -1 }, candidate: {} } } },
      { diagnostics: { ...fixture.health.diagnostics, scatter: Array(501).fill(fixture.health.diagnostics.scatter[0]) } }]) {
      expect(isTrainingResult({ ...fixture, health: { ...fixture.health, ...patch } })).toBe(false)
    }
    expect(isTrainingResult({ ...fixture, eligible: true })).toBe(false)
  })
  it('envia POST uma vez com bearer e config mínima', async () => {
    respond(job(), 202); await createTraining('private', fixture.dataset_id)
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v3/jobs'), expect.objectContaining({ method: 'POST',
      body: JSON.stringify({ job_type: 'training', dataset_id: fixture.dataset_id, environment_id: null }),
      headers: expect.objectContaining({ authorization: 'Bearer private' }) }))
  })
  it('valida UUID e não confunde geração com treinamento', async () => {
    respond(job()); await expect(fetchTrainingJob('token', 'bad')).rejects.toThrow(); expect(fetch).not.toHaveBeenCalled()
    respond({ ...job(), job_type: 'generation' }); await expect(fetchTrainingJob('token', id)).rejects.toThrow()
    respond({ ...job(), id: fixture.dataset_id }); await expect(fetchTrainingJob('token', id)).rejects.toThrow()
  })
  it('valida resultado solicitado e lista de datasets limitada', async () => {
    respond(fixture); expect(await fetchTrainingResult('token', id)).toEqual(fixture)
    respond({ ...fixture, job_id: fixture.dataset_id }); await expect(fetchTrainingResult('token', id)).rejects.toThrow()
    const dataset = { id: fixture.dataset_id, name: 'Dataset sintético', row_count: 1000000, created_at: '2026-10-17T12:00:00Z', generation_job_id: id }
    respond([dataset]); expect(await fetchDatasets('token')).toEqual([dataset])
    respond(Array(51).fill(dataset)); await expect(fetchDatasets('token')).rejects.toThrow()
  })
})

describe('falhas e limites do contrato', () => {
  it.each([401, 403, 409, 503])('preserva falha HTTP %s sem detalhes privados', async (status) => {
    respond({ password: 'private' }, status)
    await expect(fetchTrainingResult('token', id)).rejects.toThrow(/Acesso|Não foi possível/)
  })
  it('rejeita ausência de envelope e ids antes da rede', async () => {
    respond(fixture)
    await expect(createTraining('token', 'bad')).rejects.toThrow()
    await expect(fetchTrainingResult('token', 'bad')).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: fixture }))))
    await expect(fetchTrainingResult('token', id)).rejects.toThrow('Resposta inválida')
  })
  it('recusa dados malformados em qualquer parte do relatório', () => {
    const patches = [{ job_id: 'bad' }, { model_id: 'bad' }, { seed: -1 }, { equipment_counts: { train: 0, validation: 1, test: 1 } },
      { versions: {} }, { limitations: [null] }, { health: { ...fixture.health, target: 'rul_hours_true' } },
      { health: { ...fixture.health, partition_rows: { train: 1, validation: 1, test: 999 } } },
      { rul: { ...fixture.rul, near_failure: null } },
      { rul: { ...fixture.rul, near_failure: { ...fixture.rul.near_failure, test: { row_count: 0, baseline: {}, candidate: {} } } } },
      ...[{ partition: 'train' }, { sample_count: 501 }, { sample_seed: -1 }, { sample_max: 501 }, { sampling: 'first' },
        { scatter: [{ actual: 1, predicted: 3, baseline: 2, error: -2 }] },
        { permutation: { ...fixture.health.diagnostics.permutation, repeats: 2 } },
        { permutation: { ...fixture.health.diagnostics.permutation, features: [{ name: 'x', mean: 1, std: -1 }] } },
      ].map((diagnostics) => ({ health: { ...fixture.health, diagnostics: { ...fixture.health.diagnostics, ...diagnostics } } }))]
    for (const patch of patches) expect(isTrainingResult({ ...fixture, ...patch }), JSON.stringify(patch)).toBe(false)
  })
  it('aceita recorte sem falhas e R² indefinido', () => {
    const result = structuredClone(fixture)
    result.rul.near_failure.test = { row_count: 0, baseline: null, candidate: null } as unknown as typeof result.rul.near_failure.test
    result.health.metrics.test.candidate.r2 = null as unknown as number
    expect(isTrainingResult(result)).toBe(true)
  })
})
