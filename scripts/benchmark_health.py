"""Exercise offline health training on generated data or an existing B2-20 preparation."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time
from uuid import NAMESPACE_URL, uuid5

from backend.app.domain.jobs import GenerationInput
from backend.app.services.generation import write_dataset
from backend.app.services.health_training import train_health
from backend.app.services.training_data import prepare_dataset


def fingerprints(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:
                result[str(path.relative_to(directory))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def benchmark(output: Path, *, prepared: Path | None = None, total: int = 1_000_000,
              seed: int = 42) -> dict:
    if prepared is not None:
        prepared = prepared.resolve(strict=True)
        if output.resolve().is_relative_to(prepared) or prepared.is_relative_to(output.resolve()):
            raise ValueError('Preparation and output directories must be separate')
    output.mkdir(mode=0o700, exist_ok=False)
    timings = {}
    if prepared is None:
        config = GenerationInput(job_type='generation', total_units=total, seed=seed)
        dataset_id = uuid5(NAMESPACE_URL, f'coldsafe-b2-21-benchmark-{total}-{seed}')
        owner, job_id = uuid5(dataset_id, 'owner'), uuid5(dataset_id, 'generation')
        started = time.perf_counter()
        write_dataset(output / 'source', dataset_id, config, lambda _: None)
        timings['generation_seconds'] = time.perf_counter() - started
        dataset = {'id': dataset_id, 'owner_user_id': owner, 'generation_job_id': job_id,
            'created_at': datetime.now(UTC), 'row_count': total, 'artifact_key': 'source/manifest.json'}
        job = {'id': job_id, 'owner_user_id': owner, 'job_type': 'generation',
            'status': 'completed', 'result_id': dataset_id, 'total_units': total,
            'environment_id': None, 'config': config.model_dump(mode='json')}
        prepared = output / 'prepared'
        started = time.perf_counter()
        prepare_dataset(output, dataset, job, prepared, seed=seed)
        timings['preparation_seconds'] = time.perf_counter() - started
    before = fingerprints(prepared)
    report = train_health(prepared, output / 'health', seed=seed)
    assert before == fingerprints(prepared), 'Training changed its source preparation'
    if (output / 'source').exists():
        source = json.loads((output / 'source/manifest.json').read_text())
        for block in source['blocks']:
            with (output / 'source' / block['file']).open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == block['sha256']
    result = {'training': report, 'timings': timings, 'prepared_sha256': before,
              'preparation_unchanged': True,
              'source_blocks_unchanged': True if (output / 'source').exists() else None}
    (output / 'benchmark.json').write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--total', type=int, choices=(1_000_000, 2_000_000), default=1_000_000)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.output, prepared=args.prepared, total=args.total, seed=args.seed),
                     allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
