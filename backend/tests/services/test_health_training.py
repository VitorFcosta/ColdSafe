import hashlib
import json
import pickle
from uuid import UUID

import numpy as np
import pytest

from backend.app.domain.features import FeatureSpec
from backend.app.domain.feature_preprocessing import FeatureTransform
from backend.app.services.feature_inputs import features_version
from backend.app.services.training_data import TARGET_DTYPE, split_equipment
from backend.app.services.health_training import train_health


def prepared(path, *, constant=False):
    path.mkdir()
    spec = FeatureSpec(sensors=('ambient_temperature_c',), windows_seconds=(2,))
    ids = tuple(str(UUID(int=i + 1)) for i in range(3))
    split = split_equipment(ids)
    transform = FeatureTransform(spec.names, np.full(4, 50.), np.zeros(4), np.full(4, 100.))
    manifest = {'storage_version': 'training-numpy-v1', 'features_version': features_version(spec),
        'sensors': list(spec.sensors), 'windows_seconds': list(spec.windows_seconds),
        'feature_names': list(spec.names), 'transform': transform.to_dict(),
        'source': {'dataset_id': str(UUID(int=42))}, 'split_seed': 42,
        'equipment_split': {part: list(values) for part, values in split.items()},
        'source_row_count': 600, 'row_count': 600, 'dropped_insufficient_history': 0,
        'partitions': {}}
    for part in split:
        (path / part).mkdir()
        x = np.linspace(0, 100, 200)
        matrix = np.repeat(x[:, None], 4, axis=1)
        targets = np.zeros(200, dtype=TARGET_DTYPE)
        targets['equipment_index'] = ids.index(split[part][0])
        targets['observed_at'] = np.datetime64('2026-01-01', 'ms') + np.arange(200) * np.timedelta64(1, 's')
        targets['health_score_true'] = 50 if constant else x
        targets['rul_hours_true'] = np.nan
        np.save(path / part / 'features.npy', matrix, allow_pickle=False)
        np.save(path / part / 'targets.npy', targets, allow_pickle=False)
        manifest['partitions'][part] = {'features': f'{part}/features.npy',
            'targets': f'{part}/targets.npy', 'row_count': 200,
            'rul_observed_rows': 0, 'rul_censored_rows': 200}
    write_manifest(path, manifest)
    return manifest


def write_manifest(path, manifest):
    (path / 'manifest.json').write_text(json.dumps(manifest, allow_nan=False))


def hashes(path):
    return {str(file.relative_to(path)): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in path.rglob('*') if file.is_file()}


def test_training_is_reproducible_private_and_keeps_source_readonly(tmp_path):
    source = tmp_path / 'prepared'
    manifest = prepared(source)
    before = hashes(source)
    a = train_health(source, tmp_path / 'a')
    b = train_health(source, tmp_path / 'b')
    assert a['status'] == b['status'] == 'eligible'
    assert a['selection'] == b['selection']
    assert a['metrics'] == b['metrics']
    assert a['diagnostics'] == b['diagnostics']
    assert a['model_sha256'] == b['model_sha256']
    assert a['diagnostics']['total_rows'] == a['diagnostics']['sample_count'] == 200
    assert [item['name'] for item in a['diagnostics']['permutation']['features']] == manifest['feature_names']
    assert a['diagnostics']['permutation']['reference_mae'] == pytest.approx(a['metrics']['test']['candidate']['mae'])
    assert a['metrics']['validation']['candidate']['mae'] < a['metrics']['validation']['baseline']['mae']
    expected_mae = float(np.mean(abs(np.linspace(0, 100, 200) - 50)))
    assert a['metrics']['validation']['baseline']['mae'] == pytest.approx(expected_mae)
    assert a['metrics']['test']['baseline']['mae'] == pytest.approx(expected_mae)
    assert a['input_hashes'] == b['input_hashes']
    assert hashes(source) == before
    assert (tmp_path / 'a').stat().st_mode & 0o777 == 0o700
    assert json.loads((tmp_path / 'a/report.json').read_text()) == a
    with (tmp_path / 'a/model.pkl').open('rb') as stream:
        bundle = pickle.load(stream)
    assert bundle['transform'].to_dict() == manifest['transform']
    assert bundle['features_version'] == manifest['features_version']
    assert a['model_sha256'] == hashlib.sha256((tmp_path / 'a/model.pkl').read_bytes()).hexdigest()


def test_constant_target_rejects_tie_and_serializes_undefined_r2(tmp_path):
    prepared(tmp_path / 'prepared', constant=True)
    report = train_health(tmp_path / 'prepared', tmp_path / 'output')
    assert report['status'] == 'rejected'
    assert report['diagnostics']['sample_count'] == 200
    assert report['diagnostics']['permutation']['reference_mae'] == 0
    assert not (tmp_path / 'output/model.pkl').exists()
    for metrics in report['metrics'].values():
        assert metrics['baseline'] == metrics['candidate'] == {'mae': 0., 'rmse': 0., 'r2': None}
    assert 'NaN' not in (tmp_path / 'output/report.json').read_text()


def test_test_labels_never_choose_candidate_or_eligibility(tmp_path):
    source = tmp_path / 'prepared'
    prepared(source)
    first = train_health(source, tmp_path / 'first')
    targets = np.load(source / 'test/targets.npy', allow_pickle=False)
    targets['health_score_true'] = 100 - targets['health_score_true']
    np.save(source / 'test/targets.npy', targets, allow_pickle=False)
    second = train_health(source, tmp_path / 'second')
    assert first['selection'] == second['selection']
    assert first['status'] == second['status']
    assert first['metrics']['validation'] == second['metrics']['validation']
    assert first['model_sha256'] == second['model_sha256']
    assert first['diagnostics'] != second['diagnostics']
    assert first['metrics']['test']['candidate']['mae'] < second['metrics']['test']['candidate']['mae']


@pytest.mark.parametrize('corruption', ['version', 'count', 'leakage', 'uuid', 'traversal', 'transform', 'nan', 'out_of_range', 'symlink'])
def test_invalid_preparation_never_produces_success_report(tmp_path, corruption):
    source = tmp_path / 'prepared'
    manifest = prepared(source)
    if corruption == 'version':
        manifest['storage_version'] = 'wrong'
    elif corruption == 'count':
        manifest['partitions']['train']['row_count'] += 1
    elif corruption == 'uuid':
        manifest['equipment_split']['test'] = manifest['equipment_split']['train']
    elif corruption == 'traversal':
        manifest['partitions']['train']['features'] = '../elsewhere.npy'
    elif corruption == 'transform':
        manifest['transform']['names'].reverse()
    elif corruption == 'symlink':
        target = source / 'train/features.npy'
        target.rename(tmp_path / 'features.npy')
        target.symlink_to(tmp_path / 'features.npy')
    else:
        path = source / 'test/targets.npy'
        targets = np.load(path, allow_pickle=False)
        if corruption == 'leakage':
            training = np.load(source / 'train/targets.npy', allow_pickle=False)
            targets['equipment_index'] = training['equipment_index'][0]
        else:
            targets['health_score_true'][0] = np.nan if corruption == 'nan' else 101
        np.save(path, targets, allow_pickle=False)
    write_manifest(source, manifest)
    with pytest.raises(ValueError):
        train_health(source, tmp_path / 'output')
    assert not (tmp_path / 'output/report.json').exists()


def test_existing_output_and_partial_failure_preserve_success_boundary(tmp_path, monkeypatch):
    from backend.app.services import health_training
    source = tmp_path / 'prepared'
    prepared(source)
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'keep').write_text('keep')
    with pytest.raises(FileExistsError):
        train_health(source, output)
    assert (output / 'keep').read_text() == 'keep'
    def fail(*args, **kwargs):
        raise RuntimeError('fit failure')
    monkeypatch.setattr(health_training.HistGradientBoostingRegressor, 'fit', fail)
    with pytest.raises(RuntimeError, match='fit failure'):
        train_health(source, tmp_path / 'partial')
    assert not (tmp_path / 'partial/report.json').exists()


def test_worse_candidate_rejects_without_publishing_model(tmp_path, monkeypatch):
    from backend.app.services import health_training
    prepared(tmp_path / 'prepared')
    monkeypatch.setattr(health_training.HistGradientBoostingRegressor, 'predict',
                        lambda self, values: np.full(len(values), -1000.))
    report = train_health(tmp_path / 'prepared', tmp_path / 'output')
    assert report['status'] == 'rejected'
    assert report['metrics']['validation']['candidate']['mae'] == pytest.approx(50.)
    assert report['metrics']['validation']['candidate']['mae'] > report['metrics']['validation']['baseline']['mae']
    assert not (tmp_path / 'output/model.pkl').exists()


def test_test_arrays_open_only_after_both_candidates_fit(tmp_path, monkeypatch):
    from backend.app.services import health_training
    prepared(tmp_path / 'prepared')
    events = []
    original_fit = health_training.HistGradientBoostingRegressor.fit
    original_partition = health_training._partition
    def fit(self, x, y):
        events.append('fit')
        return original_fit(self, x, y)
    def partition(root, manifest, part, hashes):
        events.append(part)
        return original_partition(root, manifest, part, hashes)
    monkeypatch.setattr(health_training.HistGradientBoostingRegressor, 'fit', fit)
    monkeypatch.setattr(health_training, '_partition', partition)
    train_health(tmp_path / 'prepared', tmp_path / 'output')
    assert events == ['train', 'validation', 'fit', 'fit', 'test']


def test_missing_readings_use_existing_training_transform(tmp_path):
    from backend.app.services.generation import DTYPE
    from backend.app.services.training_data import _prepare_blocks
    ids = tuple(str(UUID(int=i + 1)) for i in range(3))
    spec = FeatureSpec(sensors=('ambient_temperature_c',), windows_seconds=(2, 4))
    rows = np.zeros(300, dtype=DTYPE)
    seconds = np.tile(np.arange(100), 3)
    rows['equipment_index'] = np.repeat(np.arange(3), 100)
    rows['observed_at'] = np.datetime64('2026-01-01', 'ms') + seconds * np.timedelta64(1, 's')
    rows['ambient_temperature_c'] = seconds
    rows['ambient_temperature_c'][seconds % 5 == 0] = np.nan
    rows['health_score_true'] = 100 - seconds
    rows['rul_hours_true'] = np.nan
    manifest = _prepare_blocks([rows], len(rows), ids, tmp_path / 'prepared', spec, 42)
    report = train_health(tmp_path / 'prepared', tmp_path / 'output')
    assert report['status'] == 'eligible'
    assert report['transform'] == manifest['transform']
    state = FeatureTransform.from_dict(report['transform'])
    assert np.isfinite(state.apply(np.full((1, len(spec.names)), np.nan), spec.names)).all()


@pytest.mark.parametrize('seed', [True, -1, 2**32])
def test_invalid_training_seed_fails_before_output(tmp_path, seed):
    prepared(tmp_path / 'prepared')
    with pytest.raises(ValueError, match='seed'):
        train_health(tmp_path / 'prepared', tmp_path / 'output', seed=seed)
    assert not (tmp_path / 'output').exists()


def test_source_symlink_and_output_inside_source_fail(tmp_path):
    source = tmp_path / 'prepared'
    prepared(source)
    alias = tmp_path / 'alias'
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        train_health(alias, tmp_path / 'output')
    with pytest.raises(ValueError, match='mutate'):
        train_health(source, source / 'output')
    assert not (source / 'output').exists()


def test_r2_for_one_target_is_null_and_prediction_is_clipped():
    from backend.app.services.health_training import _evaluate
    class Model:
        def predict(self, x):
            return np.full(len(x), 1000.)
    assert _evaluate(Model(), np.zeros((1, 2)), np.array([100.])) == {'mae': 0., 'rmse': 0., 'r2': None}


def test_numerically_zero_target_variance_does_not_divide_by_zero():
    from backend.app.services.health_training import _evaluate
    class Model:
        def predict(self, x):
            return np.zeros(len(x))
    metrics = _evaluate(Model(), np.zeros((2, 1)), np.array([0., 1e-300]))
    assert metrics['r2'] is None
    assert metrics['mae'] == 5e-301


def test_shared_evaluation_can_preserve_hours_above_health_range():
    from backend.app.services.health_training import _evaluate
    class Model:
        def predict(self, x):
            return np.array([-5., 240.])
    metrics = _evaluate(Model(), np.zeros((2, 1)), np.array([0., 240.]), upper_bound=None)
    assert metrics == {'mae': 0., 'rmse': 0., 'r2': 1.}
