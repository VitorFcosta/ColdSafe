"""Benchmark independent health and RUL training in sequential child processes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter


PREPARED_FILES = ('manifest.json', *(f'{part}/{kind}.npy'
    for part in ('train', 'validation', 'test') for kind in ('features', 'targets')))
CHILDREN = {
    'health': 'from pathlib import Path; import sys; '
              'from backend.app.services.health_training import train_health; '
              'train_health(Path(sys.argv[1]), Path(sys.argv[2]), seed=int(sys.argv[3]))',
    'rul': 'from pathlib import Path; import sys; '
           'from backend.app.services.rul_training import train_rul; '
           'train_rul(Path(sys.argv[1]), Path(sys.argv[2]), seed=int(sys.argv[3]))',
}


def _sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fingerprints(directory: Path) -> dict[str, str]:
    """Hash only the seven files in the preparation contract."""
    result = {}
    for name in PREPARED_FILES:
        path = directory / name
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ValueError('Prepared files must be regular internal files, without symlinks')
        result[name] = _sha256(path)
    return result


def _report(directory: Path) -> dict:
    path = directory / 'report.json'
    if path.is_symlink() or not 0 < path.stat().st_size <= 4 * 1_048_576:
        raise ValueError('Invalid child report size or symlink')
    report = json.loads(path.read_bytes())
    if not isinstance(report, dict) or report.get('status') not in ('eligible', 'rejected'):
        raise ValueError('Invalid child training status')
    model = directory / 'model.pkl'
    if report['status'] == 'eligible':
        if model.is_symlink() or not model.is_file() or _sha256(model) != report.get('model_sha256'):
            raise ValueError('Child model hash does not match its report')
    elif model.exists() or report.get('model_sha256') is not None:
        raise ValueError('Rejected child must not publish a model')
    return report


def benchmark(output: Path, *, prepared: Path, seed: int = 42) -> dict:
    """Train one estimator process at a time; publish evidence only after validation."""
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('Training seed must be an unsigned 32-bit integer')
    if prepared.is_symlink():
        raise ValueError('Prepared root cannot be a symlink')
    prepared = prepared.resolve(strict=True)
    destination = output.resolve()
    if destination.is_relative_to(prepared) or prepared.is_relative_to(destination):
        raise ValueError('Preparation and output directories must be separate')
    before = fingerprints(prepared)
    output.mkdir(mode=0o700, exist_ok=False)
    reports, durations = {}, {}
    for role, code in CHILDREN.items():
        started = perf_counter()
        subprocess.run([sys.executable, '-c', code, str(prepared), str(output.resolve() / role), str(seed)],
                       check=True, cwd=Path(__file__).resolve().parents[1])
        durations[role] = perf_counter() - started
        reports[role] = _report(output / role)
        if fingerprints(prepared) != before:
            raise ValueError('Training changed its source preparation')
        if reports[role].get('input_hashes') != before:
            raise ValueError('Child input hashes do not match the preparation')
        if reports[role].get('seed') != seed:
            raise ValueError('Child training seed does not match the benchmark')
    health, rul = reports['health'], reports['rul']
    for key in ('source', 'features_version', 'feature_names', 'sensors', 'windows_seconds',
                'transform', 'split_seed', 'equipment_split'):
        if key not in health or key not in rul or health[key] != rul[key]:
            raise ValueError(f'Health and RUL training contracts differ: {key}')
    if health.get('target') != 'health_score_true' or rul.get('target') != 'rul_hours_true':
        raise ValueError('Health and RUL must train their independent targets')
    if rul.get('unit') != 'hours' or rul.get('prediction_range') != [0, None]:
        raise ValueError('RUL predictions must be nonnegative hours without an upper limit')
    eligible = all(report['status'] == 'eligible' for report in reports.values())
    if eligible and health['model_sha256'] == rul['model_sha256']:
        raise ValueError('Independent targets must produce distinct model artifacts')
    after = fingerprints(prepared)
    if before != after:
        raise ValueError('Training changed its source preparation')
    result = {'status': 'eligible' if eligible else 'rejected', **reports,
        'run_order': list(CHILDREN), 'sequential_processes': True,
        'process_wall_seconds': durations, 'source_unchanged': True,
        'prepared_sha256_before': before, 'prepared_sha256_after': after}
    temporary = output / 'benchmark.json.tmp'
    temporary.write_text(json.dumps(result, allow_nan=False, sort_keys=True, indent=2) + '\n')
    temporary.replace(output / 'benchmark.json')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.output, prepared=args.prepared, seed=args.seed),
                     allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
