import json
import pickle
import shutil
from unittest.mock import patch

import numpy as np
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor

from backend.app.services.health_training import _sha256
from backend.app.services.model_bundle import load_model_bundle, ModelBundleUnavailable
from backend.tests.services.test_training import package


def test_loads_private_pair_with_identity_and_training_transform(package):
    root, model, job, dataset = package
    bundle = load_model_bundle(root, model, job, dataset)
    assert bundle.model_id == model['id']
    assert bundle.model_version == model['model_version']
    assert bundle.features_version == model['features_version']
    assert bundle.units == {'health': 'points', 'rul': 'hours'}
    row = bundle.transform.apply(np.full((1, len(bundle.spec.names)), np.nan), bundle.spec.names)
    assert np.isfinite(bundle.health.predict(row)).all()
    assert np.isfinite(bundle.rul.predict(row)).all()


@pytest.fixture
def copied(package, tmp_path):
    root, model, job, dataset = package
    shutil.copytree(root / 'attempt', tmp_path / 'attempt')
    return tmp_path, model, job, dataset


def refresh_report(directory, target, report):
    path = directory / target / 'report.json'
    path.write_text(json.dumps(report))
    manifest = directory / 'manifest.json'
    package = json.loads(manifest.read_text())
    package['reports'][target]['sha256'] = _sha256(path)
    package['reports'][target]['model_sha256'] = report['model_sha256']
    manifest.write_text(json.dumps(package))


@pytest.mark.parametrize('library', ['python', 'numpy', 'sklearn', 'scipy', 'joblib', 'threadpoolctl', 'narwhals', 'cloudpickle'])
def test_incompatible_runtime_rejected_before_pickle(copied, library):
    root, model, job, dataset = copied
    for target in ('health', 'rul'):
        report = json.loads((root / 'attempt' / target / 'report.json').read_text())
        report['versions'][library] = '0.0.0'
        refresh_report(root / 'attempt', target, report)
    with patch('backend.app.services.model_bundle.pickle.loads') as deserialize:
        with pytest.raises(ModelBundleUnavailable, match='^Model bundle unavailable$'):
            load_model_bundle(root, model, job, dataset)
    deserialize.assert_not_called()


def test_python_patch_release_remains_compatible(copied):
    root, model, job, dataset = copied
    for target in ('health', 'rul'):
        report = json.loads((root / 'attempt' / target / 'report.json').read_text())
        report['versions']['python'] = '.'.join(report['versions']['python'].split('.')[:2] + ['999'])
        refresh_report(root / 'attempt', target, report)
    assert load_model_bundle(root, model, job, dataset).model_id == model['id']


@pytest.mark.parametrize('damage', ['missing', 'hash', 'symlink', 'absent_version', 'baseline_regression'])
def test_incomplete_or_rejected_candidate_never_deserializes(copied, damage):
    root, model, job, dataset = copied
    directory = root / 'attempt'
    path = directory / 'health/model.pkl'
    if damage == 'missing':
        path.unlink()
    elif damage == 'hash':
        path.write_bytes(b'broken')
    elif damage == 'symlink':
        stored = directory / 'health/original.pkl'
        path.rename(stored)
        path.symlink_to(stored)
    elif damage == 'absent_version':
        model = model | {'artifact_key': 'missing/manifest.json'}
    else:
        report = json.loads((directory / 'health/report.json').read_text())
        report['status'] = 'rejected'
        report['model_sha256'] = None
        report['metrics']['validation']['candidate']['mae'] = report['metrics']['validation']['baseline']['mae'] + 1
        path.unlink()
        refresh_report(directory, 'health', report)
    with patch('backend.app.services.model_bundle.pickle.loads') as deserialize:
        with pytest.raises(ModelBundleUnavailable, match='^Model bundle unavailable$'):
            load_model_bundle(root, model, job, dataset)
    deserialize.assert_not_called()


@pytest.mark.parametrize('damage', ['pickle', 'payload_type', 'unexpected_key', 'estimator', 'spec',
    'transform', 'feature_version', 'range', 'target', 'unit', 'columns', 'parameters', 'not_fitted'])
def test_pickle_contract_is_checked_even_with_valid_hash(copied, damage):
    root, model, job, dataset = copied
    directory = root / 'attempt'
    target = 'rul' if damage in ('target', 'unit') else 'health'
    path = directory / target / 'model.pkl'
    payload = pickle.loads(path.read_bytes())
    if damage == 'payload_type':
        payload = []
    elif damage == 'unexpected_key':
        payload['extra'] = True
    elif damage == 'estimator':
        payload['model'] = DummyRegressor()
    elif damage == 'spec':
        object.__setattr__(payload['spec'], 'windows_seconds', (1,))
    elif damage == 'transform':
        object.__setattr__(payload['transform'], 'medians', np.full(len(payload['spec'].names), np.nan))
    elif damage == 'feature_version':
        payload['features_version'] = 'other'
    elif damage == 'range':
        payload['prediction_range'] = (0, None)
    elif damage == 'target':
        payload['target'] = 'health_score_true'
    elif damage == 'unit':
        payload['unit'] = 'days'
    elif damage == 'columns':
        payload['model'].n_features_in_ = 999
    elif damage == 'parameters':
        payload['model'].max_iter = 1
    elif damage == 'not_fitted':
        payload['model'] = HistGradientBoostingRegressor(**payload['model'].get_params())
    path.write_bytes(b'broken' if damage == 'pickle' else pickle.dumps(payload))
    report = json.loads((directory / target / 'report.json').read_text())
    report['model_sha256'] = _sha256(path)
    refresh_report(directory, target, report)
    with pytest.raises(ModelBundleUnavailable, match='^Model bundle unavailable$'):
        load_model_bundle(root, model, job, dataset)


@pytest.mark.parametrize('prediction', [np.array([np.nan]), np.array([np.inf]), np.array([1, 2])])
def test_smoke_prediction_rejects_unusable_estimator(package, prediction):
    with patch.object(HistGradientBoostingRegressor, 'predict', return_value=prediction):
        with pytest.raises(ModelBundleUnavailable):
            load_model_bundle(*package)


def test_changed_pickle_after_json_validation_is_rejected(copied):
    from backend.app.services.training_results import read_training_result
    root, model, job, dataset = copied
    def validate(*args):
        result = read_training_result(*args)
        (root / 'attempt/health/model.pkl').write_bytes(b'changed')
        return result
    with patch('backend.app.services.model_bundle.read_training_result', side_effect=validate), \
            patch('backend.app.services.model_bundle.pickle.loads') as deserialize:
        with pytest.raises(ModelBundleUnavailable):
            load_model_bundle(root, model, job, dataset)
    deserialize.assert_not_called()
