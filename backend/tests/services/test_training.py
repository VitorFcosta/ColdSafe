from unittest.mock import Mock, patch
import subprocess

import pytest

from backend.app.services.training import run_child


def test_child_checks_lock_while_waiting_and_kills_on_loss():
    child = Mock()
    child.wait.side_effect = [subprocess.TimeoutExpired('train', 2), None]
    checkpoint = Mock(side_effect=RuntimeError('lost lock'))
    with patch('backend.app.services.training.subprocess.Popen', return_value=child):
        with pytest.raises(RuntimeError, match='lost lock'):
            run_child(['health', '/source', '/output'], checkpoint, 1)
    child.terminate.assert_called_once()
    checkpoint.assert_called_once_with(1)


def test_child_failure_is_not_published():
    child = Mock()
    child.wait.return_value = 1
    with patch('backend.app.services.training.subprocess.Popen', return_value=child):
        with pytest.raises(ValueError, match='Training subprocess failed'):
            run_child(['rul', '/source', '/output'], Mock(), 0)

from pathlib import Path
import json
from uuid import uuid4, uuid5

from backend.app.services.health_training import train_health, _sha256
from backend.app.services.rul_training import train_rul
from backend.app.services.training_results import build_package, read_training_result, TrainingResultUnavailable
from backend.tests.services.test_rul_training import prepared


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    root = tmp_path_factory.mktemp('training-package')
    directory = root / 'attempt'
    directory.mkdir()
    manifest = prepared(directory / 'prepared')
    owner, job_id, dataset_id, generation_id = uuid4(), uuid4(), uuid4(), uuid4()
    dataset = {'id': dataset_id, 'owner_user_id': owner, 'generation_job_id': generation_id, 'row_count': 720}
    job = {'id': job_id, 'owner_user_id': owner, 'dataset_id': dataset_id, 'job_type': 'training'}
    manifest['source'] = {'dataset_id': str(dataset_id), 'owner_user_id': str(owner), 'generation_job_id': str(generation_id)}
    (directory / 'prepared/manifest.json').write_text(json.dumps(manifest))
    train_health(directory / 'prepared', directory / 'health')
    train_rul(directory / 'prepared', directory / 'rul')
    identifier = uuid5(job_id, 'training-package-v1')
    info = build_package(directory, job, dataset, identifier)
    (directory / 'manifest.json').write_text(json.dumps(info))
    model = {'id': identifier, 'owner_user_id': owner, 'dataset_id': dataset_id, 'training_job_id': job_id,
        'model_version': info['model_version'], 'features_version': info['features_version'],
        'artifact_key': 'attempt/manifest.json'}
    return root, model, job, dataset


def test_public_result_is_bound_to_source_and_contains_no_private_paths(package):
    root, model, job, dataset = package
    result = read_training_result(root, model, job, dataset)
    assert result['eligible'] is True
    assert result['health']['partition_rows']['test'] == 240
    assert result['rul']['partition_rows']['test'] == 200
    assert result['health']['near_failure'] is None
    assert result['rul']['near_failure']['threshold_hours'] == 24
    encoded = json.dumps(result)
    for private in ('artifact_key', 'model.pkl', 'transform', 'owner_user_id', str(root)):
        assert private not in encoded


@pytest.mark.parametrize('kind', ['hash', 'nan', 'sample_count', 'feature', 'model', 'symlink', 'source', 'status', 'range', 'unit', 'near_partial'])
def test_corrupt_or_partial_package_is_sanitized(package, tmp_path, kind):
    import shutil
    root, model, job, dataset = package
    shutil.copytree(root / 'attempt', tmp_path / 'attempt')
    directory = tmp_path / 'attempt'
    target = 'rul' if kind in ('unit', 'near_partial') else 'health'
    report_path = directory / target / 'report.json'
    report = json.loads(report_path.read_text())
    if kind == 'hash':
        report_path.write_text('{}')
    elif kind == 'model':
        (directory / 'health/model.pkl').unlink()
    elif kind == 'symlink':
        report_path.unlink()
        report_path.symlink_to(root / 'attempt/health/report.json')
    else:
        if kind == 'nan':
            report['metrics']['test']['candidate']['mae'] = float('nan')
        elif kind == 'sample_count':
            report['diagnostics']['sample_count'] = 501
        elif kind == 'feature':
            report['diagnostics']['permutation']['features'][0]['name'] = 'leaked_target'
        elif kind == 'source':
            report['source']['owner_user_id'] = str(uuid4())
        elif kind == 'status':
            report['status'] = 'rejected'
        elif kind == 'range':
            report['prediction_range'] = [0, None]
        elif kind == 'unit':
            report['unit'] = 'days'
        elif kind == 'near_partial':
            report['near_failure']['test']['row_count'] = 0
            report['near_failure']['test']['baseline'] = None
        report_path.write_text(json.dumps(report))
        info = json.loads((directory / 'manifest.json').read_text())
        info['reports'][target]['sha256'] = _sha256(report_path)
        (directory / 'manifest.json').write_text(json.dumps(info))
    with pytest.raises(TrainingResultUnavailable, match='Training result unavailable'):
        read_training_result(tmp_path, model, job, dataset)


def test_result_rejects_cross_owner_before_artifact_access(package):
    root, model, job, dataset = package
    with patch('backend.app.services.training_results._internal_file') as file:
        with pytest.raises(TrainingResultUnavailable):
            read_training_result(root, model | {'owner_user_id': uuid4()}, job, dataset)
    file.assert_not_called()


def test_handler_replays_in_new_attempt_and_never_activates(package, tmp_path):
    import shutil
    from contextlib import contextmanager
    from datetime import UTC, datetime
    from backend.app.services.training import TrainingHandler
    root, model, private_job, dataset = package
    template = {'owner_user_id': private_job['owner_user_id'], 'environment_id': None, 'dataset_id': None,
        'completed_units': 0, 'total_units': 2, 'error_code': None, 'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC), 'result_dataset_id': None, 'result_model_id': None, 'config': {}}
    job = template | private_job | {'status': 'running', 'completed_units': 1}
    generation = template | {'id': dataset['generation_job_id'], 'job_type': 'generation',
        'status': 'completed', 'result_dataset_id': dataset['id'], 'total_units': 1_000_000,
        'config': {'job_type': 'generation', 'total_units': 1_000_000}}
    handler = TrainingHandler(Mock(), artifact_root=tmp_path / 'source', training_artifact_root=tmp_path / 'output')
    handler.artifact_root.mkdir()
    handler.repository = Mock()
    handler.repository.get_dataset.return_value = dataset
    handler.repository.get_job.return_value = generation
    connection = Mock()
    @contextmanager
    def connect(_):
        yield connection
    def child(arguments, checkpoint, completed):
        phase, _, destination, *_ = arguments
        shutil.copytree(root / 'attempt' / ('prepared' if phase == 'prepare' else phase), destination)
        checkpoint(completed)
    checkpoints = []
    with patch('backend.app.services.training.run_child', side_effect=child), patch('backend.app.services.training.connect', connect):
        assert handler(job, checkpoints.append) == model['id']
        assert handler(job, checkpoints.append) == model['id']
    assert len(list((tmp_path / 'output').iterdir())) == 2
    assert all(value in (1, 2) for value in checkpoints)
    middle = len(checkpoints) // 2
    assert checkpoints[:middle] == sorted(checkpoints[:middle])
    assert checkpoints[middle:] == sorted(checkpoints[middle:])
    assert all('INSERT INTO models' in call.args[0] for call in connection.execute.call_args_list)
    assert all('active_models' not in call.args[0] for call in connection.execute.call_args_list)
    handler.repository.get_dataset.assert_called_with(private_job['owner_user_id'], private_job['dataset_id'])


def test_rejected_target_is_valid_calculation_without_pickle(tmp_path):
    directory = tmp_path / 'attempt'
    directory.mkdir()
    manifest = prepared(directory / 'prepared', constant=True)
    owner, job_id, dataset_id, generation_id = uuid4(), uuid4(), uuid4(), uuid4()
    dataset = {'id': dataset_id, 'owner_user_id': owner, 'generation_job_id': generation_id, 'row_count': 720}
    job = {'id': job_id, 'owner_user_id': owner, 'dataset_id': dataset_id, 'job_type': 'training'}
    manifest['source'] = {'dataset_id': str(dataset_id), 'owner_user_id': str(owner), 'generation_job_id': str(generation_id)}
    (directory / 'prepared/manifest.json').write_text(json.dumps(manifest))
    train_health(directory / 'prepared', directory / 'health')
    train_rul(directory / 'prepared', directory / 'rul')
    identifier = uuid5(job_id, 'training-package-v1')
    info = build_package(directory, job, dataset, identifier)
    (directory / 'manifest.json').write_text(json.dumps(info))
    model = {'id': identifier, 'owner_user_id': owner, 'dataset_id': dataset_id, 'training_job_id': job_id,
        'model_version': info['model_version'], 'features_version': info['features_version'],
        'artifact_key': 'attempt/manifest.json'}
    result = read_training_result(tmp_path, model, job, dataset)
    assert result['eligible'] is False
    assert result['rul']['status'] == 'rejected'
    assert not (directory / 'rul/model.pkl').exists()
    assert result['rul']['diagnostics']['scatter']


def test_lock_loss_kills_child_that_ignores_termination():
    child = Mock()
    child.wait.side_effect = [subprocess.TimeoutExpired('train', 2), subprocess.TimeoutExpired('train', 5), 0]
    with patch('backend.app.services.training.subprocess.Popen', return_value=child):
        with pytest.raises(RuntimeError):
            run_child(['rul', '/source', '/output'], Mock(side_effect=RuntimeError('lost')), 0)
    child.terminate.assert_called_once()
    child.kill.assert_called_once()


def test_completed_model_is_checked_under_training_root(tmp_path):
    from unittest.mock import MagicMock
    from backend.app.services.jobs import JobService
    from backend.tests.api.test_runtime_lifecycle import settings
    generation, training = tmp_path / 'generation', tmp_path / 'training'
    generation.mkdir()
    training.mkdir()
    (training / 'manifest.json').write_text('{}')
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
        'artifact_key': 'manifest.json'}
    service = JobService(settings(), artifact_root=generation, training_artifact_root=training)
    service._verify_artifact(connection, {'job_type': 'training', 'id': uuid4(),
        'owner_user_id': uuid4(), 'dataset_id': uuid4()}, uuid4())
    assert not (generation / 'manifest.json').exists()
