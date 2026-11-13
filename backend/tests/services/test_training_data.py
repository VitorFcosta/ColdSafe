from datetime import UTC, datetime, timedelta
import json
from uuid import UUID

import numpy as np
import pytest

from backend.app.domain.features import FeatureSpec
from backend.app.domain.feature_preprocessing import FeatureTransform
from backend.app.services.feature_inputs import offline_features, telemetry_features
from backend.app.services.generation import DTYPE
from backend.app.services.training_data import _prepare_blocks, split_equipment
from backend.app.services import training_data

IDS = tuple(str(UUID(int=index + 1)) for index in range(6))
SPEC = FeatureSpec(sensors=('ambient_temperature_c',), windows_seconds=(2, 4))


def readings():
    rows = np.zeros(72, dtype=DTYPE)
    rows['equipment_index'] = np.tile(np.arange(6), 12)
    seconds = np.repeat(np.arange(12), 6)
    rows['observed_at'] = np.datetime64('2026-01-01', 'ms') + seconds * np.timedelta64(1, 's')
    for sensor in DTYPE.names[2:8]:
        rows[sensor] = 5 + rows['equipment_index'] + seconds * 0.1
    rows['health_score_true'] = 90 - seconds
    rows['degradation_true'] = 1 - rows['health_score_true'] / 100
    rows['rul_observed'] = rows['equipment_index'] % 2 == 0
    rows['rul_hours_true'] = np.where(rows['rul_observed'], 11 - seconds, np.nan)
    return rows


def prepare(rows, path):
    return _prepare_blocks((rows[:13], rows[13:49], rows[49:]), len(rows), IDS, path, SPEC, 42)


def test_split_is_grouped_stable_and_seeded():
    parts = split_equipment(IDS, 42)
    assert parts == split_equipment(tuple(reversed(IDS)), 42)
    assert parts != split_equipment(IDS, 43)
    assert set(parts) == {'train', 'validation', 'test'}
    assert all(parts.values())
    assert set.union(*(set(ids) for ids in parts.values())) == set(IDS)
    assert sum(len(ids) for ids in parts.values()) == len(IDS)


@pytest.mark.parametrize('ids,seed', [(IDS[:2], 42), (IDS + IDS[:1], 42),
    (('invalid', *IDS[1:]), 42), (IDS, True), (IDS, -1), (IDS, 2**32)])
def test_split_rejects_impossible_or_invalid_input(ids, seed):
    with pytest.raises(ValueError):
        split_equipment(ids, seed)


def test_blocks_keep_history_groups_labels_and_censoring_separate(tmp_path):
    rows = readings()
    before = rows.copy()
    output = tmp_path / 'prepared'
    manifest = prepare(rows, output)
    assert manifest['source_row_count'] == 72
    assert manifest['row_count'] == 48
    assert manifest['dropped_insufficient_history'] == 24
    assert tuple(manifest['feature_names']) == SPEC.names
    assert not any(word in name for name in SPEC.names for word in ('true', 'equipment', 'observed_at', 'rul'))
    all_groups = []
    censored_health = 0
    observed_zero = 0
    for part, info in manifest['partitions'].items():
        features = np.load(output / info['features'], allow_pickle=False)
        targets = np.load(output / info['targets'], allow_pickle=False)
        assert features.shape == (info['row_count'], len(SPEC.names))
        assert np.isfinite(features).all()
        groups = {IDS[index] for index in targets['equipment_index']}
        assert groups == set(manifest['equipment_split'][part])
        all_groups.append(groups)
        censored_health += int(np.sum(~targets['rul_observed'] & np.isfinite(targets['health_score_true'])))
        observed_zero += int(np.sum(targets['rul_observed'] & (targets['rul_hours_true'] == 0)))
        assert np.isnan(targets['rul_hours_true'][~targets['rul_observed']]).all()
    assert not (all_groups[0] & all_groups[1] or all_groups[0] & all_groups[2] or all_groups[1] & all_groups[2])
    assert censored_health > 0
    assert observed_zero > 0
    for field in DTYPE.names:
        np.testing.assert_array_equal(rows[field], before[field])
    assert json.loads((output / 'manifest.json').read_text()) == manifest
    assert not (output / 'source.npy').exists()


def test_held_out_extremes_cannot_fit_transform(tmp_path):
    baseline = readings()
    changed = readings()
    training = set(split_equipment(IDS, 42)['train'])
    held_out_indices = [index for index, identifier in enumerate(IDS) if identifier not in training]
    changed['ambient_temperature_c'][np.isin(changed['equipment_index'], held_out_indices)] = 100_000
    first = prepare(baseline, tmp_path / 'first')
    second = prepare(changed, tmp_path / 'second')
    assert first['transform'] == second['transform']
    for part in ('train', 'validation', 'test'):
        state = FeatureTransform.from_dict(first['transform'])
        values = np.load(tmp_path / 'second' / second['partitions'][part]['features'], allow_pickle=False)
        assert np.all(values <= state.upper) and np.all(values >= state.lower)


def test_changing_all_labels_cannot_change_features_or_fitted_transform(tmp_path):
    original, changed = readings(), readings()
    changed['health_score_true'] = 50
    changed['degradation_true'] = 0.5
    changed['rul_observed'] = ~changed['rul_observed']
    changed['rul_hours_true'] = np.where(changed['rul_observed'], 20, np.nan)
    first = prepare(original, tmp_path / 'original')
    second = prepare(changed, tmp_path / 'changed')
    assert first['transform'] == second['transform']
    for part in first['partitions']:
        np.testing.assert_array_equal(
            np.load(tmp_path / 'original' / first['partitions'][part]['features'], allow_pickle=False),
            np.load(tmp_path / 'changed' / second['partitions'][part]['features'], allow_pickle=False))


def test_live_uses_received_time_and_matches_offline_after_saved_transform(tmp_path):
    rows = readings()
    manifest = prepare(rows, tmp_path / 'prepared')
    state = FeatureTransform.from_dict(manifest['transform'])
    history = rows[rows['equipment_index'] == 0]
    expected = offline_features(history, SPEC)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    events = [{'schema_version': 3, 'type': 'telemetry',
        'occurred_at': '2099-01-01T00:00:00Z',
        'received_at': (start + timedelta(seconds=index)).isoformat(),
        'data': {'equipment': {'equipment_id': IDS[0]}, 'measurements': {
            'ambient_temperature': {'unit': 'degC', 'value': float(row['ambient_temperature_c'])}}}}
        for index, row in enumerate(history)]
    actual = telemetry_features(events, IDS[0], (start + timedelta(seconds=11)).isoformat(), state, SPEC)
    assert actual.sufficient.tolist() == [True]
    np.testing.assert_array_equal(actual.values, state.apply(expected.values[-1:], SPEC.names))
    # A future event and labels on unrelated fields cannot change the accepted history.
    events[-1]['data']['measurements']['ambient_temperature']['value'] = 100_000
    events[-1]['data']['health_score_true'] = -100_000
    np.testing.assert_array_equal(telemetry_features(events, IDS[0],
        (start + timedelta(seconds=11)).isoformat(), state, SPEC).values, actual.values)


def test_insufficient_live_history_is_not_imputed_as_available(tmp_path):
    manifest = prepare(readings(), tmp_path / 'prepared')
    state = FeatureTransform.from_dict(manifest['transform'])
    result = telemetry_features([], IDS[0], '2026-01-01T00:00:00Z', state, SPEC)
    assert result.sufficient.tolist() == [False]
    assert np.isnan(result.values).all()


def test_impossible_history_all_missing_and_existing_output_fail(tmp_path):
    rows = readings()
    with pytest.raises(ValueError):
        _prepare_blocks([rows[:6]], 6, IDS, tmp_path / 'sparse', SPEC, 42)
    rows['ambient_temperature_c'] = np.nan
    with pytest.raises(ValueError, match='missing'):
        prepare(rows, tmp_path / 'missing')
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'keep.txt').write_text('preserve')
    with pytest.raises(FileExistsError):
        prepare(readings(), output)
    assert (output / 'keep.txt').read_text() == 'preserve'


def test_private_preparation_reuses_reader_before_accessing_blocks(tmp_path, monkeypatch):
    from uuid import uuid4
    rows = readings()
    source = tmp_path / 'source'
    source.mkdir()
    np.save(source / 'block.npy', rows, allow_pickle=False)
    (source / 'manifest.json').write_text(json.dumps({'blocks': [{'file': 'block.npy'}],
        'equipment': [{'id': identifier} for identifier in IDS]}))
    owner, identifier, job_id = uuid4(), uuid4(), uuid4()
    dataset = {'id': identifier, 'owner_user_id': owner, 'generation_job_id': job_id,
               'artifact_key': 'source/manifest.json'}
    job = {'id': job_id, 'status': 'completed', 'job_type': 'generation',
           'result_id': identifier, 'owner_user_id': owner}
    calls = []
    def validated(root, candidate, origin):
        calls.append((root, candidate, origin))
        return {'row_count': len(rows), 'config': {'sensor_types': list(SPEC.sensors)}}, {}
    monkeypatch.setattr(training_data, 'read_dataset', validated)
    result = training_data.prepare_dataset(tmp_path, dataset, job, tmp_path / 'prepared', spec=SPEC)
    assert calls == [(tmp_path, dataset, job)]
    assert result['source'] == {'dataset_id': str(identifier), 'owner_user_id': str(owner),
                                'generation_job_id': str(job_id)}
    with pytest.raises(ValueError, match='sensors'):
        training_data.prepare_dataset(tmp_path, dataset, job, tmp_path / 'mismatch',
            spec=FeatureSpec(sensors=('vibration_rms_mm_s',)))
    calls.clear()
    with pytest.raises(ValueError, match='owner-linked'):
        training_data.prepare_dataset(tmp_path, dataset, job | {'owner_user_id': uuid4()}, tmp_path / 'foreign')
    assert calls == []


@pytest.mark.parametrize('bad_rows,count', [
    (np.zeros(2), 2), (readings(), 71), (readings()[:12], 72),
])
def test_invalid_source_block_or_count_fails_without_success_manifest(tmp_path, bad_rows, count):
    output = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        _prepare_blocks([bad_rows], count, IDS, output, SPEC, 42)
    assert not (output / 'manifest.json').exists()


@pytest.mark.parametrize('value', ['2026-01-01T00:00:00', '2026-01-01T01:00:00+01:00', 42])
def test_live_rejects_non_utc_cutoff(tmp_path, value):
    manifest = prepare(readings(), tmp_path / 'prepared')
    with pytest.raises(ValueError):
        telemetry_features([], IDS[0], value, FeatureTransform.from_dict(manifest['transform']), SPEC)


def test_adapters_reject_mixed_equipment_units_layout_and_boolean_measurements(tmp_path):
    with pytest.raises(ValueError, match='one equipment'):
        offline_features(readings(), SPEC)
    with pytest.raises(ValueError, match='structured'):
        offline_features(np.zeros(2), SPEC)
    manifest = prepare(readings(), tmp_path / 'prepared')
    state = FeatureTransform.from_dict(manifest['transform'])
    event = {'schema_version': 3, 'type': 'telemetry', 'received_at': '2026-01-01T00:00:00Z',
        'data': {'equipment': {'equipment_id': IDS[0]}, 'measurements': {
            'ambient_temperature': {'unit': 'degC', 'value': 5.0}}}}
    event['data']['equipment']['equipment_id'] = IDS[1]
    with pytest.raises(ValueError, match='one equipment'):
        telemetry_features([event], IDS[0], '2026-01-01T00:00:05Z', state, SPEC)
    event['data']['equipment']['equipment_id'] = IDS[0]
    event['data']['measurements']['ambient_temperature']['unit'] = 'F'
    with pytest.raises(ValueError, match='measurement/unit'):
        telemetry_features([event], IDS[0], '2026-01-01T00:00:05Z', state, SPEC)
    event['data']['measurements']['ambient_temperature'] = {'unit': 'degC', 'value': True}
    with pytest.raises(ValueError, match='measurement/unit'):
        telemetry_features([event], IDS[0], '2026-01-01T00:00:05Z', state, SPEC)
    with pytest.raises(ValueError, match='layout'):
        telemetry_features([], IDS[0], '2026-01-01T00:00:05Z', state, FeatureSpec())
