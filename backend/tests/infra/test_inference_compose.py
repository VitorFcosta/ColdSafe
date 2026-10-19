"""Inference opts into the existing bounded model service, without another process."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_inference_overlay_reuses_private_models_service_and_readonly_catalog():
    overlay = yaml.safe_load((ROOT / 'compose.inference.yaml').read_text())
    assert set(overlay['services']) == {'models'}
    worker = overlay['services']['models']
    assert worker['command'] == ['python', '-m', 'backend.app.inference_worker']
    assert worker['environment'] == {
        'AIOT_CATALOG_PATH': '/catalog/catalog.json',
        'AIOT_OWNER_USER_ID': '${GATEWAY_OWNER_USER_ID:?Preencha o proprietario do catalogo AIoT}',
    }
    assert worker['volumes'] == [{'type': 'bind',
        'source': '${SIMULATOR_CATALOG_DIR:-./simulator/local}', 'target': '/catalog',
        'read_only': True, 'bind': {'create_host_path': False}}]
    base = yaml.safe_load((ROOT / 'compose.jobs.yaml').read_text())['services']['models']
    assert base['volumes'] == ['training-artifacts:/app/training-artifacts:ro']
    assert base['mem_limit'] == '512m' and base['cpus'] == 1.0
    assert 'RABBITMQ_INFERENCE_PASSWORD' in base['environment']
    assert not {'build', 'ports', 'networks', 'mem_limit'} & set(worker)
