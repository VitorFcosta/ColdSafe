from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

import numpy as np
import pytest

from backend.app.domain.jobs import GenerationInput
from backend.app.services.datasets import DatasetUnavailable, read_dataset
from backend.app.services.generation import write_dataset
from backend.app.services.jobs import public_job


@pytest.fixture(scope='module')
def generated(tmp_path_factory):
    root = tmp_path_factory.mktemp('datasets')
    identifier, owner, job_id = uuid4(), uuid4(), uuid4()
    config = GenerationInput(job_type='generation', total_units=1_000_000,
                             sensor_types=['vibration_rms_mm_s'], missing_rate=1)
    manifest = write_dataset(root / 'attempt', identifier, config, lambda _: None)
    dataset = dict(id=identifier, owner_user_id=owner, generation_job_id=job_id,
                   row_count=config.total_units, artifact_key='attempt/manifest.json',
                   created_at=datetime.now(UTC))
    job = dict(id=job_id, owner_user_id=owner, status='completed', job_type='generation',
               result_id=identifier, total_units=config.total_units,
               config=config.model_dump(mode='json'), environment_id=None)
    return root, manifest, dataset, job


def test_summary_and_separate_sample_are_bounded_and_match_selected_sensors(generated):
    root, _, dataset, job = generated
    summary, sample = read_dataset(root, dataset, job)
    assert summary['row_count'] == 1_000_000
    assert summary['config'] == job['config']
    assert summary['owner_user_id'] == dataset['owner_user_id']
    assert summary['quality']['missing_by_sensor'] == {'vibration_rms_mm_s': 1_000_000}
    assert summary['quality']['range_by_sensor'] == {'vibration_rms_mm_s': {'min': None, 'max': None}}
    assert sum(summary['quality'][key] for key in ('rul_observed_rows', 'rul_censored_rows')) == 1_000_000
    assert summary['units'] == {'vibration_rms_mm_s': 'mm/s'}
    assert 'rows' not in summary
    assert sample['dataset_id'] == dataset['id']
    assert len(sample['rows']) == 10
    assert all(row['measurements'] == {'vibration_rms_mm_s': None} for row in sample['rows'])
    assert all(0 <= row['degradation_true'] <= 1 for row in sample['rows'])
    json.dumps(sample, default=str, allow_nan=False)


@pytest.mark.parametrize('change', [
    {'dataset_id': str(uuid4())}, {'row_count': 999999}, {'schema_version': 2},
    {'storage_version': 'unknown'}, {'units': {}}, {'config': {}}, {'blocks': []},
    {'equipment': []}, {'block_size': 2_000_000},
])
def test_rejects_inconsistent_manifest(generated, change):
    root, manifest, dataset, job = generated
    changed = json.loads(manifest.read_text()) | change
    alternate = root / f'{uuid4()}.json'
    alternate.write_text(json.dumps(changed))
    try:
        with pytest.raises(DatasetUnavailable):
            read_dataset(root, dataset | {'artifact_key': alternate.name}, job)
    finally:
        alternate.unlink()


@pytest.mark.parametrize('key', ['../escape.json', '/tmp/escape.json', 'missing.json'])
def test_rejects_external_or_missing_paths(generated, key):
    root, _, dataset, job = generated
    with pytest.raises(DatasetUnavailable):
        read_dataset(root, dataset | {'artifact_key': key}, job)


def test_rejects_symlink_manifest(generated):
    root, manifest, dataset, job = generated
    link = root / 'link.json'
    link.symlink_to(manifest)
    with pytest.raises(DatasetUnavailable):
        read_dataset(root, dataset | {'artifact_key': link.name}, job)


def test_rejects_corrupt_block_without_leaking_paths(generated):
    root, manifest, dataset, job = generated
    original = json.loads(manifest.read_text())
    changed = json.loads(manifest.read_text())
    changed['blocks'][0]['sha256'] = '0' * 64
    manifest.write_text(json.dumps(changed))
    try:
        with pytest.raises(DatasetUnavailable) as error:
            read_dataset(root, dataset, job)
        assert str(root) not in str(error.value)
    finally:
        manifest.write_text(json.dumps(original))


def test_public_job_exposes_author_and_complete_persisted_generation_config(generated):
    _, _, dataset, job = generated
    row = job | {'config': {'seed': 42}, 'completed_units': 1_000_000,
                 'result_dataset_id': dataset['id'], 'result_model_id': None,
                 'dataset_id': None, 'error_code': None, 'created_at': dataset['created_at'],
                 'updated_at': dataset['created_at']}
    result = public_job(row)
    assert result['owner_user_id'] == row['owner_user_id']
    assert result['config']['total_units'] == row['total_units']
    assert result['config']['job_type'] == 'generation'
    assert result['config']['environment_id'] is None
    assert result['config']['seed'] == 42
    assert result['config']['equipment_count'] == 100


@pytest.mark.parametrize('corruption', ['dtype', 'infinity', 'equipment', 'censor', 'timestamp', 'health'])
def test_rejects_invalid_numpy_schema_and_values_even_with_matching_checksum(generated, corruption):
    root, manifest, dataset, job = generated
    metadata = json.loads(manifest.read_text())
    block = manifest.parent / metadata['blocks'][0]['file']
    original = block.read_bytes()
    data = np.load(block, allow_pickle=False)
    if corruption == 'dtype':
        data = np.zeros(len(data), dtype=f'V{data.dtype.itemsize}')
    elif corruption == 'infinity':
        data['vibration_rms_mm_s'][0] = np.inf
    elif corruption == 'equipment':
        data['equipment_index'][0] = -1
    elif corruption == 'censor':
        data['rul_observed'][0] = False
        data['rul_hours_true'][0] = 10
    elif corruption == 'timestamp':
        data['observed_at'][0] = np.datetime64('NaT', 'ms')
    else:
        data['health_score_true'][0] = 101
    with block.open('wb') as stream:
        np.save(stream, data, allow_pickle=False)
    changed = json.loads(manifest.read_text())
    changed['blocks'][0]['sha256'] = hashlib.sha256(block.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(changed))
    try:
        with pytest.raises(DatasetUnavailable):
            read_dataset(root, dataset, job)
    finally:
        block.write_bytes(original)
        manifest.write_text(json.dumps(metadata))


def test_measured_range_ignores_missing_values(generated):
    root, manifest, dataset, job = generated
    metadata = json.loads(manifest.read_text())
    block = manifest.parent / metadata['blocks'][0]['file']
    original = block.read_bytes()
    data = np.load(block, allow_pickle=False)
    data['vibration_rms_mm_s'][0] = 1.5
    with block.open('wb') as stream:
        np.save(stream, data, allow_pickle=False)
    changed = json.loads(manifest.read_text())
    changed['blocks'][0]['sha256'] = hashlib.sha256(block.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(changed))
    try:
        summary, sample = read_dataset(root, dataset, job)
        assert summary['quality']['missing_by_sensor'] == {'vibration_rms_mm_s': 999_999}
        assert summary['quality']['range_by_sensor'] == {'vibration_rms_mm_s': {'min': 1.5, 'max': 1.5}}
        assert sample['rows'][0]['measurements'] == {'vibration_rms_mm_s': 1.5}
    finally:
        block.write_bytes(original)
        manifest.write_text(json.dumps(metadata))


def test_rejects_oversized_and_deeply_nested_manifest(generated):
    root, manifest, dataset, job = generated
    alternate = root / 'invalid.json'
    try:
        for content in (' ' * (4 * 1_048_576 + 1), '[' * 2000 + ']' * 2000):
            alternate.write_text(content)
            with pytest.raises(DatasetUnavailable):
                read_dataset(root, dataset | {'artifact_key': alternate.name}, job)
    finally:
        alternate.unlink()


@pytest.mark.parametrize('corruption', ['npz', 'invalid_zip'])
def test_rejects_npz_block_even_with_matching_hash(generated, corruption):
    root, manifest, dataset, job = generated
    metadata = json.loads(manifest.read_text())
    block = manifest.parent / metadata['blocks'][0]['file']
    original = block.read_bytes()
    with block.open('wb') as stream:
        if corruption == 'npz':
            np.savez(stream, rows=np.zeros(50_000, dtype='V85'))
        else:
            stream.write(b'PK\x03\x04' + b'\0' * (len(original) - 4))
    changed = json.loads(manifest.read_text())
    changed['blocks'][0]['sha256'] = hashlib.sha256(block.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(changed))
    try:
        with pytest.raises(DatasetUnavailable):
            read_dataset(root, dataset, job)
    finally:
        block.write_bytes(original)
        manifest.write_text(json.dumps(metadata))


def test_rejects_symlink_block(generated):
    root, manifest, dataset, job = generated
    block = manifest.parent / 'block-0000.npy'
    moved = manifest.parent / 'original.npy'
    block.rename(moved)
    block.symlink_to(moved)
    try:
        with pytest.raises(DatasetUnavailable):
            read_dataset(root, dataset, job)
    finally:
        block.unlink()
        moved.rename(block)


def test_manifest_accepts_maximum_configured_equipment_count(tmp_path):
    identifier = uuid4()
    config = GenerationInput(job_type='generation', total_units=1_000_000, equipment_count=10_000)
    manifest = write_dataset(tmp_path / 'max-equipment', identifier, config, lambda _: None)
    dataset = dict(id=identifier, owner_user_id=uuid4(), generation_job_id=uuid4(),
                   artifact_key=str(manifest.relative_to(tmp_path)), row_count=config.total_units,
                   created_at=datetime.now(UTC))
    job = dict(config=config.model_dump(mode='json'), environment_id=None, total_units=config.total_units)
    assert manifest.stat().st_size > 1_048_576
    summary, sample = read_dataset(tmp_path, dataset, job)
    assert summary['config']['equipment_count'] == 10_000
    assert len(sample['rows']) == 10
