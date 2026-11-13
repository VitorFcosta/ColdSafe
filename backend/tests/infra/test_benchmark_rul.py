import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import benchmark_rul


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / 'prepared'
    for name in benchmark_rul.PREPARED_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    return root


def fake_children(monkeypatch, prepared, *, rejected=False, mutate=False, inconsistent=False):
    calls = []

    def run(command, **kwargs):
        assert kwargs['check'] is True
        assert kwargs.get('shell', False) is False
        assert command[:2] == [sys.executable, '-c']
        assert Path(command[3]) == prepared.resolve()
        directory = Path(command[4])
        role = directory.name
        assert command[2] == benchmark_rul.CHILDREN[role]
        calls.append(role)
        directory.mkdir()
        model = role.encode()
        status = 'rejected' if rejected and role == 'rul' else 'eligible'
        model_hash = None
        if status == 'eligible':
            (directory / 'model.pkl').write_bytes(model)
            model_hash = hashlib.sha256(model).hexdigest()
        report = {
            'status': status, 'target': 'health_score_true' if role == 'health' else 'rul_hours_true',
            'unit': 'hours' if role == 'rul' else 'health_points',
            'prediction_range': [0, None] if role == 'rul' else [0, 100],
            'source': {'dataset_id': 'same'}, 'features_version': 'v1', 'feature_names': ['temperature'],
            'sensors': ['temperature'], 'windows_seconds': [60], 'transform': {'same': True},
            'seed': int(command[5]), 'split_seed': 42, 'equipment_split': {'train': ['one']},
            'input_hashes': benchmark_rul.fingerprints(prepared), 'model_sha256': model_hash,
            'timings': {'total_seconds': 0.1}, 'memory': {'peak_rss_bytes': 1234},
        }
        if inconsistent and role == 'rul':
            report['features_version'] = 'different'
        (directory / 'report.json').write_text(json.dumps(report))
        if mutate and role == 'health':
            (prepared / 'train/features.npy').write_bytes(b'changed')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(benchmark_rul.subprocess, 'run', run)
    return calls


def test_benchmark_trains_separate_sequential_children_and_records_evidence(tmp_path, prepared, monkeypatch):
    calls = fake_children(monkeypatch, prepared)
    output = tmp_path / 'output'
    result = benchmark_rul.benchmark(output, prepared=prepared, seed=7)
    assert calls == ['health', 'rul']
    assert result['run_order'] == calls
    assert result['sequential_processes'] is True
    assert result['source_unchanged'] is True
    assert result['prepared_sha256_before'] == result['prepared_sha256_after']
    assert result['status'] == 'eligible'
    assert result['health']['memory']['peak_rss_bytes'] == 1234
    assert result['rul']['timings']['total_seconds'] == 0.1
    assert output.stat().st_mode & 0o777 == 0o700
    assert json.loads((output / 'benchmark.json').read_text()) == result


def test_rejected_rul_is_recorded_without_claiming_two_models(tmp_path, prepared, monkeypatch):
    fake_children(monkeypatch, prepared, rejected=True)
    output = tmp_path / 'output'
    result = benchmark_rul.benchmark(output, prepared=prepared)
    assert result['status'] == 'rejected'
    assert result['rul']['model_sha256'] is None
    assert not (output / 'rul/model.pkl').exists()


def test_first_process_failure_prevents_second_and_completion_marker(tmp_path, prepared, monkeypatch):
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(benchmark_rul.subprocess, 'run', fail)
    output = tmp_path / 'output'
    with pytest.raises(subprocess.CalledProcessError):
        benchmark_rul.benchmark(output, prepared=prepared)
    assert len(calls) == 1
    assert not (output / 'benchmark.json').exists()


@pytest.mark.parametrize('seed', [-1, 2**32, True, 1.5])
def test_invalid_seed_does_not_create_output(tmp_path, prepared, seed):
    output = tmp_path / 'output'
    with pytest.raises(ValueError, match='seed'):
        benchmark_rul.benchmark(output, prepared=prepared, seed=seed)
    assert not output.exists()


@pytest.mark.parametrize('output_kind', ['inside', 'ancestor', 'existing'])
def test_output_must_be_new_and_separate(tmp_path, prepared, output_kind):
    output = {'inside': prepared / 'output', 'ancestor': tmp_path, 'existing': tmp_path / 'existing'}[output_kind]
    if output_kind == 'existing':
        output.mkdir()
    with pytest.raises((ValueError, FileExistsError)):
        benchmark_rul.benchmark(output, prepared=prepared)


def test_symlink_preparation_root_is_rejected(tmp_path, prepared):
    link = tmp_path / 'link'
    link.symlink_to(prepared, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        benchmark_rul.benchmark(tmp_path / 'output', prepared=link)


@pytest.mark.parametrize('mutate,inconsistent', [(True, False), (False, True)])
def test_mutation_or_inconsistent_reports_prevents_completion(tmp_path, prepared, monkeypatch, mutate, inconsistent):
    calls = fake_children(monkeypatch, prepared, mutate=mutate, inconsistent=inconsistent)
    output = tmp_path / 'output'
    with pytest.raises(ValueError):
        benchmark_rul.benchmark(output, prepared=prepared)
    assert not (output / 'benchmark.json').exists()
    if mutate:
        assert calls == ['health']


def test_hashes_only_known_prepared_files(tmp_path, prepared):
    (prepared / 'unrelated-secret').symlink_to(tmp_path / 'missing')
    assert set(benchmark_rul.fingerprints(prepared)) == set(benchmark_rul.PREPARED_FILES)


def test_symlink_partition_is_rejected_before_output_creation(tmp_path, prepared):
    (prepared / 'train').rename(prepared / 'other')
    (prepared / 'train').symlink_to(prepared / 'other', target_is_directory=True)
    output = tmp_path / 'output'
    with pytest.raises(ValueError, match='symlink'):
        benchmark_rul.benchmark(output, prepared=prepared)
    assert not output.exists()


@pytest.mark.parametrize('problem', ['corrupt_model', 'same_models', 'wrong_target', 'seconds_target',
    'wrong_unit', 'wrong_prediction_range', 'wrong_seed', 'malformed_report'])
def test_invalid_child_artifacts_never_publish_completion(tmp_path, prepared, monkeypatch, problem):
    fake_children(monkeypatch, prepared)
    child = benchmark_rul.subprocess.run

    def alter(command, **kwargs):
        result = child(command, **kwargs)
        directory = Path(command[4])
        if directory.name == 'rul':
            report_path = directory / 'report.json'
            report = json.loads(report_path.read_text())
            if problem == 'corrupt_model':
                (directory / 'model.pkl').write_bytes(b'corrupt')
            elif problem == 'same_models':
                model = (directory.parent / 'health/model.pkl').read_bytes()
                (directory / 'model.pkl').write_bytes(model)
                report['model_sha256'] = hashlib.sha256(model).hexdigest()
            elif problem == 'wrong_target':
                report['target'] = 'health_score_true'
            elif problem == 'seconds_target':
                report['target'] = 'rul_seconds_true'
            elif problem == 'wrong_unit':
                report['unit'] = 'seconds'
            elif problem == 'wrong_prediction_range':
                report['prediction_range'] = [0, 100]
            elif problem == 'wrong_seed':
                report['seed'] = 99
            report_path.write_text('broken' if problem == 'malformed_report' else json.dumps(report))
        return result

    monkeypatch.setattr(benchmark_rul.subprocess, 'run', alter)
    output = tmp_path / 'output'
    with pytest.raises(ValueError):
        benchmark_rul.benchmark(output, prepared=prepared)
    assert not (output / 'benchmark.json').exists()


def test_cli_requires_prepared_and_passes_arguments(tmp_path, prepared, monkeypatch, capsys):
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', ['benchmark_rul', '--prepared', str(prepared), '--output', str(output), '--seed', '8'])
    seen = []
    monkeypatch.setattr(benchmark_rul, 'benchmark', lambda directory, **kwargs: seen.append((directory, kwargs)) or {'ok': True})
    benchmark_rul.main()
    assert seen == [(output, {'prepared': prepared, 'seed': 8})]
    assert json.loads(capsys.readouterr().out) == {'ok': True}


def test_cli_requires_existing_preparation_argument(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['benchmark_rul', '--output', str(tmp_path / 'output')])
    with pytest.raises(SystemExit) as error:
        benchmark_rul.main()
    assert error.value.code == 2
