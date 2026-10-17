"""Generate and prepare a private synthetic dataset, proving B2-20 invariants."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from uuid import uuid4

import numpy as np

from backend.app.domain.features import FeatureSpec
from backend.app.domain.feature_preprocessing import FeatureTransform
from backend.app.domain.jobs import GenerationInput
from backend.app.services.feature_inputs import LIVE_NAMES, offline_features, telemetry_features
from backend.app.services.generation import MEASUREMENTS, write_dataset
from backend.app.services.training_data import prepare_dataset


def benchmark(output: Path, *, total: int = 1_000_000, seed: int = 42) -> dict:
    config = GenerationInput(job_type='generation', total_units=total, seed=seed)
    output.mkdir(mode=0o700, exist_ok=False)
    dataset_id, owner, job_id = uuid4(), uuid4(), uuid4()
    started = time.perf_counter()
    write_dataset(output / 'source', dataset_id, config, lambda _: None)
    generation_seconds = time.perf_counter() - started
    source = json.loads((output / 'source/manifest.json').read_text())
    dataset = {'id': dataset_id, 'owner_user_id': owner, 'generation_job_id': job_id,
        'created_at': datetime.now(UTC), 'row_count': total, 'artifact_key': 'source/manifest.json'}
    job = {'id': job_id, 'owner_user_id': owner, 'job_type': 'generation',
        'status': 'completed', 'result_id': dataset_id, 'total_units': total,
        'environment_id': None, 'config': config.model_dump(mode='json')}
    started = time.perf_counter()
    prepared = output / 'prepared'
    manifest = prepare_dataset(output, dataset, job, prepared, seed=seed)
    preparation_seconds = time.perf_counter() - started
    preparation_peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    groups = []
    for part, info in manifest['partitions'].items():
        features = np.load(prepared / info['features'], mmap_mode='r', allow_pickle=False)
        targets = np.load(prepared / info['targets'], mmap_mode='r', allow_pickle=False)
        assert features.shape == (info['row_count'], len(manifest['feature_names']))
        del features
        for offset in range(0, info['row_count'], 5000):
            features = np.load(prepared / info['features'], mmap_mode='r', allow_pickle=False)
            assert np.isfinite(features[offset:offset + 5000]).all()
            del features
        ids = {source['equipment'][int(index)]['id'] for index in np.unique(targets['equipment_index'])}
        assert ids == set(manifest['equipment_split'][part])
        assert np.isnan(targets['rul_hours_true'][~targets['rul_observed']]).all()
        assert np.isfinite(targets['health_score_true']).all()
        groups.append(ids)
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    assert manifest['source_row_count'] == total
    assert manifest['row_count'] + manifest['dropped_insufficient_history'] == total
    assert len(manifest['feature_names']) == 48

    train_info = manifest['partitions']['train']
    features = np.load(prepared / train_info['features'], mmap_mode='r', allow_pickle=False)
    targets = np.load(prepared / train_info['targets'], mmap_mode='r', allow_pickle=False)
    first = targets[0]
    index = int(first['equipment_index'])
    history = []
    for block in source['blocks']:
        rows = np.load(output / 'source' / block['file'], mmap_mode='r', allow_pickle=False)
        history.append(rows[(rows['equipment_index'] == index) & (rows['observed_at'] <= first['observed_at'])])
    history = np.concatenate(history)
    spec = FeatureSpec(sensors=tuple(manifest['sensors']), windows_seconds=tuple(manifest['windows_seconds']))
    transform = FeatureTransform.from_dict(manifest['transform'])
    expected = transform.apply(offline_features(history, spec).values[-1:], spec.names)
    equipment_id = source['equipment'][index]['id']
    events = [{'schema_version': 3, 'type': 'telemetry', 'received_at': str(row['observed_at']) + 'Z',
        'occurred_at': '2000-01-01T00:00:00Z', 'data': {'equipment': {'equipment_id': equipment_id},
        'measurements': {LIVE_NAMES[name]: {'unit': MEASUREMENTS[name], 'value':
            None if np.isnan(row[name]) else float(row[name])} for name in spec.sensors}}} for row in history]
    online = telemetry_features(events, equipment_id, str(first['observed_at']) + 'Z', transform, spec)
    assert online.sufficient[0]
    np.testing.assert_array_equal(online.values, expected)
    np.testing.assert_array_equal(features[:1], expected)
    for block in source['blocks']:
        with (output / 'source' / block['file']).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == block['sha256']
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = rss if sys.platform == 'darwin' else rss * 1024
    assert rss_bytes < 512 * 2**20, 'Preparation/verification exceeds the existing worker memory budget'
    report = {'total_units': total, 'seed': seed, 'generation_seconds': generation_seconds,
        'preparation_seconds': preparation_seconds, 'peak_rss_bytes': rss_bytes,
        'preparation_peak_rss_bytes': preparation_peak_rss if sys.platform == 'darwin' else preparation_peak_rss * 1024,
        'disk_bytes': sum(path.stat().st_size for path in output.rglob('*') if path.is_file()),
        'prepared_rows': manifest['row_count'], 'dropped_insufficient_history': manifest['dropped_insufficient_history'],
        'features_version': manifest['features_version'], 'features_count': len(spec.names),
        'partitions': manifest['partitions'], 'equipment_counts': {part: len(ids) for part, ids in manifest['equipment_split'].items()},
        'offline_online_max_difference': float(np.max(np.abs(online.values - expected))),
        'source_unchanged': True, 'numpy_version': np.__version__, 'python_version': sys.version.split()[0]}
    (output / 'report.json').write_text(json.dumps(report, allow_nan=False, indent=2) + '\n')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--total', type=int, choices=(1_000_000, 2_000_000), default=1_000_000)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.output, total=args.total, seed=args.seed), allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
