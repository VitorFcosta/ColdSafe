import json
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.domain.jobs import GenerationInput
from backend.app.services.generation import BLOCK_SIZE, MEASUREMENTS, generate_block, write_dataset


def config(**values):
    return GenerationInput(job_type='generation', total_units=1_000_000, **values)


@pytest.mark.parametrize('values', [
    {'equipment_count': 0}, {'equipment_count': 10001}, {'equipment_count': True},
    {'days': 0}, {'days': float('nan')}, {'days': float('inf')}, {'days': '30'},
    {'failure_fraction': -0.1}, {'failure_fraction': 1.1}, {'noise_scale': -1},
    {'missing_rate': 1.1}, {'outlier_rate': -1}, {'sensor_types': []},
    {'sensor_types': ['unknown']}, {'sensor_types': ['humidity_percent'] * 2},
    {'failure_modes': []}, {'failure_modes': ['electrical']},
    {'operating_modes': ['invalid']}, {'operating_modes': ['normal', 'normal']},
])
def test_generation_parameters_are_bounded_and_closed(values):
    with pytest.raises(ValidationError):
        config(**values)


def test_seed_reproduces_measurements_and_labels_but_other_seed_changes_them():
    first = generate_block(config(), 0)
    same = generate_block(config(), 0)
    changed = generate_block(config(seed=43), 0)
    assert len(first) == BLOCK_SIZE == 50_000
    for name in first.dtype.names:
        np.testing.assert_array_equal(first[name], same[name])
    assert not np.array_equal(first['motor_current_a'], changed['motor_current_a'])


def test_censorship_and_observed_failure_have_correct_rul_and_progressive_wear():
    c = config(noise_scale=0, missing_rate=0, outlier_rate=0)
    first = generate_block(c, 0)
    last = generate_block(c, 19)
    observed = last['rul_observed']
    assert observed.any() and (~observed).any()
    assert np.isnan(last['rul_hours_true'][~observed]).all()
    assert (last['rul_hours_true'][observed] >= 0).all()
    assert (last['rul_hours_true'][-c.equipment_count:][observed[-c.equipment_count:]] == 0).all()
    assert np.all(last['health_score_true'] < first['health_score_true'])
    for name in ('vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c', 'ambient_temperature_c'):
        assert np.mean(last[name]) > np.mean(first[name])
    assert (last['degradation_true'] >= 0).all() and (last['degradation_true'] <= 1).all()


def test_missing_sensors_noise_outliers_daily_cycle_and_modes_affect_data():
    dirty = generate_block(config(missing_rate=0.1, outlier_rate=0.1), 0)
    clean = generate_block(config(missing_rate=0, outlier_rate=0, noise_scale=0), 0)
    assert 0.08 < np.isnan(dirty['motor_current_a']).mean() < 0.12
    assert np.nanmax(np.abs(dirty['motor_current_a'] - clean['motor_current_a'])) > 10
    only = generate_block(config(sensor_types=['humidity_percent']), 0)
    assert all(np.isnan(only[name]).all() for name in MEASUREMENTS if name != 'humidity_percent')
    normal = generate_block(config(operating_modes=['normal'], missing_rate=0, outlier_rate=0), 0)
    heavy = generate_block(config(operating_modes=['heavy'], missing_rate=0, outlier_rate=0), 0)
    assert heavy['motor_current_a'].mean() > normal['motor_current_a'].mean()
    assert np.ptp(clean['humidity_percent'][::100]) > 5
    # Heterogeneity and noise must overlap adjacent health bands, not expose perfect classes.
    a = dirty['vibration_rms_mm_s'][dirty['health_score_true'] > 99]
    b = dirty['vibration_rms_mm_s'][dirty['health_score_true'] < 99]
    assert np.nanpercentile(a, 90) > np.nanpercentile(b, 10)


@pytest.mark.parametrize('fraction,expected', [(0, False), (1, True)])
def test_failure_fraction_extremes(fraction, expected):
    data = generate_block(config(failure_fraction=fraction), 19)
    assert np.all(data['rul_observed'] == expected)


def test_blocks_cover_non_divisible_equipment_and_last_partial_block():
    c = GenerationInput(job_type='generation', total_units=1_000_003, equipment_count=137)
    last = generate_block(c, 20)
    assert len(last) == 3
    assert (last['equipment_index'] < 137).all()
    with pytest.raises(ValueError):
        generate_block(c, 21)


def test_dataset_is_durable_counted_and_each_logical_row_matches_offline_schema(tmp_path):
    identifier = uuid4()
    progress = []
    path = write_dataset(tmp_path / 'dataset', identifier, config(), progress.append)
    manifest = json.loads(path.read_text())
    assert manifest['row_count'] == sum(b['row_count'] for b in manifest['blocks']) == 1_000_000
    assert manifest['dataset_id'] == str(identifier)
    assert progress == list(range(BLOCK_SIZE, 1_000_001, BLOCK_SIZE))
    schema = json.loads(open('contracts/aiot.schema.json').read())
    validator = Draft202012Validator({**schema, '$ref': '#/$defs/offline_row'}, format_checker=FormatChecker())
    for block in (manifest['blocks'][0], manifest['blocks'][-1]):
        data = np.load(path.parent / block['file'], allow_pickle=False)
        for row in data[:100]:
            number = lambda x: None if np.isnan(x) else float(x)
            logical = {'schema_version': 3, 'dataset_id': str(identifier),
                'equipment_id': manifest['equipment'][int(row['equipment_index'])]['id'],
                'observed_at': str(row['observed_at']) + 'Z',
                'measurements': {k: number(row[k]) for k in MEASUREMENTS},
                'labels': {k: number(row[k]) for k in ('health_score_true', 'rul_hours_true', 'degradation_true')} |
                          {'rul_observed': bool(row['rul_observed'])}}
            validator.validate(logical)


def test_write_failure_never_publishes_manifest_and_replay_never_regresses_progress(tmp_path, monkeypatch):
    def fail(*_, **__):
        raise OSError('disk full')
    monkeypatch.setattr(np, 'save', fail)
    with pytest.raises(OSError):
        write_dataset(tmp_path / 'broken', uuid4(), config(), lambda _: pytest.fail('premature progress'))
    assert not (tmp_path / 'broken' / 'manifest.json').exists()
    monkeypatch.undo()
    progress = []
    write_dataset(tmp_path / 'replay', uuid4(), config(), progress.append, completed_units=950_000)
    assert progress == [950_000] * 19 + [1_000_000]


def test_replay_checks_coordination_connection_after_each_durable_block(tmp_path):
    def disconnected(completed):
        assert completed == 950_000
        raise ConnectionError('coordinator lost')
    with pytest.raises(ConnectionError):
        write_dataset(tmp_path / 'replay', uuid4(), config(), disconnected, completed_units=950_000)
    assert len(list((tmp_path / 'replay').glob('*.npy'))) == 1
    assert not (tmp_path / 'replay' / 'manifest.json').exists()
