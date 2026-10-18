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
from backend.app.services.rul_training import train_rul


def prepared(path, *, constant=False, no_near_failure=False):
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
        'source_row_count': 720, 'row_count': 720, 'dropped_insufficient_history': 0,
        'partitions': {}}
    for part in split:
        (path / part).mkdir()
        x = np.arange(240, dtype=float)
        matrix = np.repeat(x[:, None], 4, axis=1)
        targets = np.zeros(240, dtype=TARGET_DTYPE)
        targets['equipment_index'] = ids.index(split[part][0])
        targets['observed_at'] = np.datetime64('2026-01-01', 'ms') + np.arange(240) * np.timedelta64(1, 's')
        targets['health_score_true'] = np.minimum(x, 100)
        targets['rul_observed'] = x < 200
        targets['rul_hours_true'] = 80 if constant else x * 2 + (100 if no_near_failure else 0)
        targets['rul_hours_true'][~targets['rul_observed']] = np.nan
        np.save(path / part / 'features.npy', matrix, allow_pickle=False)
        np.save(path / part / 'targets.npy', targets, allow_pickle=False)
        manifest['partitions'][part] = {'features': f'{part}/features.npy',
            'targets': f'{part}/targets.npy', 'row_count': 240,
            'rul_observed_rows': 200, 'rul_censored_rows': 40}
    write_manifest(path, manifest)
    return manifest


def write_manifest(path, manifest):
    (path / 'manifest.json').write_text(json.dumps(manifest, allow_nan=False))


def hashes(path):
    return {str(file.relative_to(path)): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in path.rglob('*') if file.is_file()}


def mutate_targets(source, part, update):
    path = source / part / 'targets.npy'
    targets = np.load(path, allow_pickle=False)
    update(targets)
    np.save(path, targets, allow_pickle=False)


def test_observed_only_baseline_reproduction_units_and_private_artifacts(tmp_path):
    source = tmp_path / 'prepared'
    manifest = prepared(source)
    before = hashes(source)
    a = train_rul(source, tmp_path / 'a')
    b = train_rul(source, tmp_path / 'b')
    assert a['status'] == b['status'] == 'eligible'
    assert a['metrics'] == b['metrics']
    assert a['selection'] == b['selection']
    assert a['diagnostics'] == b['diagnostics']
    assert a['diagnostics']['total_rows'] == a['diagnostics']['sample_count'] == 200
    assert max(point['actual'] for point in a['diagnostics']['scatter']) == 398
    assert max(point['predicted'] for point in a['diagnostics']['scatter']) > 300
    assert [item['name'] for item in a['diagnostics']['permutation']['features']] == manifest['feature_names']
    assert a['diagnostics']['permutation']['reference_mae'] == pytest.approx(a['metrics']['test']['candidate']['mae'])
    assert a['model_sha256'] == b['model_sha256']
    assert a['baseline']['training_mean'] == 199
    assert a['target'] == 'rul_hours_true'
    assert a['unit'] == 'hours'
    assert a['prediction_range'] == [0, None]
    assert a['partition_rows'] == {part: {'full': 240, 'observed': 200, 'censored': 40} for part in ('train', 'validation', 'test')}
    assert a['input_hashes'] == before
    assert hashes(source) == before
    assert (tmp_path / 'a').stat().st_mode & 0o777 == 0o700
    assert json.loads((tmp_path / 'a/report.json').read_text()) == a
    with (tmp_path / 'a/model.pkl').open('rb') as stream:
        bundle = pickle.load(stream)
    assert bundle['target'] == 'rul_hours_true'
    assert bundle['unit'] == 'hours'
    assert bundle['prediction_range'] == (0, None)
    assert bundle['transform'].to_dict() == manifest['transform']
    model = bundle['model']
    predictions = np.maximum(model.predict(np.array([[0.] * 4, [190.] * 4])), 0)
    assert 0 <= predictions[0] < 24
    assert predictions[1] > 300
    assert a['near_failure']['threshold_hours'] == 24
    for part in ('validation', 'test'):
        near = a['near_failure'][part]
        assert near['row_count'] == 13  # RUL zero and the inclusive 24-hour boundary remain observed.
        assert near['baseline']['mae'] == 187
        assert near['candidate']['mae'] < near['baseline']['mae']
        assert a['metrics'][part]['candidate']['mae'] < a['metrics'][part]['baseline']['mae']


def test_fit_uses_only_observed_rows_and_opens_test_after_selection(tmp_path, monkeypatch):
    from backend.app.services import rul_training
    source = tmp_path / 'prepared'
    prepared(source)
    events = []
    original_fit = rul_training.HistGradientBoostingRegressor.fit
    original_baseline = rul_training.DummyRegressor.fit
    original_partition = rul_training._rul_partition
    def fit(self, x, y):
        events.append('candidate')
        assert len(y) == 200 and np.isfinite(y).all() and y[0] == 0
        assert np.max(x) == 199
        return original_fit(self, x, y)
    def baseline(self, x, y):
        events.append('baseline')
        assert len(y) == 200 and y[0] == 0
        return original_baseline(self, x, y)
    def partition(root, manifest, part, hashes):
        events.append(part)
        return original_partition(root, manifest, part, hashes)
    monkeypatch.setattr(rul_training.HistGradientBoostingRegressor, 'fit', fit)
    monkeypatch.setattr(rul_training.DummyRegressor, 'fit', baseline)
    monkeypatch.setattr(rul_training, '_rul_partition', partition)
    train_rul(source, tmp_path / 'out')
    assert events == ['train', 'validation', 'baseline', 'candidate', 'candidate', 'test']


def test_test_targets_do_not_influence_selection(tmp_path):
    source = tmp_path / 'prepared'
    prepared(source)
    first = train_rul(source, tmp_path / 'first')
    def reverse(y):
        observed = y['rul_observed']
        y['rul_hours_true'][observed] = 398 - y['rul_hours_true'][observed]
    mutate_targets(source, 'test', reverse)
    second = train_rul(source, tmp_path / 'second')
    assert first['selection'] == second['selection']
    assert first['status'] == second['status']
    assert first['metrics']['validation'] == second['metrics']['validation']
    assert first['model_sha256'] == second['model_sha256']
    assert first['diagnostics'] != second['diagnostics']
    assert first['metrics']['test']['candidate']['mae'] < second['metrics']['test']['candidate']['mae']


def test_tie_rejects_without_model_and_empty_near_failure_is_explicit(tmp_path):
    source = tmp_path / 'prepared'
    prepared(source, constant=True)
    report = train_rul(source, tmp_path / 'output')
    assert report['status'] == 'rejected'
    assert report['diagnostics']['sample_count'] == 200
    assert report['diagnostics']['permutation']['reference_mae'] == 0
    assert not (tmp_path / 'output/model.pkl').exists()
    for part in ('validation', 'test'):
        assert report['metrics'][part]['candidate'] == {'mae': 0., 'rmse': 0., 'r2': None}
        assert report['near_failure'][part] == {'row_count': 0, 'baseline': None, 'candidate': None}


def test_worse_candidate_rejected_and_negative_predictions_clamped(tmp_path, monkeypatch):
    from backend.app.services import rul_training
    prepared(tmp_path / 'prepared')
    monkeypatch.setattr(rul_training.HistGradientBoostingRegressor, 'predict',
                        lambda self, x: np.full(len(x), -1000.))
    report = train_rul(tmp_path / 'prepared', tmp_path / 'output')
    assert report['status'] == 'rejected'
    assert report['metrics']['validation']['candidate']['mae'] == 199
    assert not (tmp_path / 'output/model.pkl').exists()


@pytest.mark.parametrize('part', ['train', 'validation', 'test'])
@pytest.mark.parametrize('observed,value', [(True, np.nan), (True, np.inf), (True, -1.),
                                         (False, 0.), (False, 500.), (False, np.inf)])
def test_invalid_rul_labels_never_publish_report(tmp_path, part, observed, value):
    source = tmp_path / 'prepared'
    prepared(source)
    def update(y):
        y['rul_hours_true'][0 if observed else 239] = value
    mutate_targets(source, part, update)
    with pytest.raises(ValueError, match='RUL'):
        train_rul(source, tmp_path / 'output')
    assert not (tmp_path / 'output/report.json').exists()


@pytest.mark.parametrize('part', ['train', 'validation', 'test'])
def test_partition_without_observed_failures_is_explicit_error(tmp_path, part):
    source = tmp_path / 'prepared'
    manifest = prepared(source)
    def update(y):
        y['rul_observed'] = False
        y['rul_hours_true'] = np.nan
    mutate_targets(source, part, update)
    manifest['partitions'][part].update(rul_observed_rows=0, rul_censored_rows=240)
    write_manifest(source, manifest)
    with pytest.raises(ValueError, match='observed'):
        train_rul(source, tmp_path / 'output')
    assert not (tmp_path / 'output/report.json').exists()


@pytest.mark.parametrize('leaking_part', ['validation', 'test'])
def test_censored_machine_still_detects_equipment_leakage(tmp_path, leaking_part):
    source = tmp_path / 'prepared'
    manifest = prepared(source)
    ids = tuple(str(UUID(int=i + 1)) for i in range(20))
    split = split_equipment(ids)
    manifest['equipment_split'] = {part: list(values) for part, values in split.items()}
    for part in split:
        def update(y, part=part):
            y['equipment_index'][y['rul_observed']] = ids.index(split[part][0])
            censored_id = split['train'][1] if part == leaking_part else split[part][1]
            y['equipment_index'][~y['rul_observed']] = ids.index(censored_id)
        mutate_targets(source, part, update)
    write_manifest(source, manifest)
    with pytest.raises(ValueError, match='Equipment leakage'):
        train_rul(source, tmp_path / 'output')
    assert not (tmp_path / 'output/report.json').exists()


@pytest.mark.parametrize('corruption', ['metadata', 'missing_key', 'health', 'features', 'symlink', 'layout', 'count'])
def test_shared_prepared_validation_remains_enforced(tmp_path, corruption):
    source = tmp_path / 'prepared'
    manifest = prepared(source)
    if corruption == 'metadata':
        manifest['storage_version'] = 'wrong'
    elif corruption == 'missing_key':
        del manifest['transform']
    elif corruption == 'health':
        mutate_targets(source, 'train', lambda y: y['health_score_true'].__setitem__(0, np.nan))
    elif corruption == 'features':
        x = np.load(source / 'train/features.npy', allow_pickle=False)
        x[0, 0] = np.inf
        np.save(source / 'train/features.npy', x, allow_pickle=False)
    elif corruption == 'symlink':
        path = source / 'train/targets.npy'
        path.rename(tmp_path / 'targets.npy')
        path.symlink_to(tmp_path / 'targets.npy')
    elif corruption == 'layout':
        np.save(source / 'train/targets.npy', np.zeros(240), allow_pickle=False)
    else:
        manifest['partitions']['train'].update(rul_observed_rows=199, rul_censored_rows=41)
    write_manifest(source, manifest)
    with pytest.raises(ValueError):
        train_rul(source, tmp_path / 'output')
    assert not (tmp_path / 'output/report.json').exists()


@pytest.mark.parametrize('seed', [True, -1, 2**32])
def test_invalid_seed_rejected_before_creating_destination(tmp_path, seed):
    prepared(tmp_path / 'prepared')
    with pytest.raises(ValueError, match='seed'):
        train_rul(tmp_path / 'prepared', tmp_path / 'output', seed=seed)
    assert not (tmp_path / 'output').exists()


def test_existing_destination_and_partial_failure_preserve_boundary(tmp_path, monkeypatch):
    from backend.app.services import rul_training
    source = tmp_path / 'prepared'
    prepared(source)
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'keep').write_text('keep')
    with pytest.raises(FileExistsError):
        train_rul(source, output)
    assert (output / 'keep').read_text() == 'keep'
    def fail(*args, **kwargs):
        raise RuntimeError('fit failure')
    monkeypatch.setattr(rul_training.HistGradientBoostingRegressor, 'fit', fail)
    with pytest.raises(RuntimeError, match='fit failure'):
        train_rul(source, tmp_path / 'partial')
    assert not (tmp_path / 'partial/report.json').exists()


def test_source_alias_and_destination_inside_source_are_rejected(tmp_path):
    source = tmp_path / 'prepared'
    prepared(source)
    alias = tmp_path / 'alias'
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        train_rul(alias, tmp_path / 'output')
    with pytest.raises(ValueError, match='mutate'):
        train_rul(source, source / 'output')
    assert not (source / 'output').exists()
