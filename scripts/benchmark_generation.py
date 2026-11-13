"""Generate and verify offline blocks in a fresh process, reporting peak RSS."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from uuid import uuid4

import numpy as np

from backend.app.domain.jobs import GenerationInput
from backend.app.services.generation import MEASUREMENTS, write_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New directory; never overwritten')
    parser.add_argument('--total', type=int, default=1_000_000)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    config = GenerationInput(job_type='generation', total_units=args.total, seed=args.seed)
    started = time.monotonic()
    path = write_dataset(args.output, uuid4(), config, lambda _: None)
    manifest = json.loads(path.read_text())
    rows = missing = observed = failures = 0
    block_hashes = []
    disk_bytes = path.stat().st_size
    for block in manifest['blocks']:
        source = path.parent / block['file']
        with source.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        assert digest == block['sha256']
        block_hashes.append(digest)
        disk_bytes += source.stat().st_size
        data = np.load(source, mmap_mode='r', allow_pickle=False)
        assert len(data) == block['row_count']
        assert np.all(np.isnan(data['rul_hours_true'][~data['rul_observed']]))
        assert np.all(data['rul_hours_true'][data['rul_observed']] >= 0)
        assert np.all((data['health_score_true'] >= 0) & (data['health_score_true'] <= 100))
        rows += len(data)
        missing += sum(int(np.isnan(data[name]).sum()) for name in MEASUREMENTS)
        observed += int(data['rul_observed'].sum())
        failures += int((data['rul_hours_true'] == 0).sum())
        del data
    assert rows == manifest['row_count'] == config.total_units
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = rss if sys.platform == 'darwin' else rss * 1024
    print(json.dumps({'row_count': rows, 'blocks': len(block_hashes), 'seed': config.seed,
        'block_hashes': block_hashes, 'disk_bytes': disk_bytes,
        'missing_measurements': missing, 'rul_observed_rows': observed, 'observed_failures': failures,
        'peak_rss_bytes': peak_bytes, 'elapsed_seconds': round(time.monotonic() - started, 3),
        'python': sys.version.split()[0], 'numpy': np.__version__, 'platform': sys.platform}, indent=2))


if __name__ == '__main__':
    main()
