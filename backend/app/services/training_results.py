"""Bounded JSON-only inspection of private training packages."""
import json
import math
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.datasets import _internal_file
from backend.app.services.health_training import PARTITIONS, _manifest, _sha256

Count = Annotated[int, Field(strict=True, ge=0, le=2_000_000)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Seed = Annotated[int, Field(strict=True, ge=0, le=2**32 - 1)]


class ResultModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Metrics(ResultModel):
    mae: Nonnegative
    rmse: Nonnegative
    r2: Annotated[float, Field(strict=True, le=1, allow_inf_nan=False)] | None


class Comparison(ResultModel):
    baseline: Metrics
    candidate: Metrics


class Evaluations(ResultModel):
    validation: Comparison
    test: Comparison


class ScatterPoint(ResultModel):
    actual: Nonnegative
    predicted: Nonnegative
    baseline: Nonnegative
    error: Number


class Importance(ResultModel):
    name: str = Field(min_length=1, max_length=200)
    mean: Number
    std: Nonnegative


class Permutation(ResultModel):
    scoring: Literal['mae_increase']
    repeats: Literal[3]
    sample_count: int = Field(strict=True, ge=1, le=500)
    reference_mae: Nonnegative
    features: list[Importance] = Field(min_length=1, max_length=144)


class Diagnostics(ResultModel):
    partition: Literal['test']
    total_rows: Count
    sample_count: int = Field(strict=True, ge=1, le=500)
    sample_seed: Seed
    sample_max: Literal[500]
    sampling: Literal['seeded_without_replacement']
    scatter: list[ScatterPoint] = Field(min_length=1, max_length=500)
    permutation: Permutation


class PartitionRows(ResultModel):
    train: Count
    validation: Count
    test: Count


class NearPartition(ResultModel):
    row_count: Count
    baseline: Metrics | None
    candidate: Metrics | None


class NearFailure(ResultModel):
    threshold_hours: Literal[24]
    validation: NearPartition
    test: NearPartition


class TargetResult(ResultModel):
    target: Literal['health_score_true', 'rul_hours_true']
    unit: Literal['points', 'hours']
    status: Literal['eligible', 'rejected']
    metrics: Evaluations
    partition_rows: PartitionRows
    diagnostics: Diagnostics
    near_failure: NearFailure | None


class TrainingResult(ResultModel):
    job_id: UUID
    dataset_id: UUID
    model_id: UUID
    model_version: str = Field(min_length=1, max_length=80)
    eligible: bool = Field(strict=True)
    features_version: str = Field(min_length=1, max_length=80)
    seed: Seed
    split_seed: Seed
    equipment_counts: PartitionRows
    versions: dict[str, str]
    health: TargetResult
    rul: TargetResult
    limitations: list[str]


class TrainingResultUnavailable(Exception):
    """Private artifact cannot safely be exposed."""


def _json(root: Path, key: str) -> dict:
    path = _internal_file(root, key)
    if not 0 < path.stat().st_size <= 4 * 1_048_576:
        raise ValueError('Invalid training JSON size')
    def finite_number(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('Nonfinite JSON')
        return number

    result = json.loads(path.read_bytes(), parse_float=finite_number,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    if not isinstance(result, dict):
        raise ValueError('Invalid training JSON object')
    return result


def build_package(directory: Path, job: dict, dataset: dict, identifier: UUID) -> dict:
    prepared, _, _ = _manifest(directory / 'prepared')
    reports = {target: _json(directory, f'{target}/report.json') for target in ('health', 'rul')}
    return {'storage_version': 'training-package-v1', 'job_id': str(job['id']),
        'dataset_id': str(dataset['id']), 'owner_user_id': str(job['owner_user_id']),
        'model_id': str(identifier), 'model_version': f"training-{job['id']}",
        'features_version': prepared['features_version'],
        'prepared_sha256': _sha256(_internal_file(directory, 'prepared/manifest.json')),
        'reports': {target: {'file': f'{target}/report.json',
            'sha256': _sha256(_internal_file(directory, f'{target}/report.json')),
            'model_sha256': reports[target]['model_sha256']} for target in reports}}


def _validated(root: Path, model: dict, job: dict, dataset: dict) -> dict:
    if (str(model['owner_user_id']) != str(job['owner_user_id']) or
            str(dataset['owner_user_id']) != str(job['owner_user_id']) or
            str(model['training_job_id']) != str(job['id']) or
            str(model['dataset_id']) != str(dataset['id']) or
            str(job['dataset_id']) != str(dataset['id']) or job['job_type'] != 'training'):
        raise ValueError('Training ownership mismatch')
    path = _internal_file(root, model['artifact_key'])
    directory = path.parent
    package = _json(root, model['artifact_key'])
    identifier = uuid5(UUID(str(job['id'])), 'training-package-v1')
    expected = {'storage_version': 'training-package-v1', 'job_id': str(job['id']),
        'dataset_id': str(dataset['id']), 'owner_user_id': str(job['owner_user_id']),
        'model_id': str(identifier), 'model_version': f"training-{job['id']}",
        'features_version': model['features_version']}
    if (any(package[key] != value for key, value in expected.items()) or str(model['id']) != str(identifier) or
            model['model_version'] != expected['model_version'] or set(package['reports']) != {'health', 'rul'}):
        raise ValueError('Training package identity mismatch')
    prepared, spec, _ = _manifest(directory / 'prepared')
    prepared_hash = _sha256(_internal_file(directory, 'prepared/manifest.json'))
    source = {'dataset_id': str(dataset['id']), 'owner_user_id': str(job['owner_user_id']),
              'generation_job_id': str(dataset['generation_job_id'])}
    if (prepared['source'] != source or prepared['source_row_count'] != dataset['row_count'] or
            prepared['features_version'] != package['features_version'] or package['prepared_sha256'] != prepared_hash):
        raise ValueError('Training prepared source mismatch')
    expected_hashes = {'manifest.json', *(prepared['partitions'][part][key]
        for part in PARTITIONS for key in ('features', 'targets'))}
    targets, reports = {}, {}
    for target, label, unit in (('health', 'health_score_true', 'points'), ('rul', 'rul_hours_true', 'hours')):
        info = package['reports'][target]
        key = f'{target}/report.json'
        if info['file'] != key or info['sha256'] != _sha256(_internal_file(directory, key)):
            raise ValueError('Training report hash mismatch')
        report = _json(directory, key)
        if (report['storage_version'] != f'{target}-training-v1' or report['target'] != label or
                report['prediction_range'] != ([0, 100] if target == 'health' else [0, None]) or
                target == 'rul' and report['unit'] != 'hours' or
                report['features_version'] != prepared['features_version'] or
                report['feature_names'] != list(spec.names) or report['sensors'] != list(spec.sensors) or
                report['windows_seconds'] != list(spec.windows_seconds) or report['transform'] != prepared['transform'] or
                report['source'] != source or report['equipment_split'] != prepared['equipment_split'] or
                report['split_seed'] != prepared['split_seed'] or report['seed'] != 42 or
                report['input_hashes']['manifest.json'] != prepared_hash or
                report['model_sha256'] != info['model_sha256']):
            raise ValueError('Training report contract mismatch')
        if (set(report['input_hashes']) != expected_hashes or
                any(not isinstance(value, str) or len(value) != 64 or
                    any(char not in '0123456789abcdef' for char in value)
                    for value in report['input_hashes'].values())):
            raise ValueError('Invalid prepared input hashes')
        if report['status'] == 'eligible':
            if info['model_sha256'] != _sha256(_internal_file(directory, f'{target}/model.pkl')):
                raise ValueError('Training model hash mismatch')
        elif (report['status'] != 'rejected' or info['model_sha256'] is not None or
                (directory / target / 'model.pkl').exists() or (directory / target / 'model.pkl').is_symlink()):
            raise ValueError('Rejected model must not contain pickle')
        rows = {part: prepared['partitions'][part]['row_count' if target == 'health' else 'rul_observed_rows']
                for part in PARTITIONS}
        if target == 'health':
            if report['partition_rows'] != rows:
                raise ValueError('Health count mismatch')
        elif report['partition_rows'] != {part: {'full': prepared['partitions'][part]['row_count'],
                'observed': rows[part], 'censored': prepared['partitions'][part]['rul_censored_rows']} for part in PARTITIONS}:
            raise ValueError('RUL count mismatch')
        targets[target] = TargetResult.model_validate({'target': label, 'unit': unit,
            'status': report['status'], 'metrics': report['metrics'], 'partition_rows': rows,
            'diagnostics': report['diagnostics'], 'near_failure': report.get('near_failure')})
        dto = targets[target]
        diagnostic = dto.diagnostics
        points = diagnostic.scatter
        if (any(value <= 0 for value in rows.values()) or diagnostic.total_rows != rows['test'] or
                diagnostic.sample_count != min(500, rows['test']) or len(points) != diagnostic.sample_count or
                diagnostic.permutation.sample_count != diagnostic.sample_count or
                [item.name for item in diagnostic.permutation.features] != list(spec.names) or
                diagnostic.sample_seed != report['seed'] or
                any(not math.isclose(point.error, point.predicted - point.actual, abs_tol=1e-8) for point in points) or
                not math.isclose(diagnostic.permutation.reference_mae,
                    sum(abs(point.error) for point in points) / len(points), rel_tol=1e-8, abs_tol=1e-8) or
                target == 'health' and any(max(point.actual, point.predicted, point.baseline) > 100 for point in points)):
            raise ValueError('Invalid diagnostic counts or semantics')
        gate = dto.metrics.validation.candidate.mae < dto.metrics.validation.baseline.mae
        if gate != (dto.status == 'eligible'):
            raise ValueError('Training selection mismatch')
        if target == 'health' and dto.near_failure is not None or target == 'rul' and dto.near_failure is None:
            raise ValueError('Invalid near failure result')
        if dto.near_failure:
            for part in ('validation', 'test'):
                near = getattr(dto.near_failure, part)
                empty = near.row_count == 0
                if (near.row_count > rows[part] or (near.baseline is None) != empty or
                        (near.candidate is None) != empty):
                    raise ValueError('Invalid near failure counts')
        reports[target] = report
    if (reports['health']['input_hashes'] != reports['rul']['input_hashes'] or
            reports['health']['versions'] != reports['rul']['versions']):
        raise ValueError('Training pair input or version mismatch')
    excluded = {part: prepared['partitions'][part]['rul_censored_rows'] for part in PARTITIONS}
    dto = TrainingResult(job_id=UUID(str(job['id'])), dataset_id=UUID(str(dataset['id'])),
        model_id=identifier, model_version=package['model_version'],
        eligible=all(item.status == 'eligible' for item in targets.values()),
        features_version=package['features_version'], seed=42, split_seed=prepared['split_seed'],
        equipment_counts=PartitionRows(**{part: len(prepared['equipment_split'][part]) for part in PARTITIONS}),
        versions=reports['health']['versions'], **targets,
        limitations=['Resultados sintéticos: precisão física ainda não validada.',
            'Pacote apenas para avaliação offline; sem uso nas leituras do monitoramento.',
            'RUL usa somente falhas observadas; linhas censuradas excluídas: ' + json.dumps(excluded, sort_keys=True),
            'Permutação e dispersão usam amostra reservada de até 500 linhas; correlação pode diluir importância.',
            'R² próximo da falha pode ser negativo; consulte o recorte das últimas 24 horas.'])
    result = dto.model_dump(mode='json')
    if 'metrics' in model:
        expected_metrics = {'eligible': result['eligible'], **{target: {
            'status': result[target]['status'], 'metrics': result[target]['metrics']}
            for target in ('health', 'rul')}}
        if model['metrics'] != expected_metrics:
            raise ValueError('Registered metrics mismatch')
    return result


def read_training_result(artifact_root: Path, model: dict, job: dict, dataset: dict) -> dict:
    try:
        return _validated(artifact_root.resolve(strict=True), model, job, dataset)
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, EOFError, RecursionError) as error:
        raise TrainingResultUnavailable('Training result unavailable') from error
