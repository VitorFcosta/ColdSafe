"""Local inference cannot reach the internet; only weight preparation can."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_ollama_is_bounded_cpu_private_and_offline_with_persistent_weights():
    overlay = yaml.safe_load((ROOT / 'compose.ollama.yaml').read_text())
    runtime = overlay['services']['ollama']
    assert runtime['image'] == 'ollama/ollama:0.40.3'
    assert runtime['networks'] == ['coldsafe-llm']
    assert overlay['networks']['coldsafe-llm']['internal'] is True
    assert runtime['environment']['OLLAMA_NO_CLOUD'] == '1'
    assert runtime['environment']['OLLAMA_NUM_PARALLEL'] == '1'
    assert runtime['environment']['OLLAMA_MAX_LOADED_MODELS'] == '1'
    assert runtime['environment']['OLLAMA_CONTEXT_LENGTH'] == '1024'
    assert runtime['mem_limit'] == '3328m' and runtime['cpus'] == 4.0
    assert runtime['volumes'] == ['ollama-data:/models:ro']
    assert runtime['read_only'] is True
    assert not {'ports', 'devices', 'gpus', 'privileged'} & runtime.keys()
    assert 'ollama-data' in overlay['volumes']


def test_only_explicit_preparation_can_download_weights_and_has_no_private_data():
    overlay = yaml.safe_load((ROOT / 'compose.ollama.yaml').read_text())
    setup = overlay['services']['ollama-prepare']
    assert setup['profiles'] == ['llm-setup']
    assert setup['networks'] == ['coldsafe-llm-download']
    assert not overlay['networks']['coldsafe-llm-download'].get('internal', False)
    assert setup['restart'] == 'no'
    assert setup['volumes'] == ['ollama-data:/models', './infra/ollama/prepare.sh:/prepare.sh:ro']
    assert set(setup['environment']) == {'OLLAMA_MODELS', 'OLLAMA_HOST', 'OLLAMA_NO_CLOUD'}
    assert not {'ports', 'depends_on', 'secrets', 'env_file'} & setup.keys()
    script = (ROOT / 'infra/ollama/prepare.sh').read_text()
    assert 'ollama pull llama3.2:3b-instruct-q4_K_M' in script
    assert 'trap ' in script


def test_all_heavy_workers_and_coordinator_share_private_ollama_configuration():
    overlay = yaml.safe_load((ROOT / 'compose.ollama.yaml').read_text())
    for name in ('backend', 'generation', 'training', 'llm'):
        service = overlay['services'][name]
        assert service['environment']['OLLAMA_URL'] == 'http://ollama:11434'
        assert 'coldsafe-llm' in service['networks']
    coordinator = overlay['services']['llm']
    assert coordinator['command'] == ['python', '-m', 'backend.app.llm_worker']
    assert coordinator['extends'] == {'file': 'compose.yaml', 'service': 'backend'}
    assert coordinator['mem_limit'] == '128m'
    assert coordinator['environment']['COLDSAFE_HEALTHCHECK'] == '1'
    assert coordinator['healthcheck']['test'] == ['CMD', 'python', '-m', 'simulator.health', '240']
    assert coordinator['healthcheck']['start_period'] == '240s'
