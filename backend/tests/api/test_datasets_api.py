from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest

from backend.app.api.auth import AuthService
from backend.app.api.jobs import create_jobs_router
from backend.app.security.tokens import SessionPrincipal
from backend.app.services.datasets import DatasetUnavailable
from backend.tests.api.test_runtime_lifecycle import settings

HEADERS = {'Authorization': 'Bearer test'}


@pytest.fixture
def api(tmp_path):
    owner, dataset_id, job_id = uuid4(), uuid4(), uuid4()
    auth = AuthService(settings())
    auth.session_for_token = Mock(return_value=SessionPrincipal(
        uuid4(), owner, 'viewer@example.test', 'viewer', datetime.now(UTC) + timedelta(hours=1)))
    service = Mock(artifact_root=tmp_path)
    dataset = {'id': dataset_id, 'owner_user_id': owner, 'generation_job_id': job_id}
    service.repository.get_dataset.return_value = dataset
    service.get.return_value = {'id': job_id, 'owner_user_id': owner, 'job_type': 'generation',
                                'status': 'completed', 'result_id': dataset_id}
    app = FastAPI()
    app.include_router(create_jobs_router(auth, service))
    auth.install_exception_handlers(app)
    return TestClient(app), auth, service, dataset


@pytest.mark.parametrize('suffix', ['', '/sample'])
def test_dataset_reads_require_bearer_and_never_read_files_unauthenticated(api, suffix):
    client, _, service, dataset = api
    response = client.get(f'/api/v3/datasets/{dataset["id"]}{suffix}?token=test')
    assert response.status_code == 401
    service.repository.get_dataset.assert_not_called()


@pytest.mark.parametrize('suffix', ['', '/sample'])
@pytest.mark.parametrize('failure', ['missing', 'foreign', 'running', 'wrong_result', 'wrong_type', 'missing_job'])
def test_unowned_or_incomplete_dataset_is_404_before_artifact_read(api, suffix, failure):
    client, _, service, dataset = api
    if failure == 'missing':
        service.repository.get_dataset.return_value = None
    elif failure == 'foreign':
        dataset['owner_user_id'] = uuid4()
    elif failure == 'running':
        service.get.return_value['status'] = 'running'
    elif failure == 'wrong_result':
        service.get.return_value['result_id'] = uuid4()
    elif failure == 'wrong_type':
        service.get.return_value['job_type'] = 'training'
    else:
        service.get.return_value = None
    with patch('backend.app.api.jobs.read_dataset') as reader:
        response = client.get(f'/api/v3/datasets/{dataset["id"]}{suffix}', headers=HEADERS)
    assert response.status_code == 404
    reader.assert_not_called()


@pytest.mark.parametrize('suffix,index', [('', 0), ('/sample', 1)])
def test_completed_dataset_and_sample_have_private_separate_envelopes(api, suffix, index):
    client, _, service, dataset = api
    outputs = ({'id': str(dataset['id']), 'row_count': 1_000_000},
               {'dataset_id': str(dataset['id']), 'rows': []})
    with patch('backend.app.api.jobs.read_dataset', return_value=outputs) as reader:
        response = client.get(f'/api/v3/datasets/{dataset["id"]}{suffix}', headers=HEADERS)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json() == {'success': True, 'data': outputs[index], 'meta': {'schema_version': 3}}
    reader.assert_called_once_with(service.artifact_root, dataset, service.get.return_value)
    service.repository.get_dataset.assert_called_once_with(dataset['owner_user_id'], dataset['id'])


@pytest.mark.parametrize('suffix', ['', '/sample'])
def test_corrupt_artifact_is_sanitized_503(api, suffix):
    client, _, _, dataset = api
    with patch('backend.app.api.jobs.read_dataset', side_effect=DatasetUnavailable()):
        response = client.get(f'/api/v3/datasets/{dataset["id"]}{suffix}', headers=HEADERS)
    assert response.status_code == 503
    assert 'DATASET_UNAVAILABLE' in response.text
    assert 'artifact_root' not in response.text


def test_dataset_database_failure_is_sanitized(api):
    client, _, service, dataset = api
    service.repository.get_dataset.side_effect = psycopg.OperationalError('private credentials')
    response = client.get(f'/api/v3/datasets/{dataset["id"]}', headers=HEADERS)
    assert response.status_code == 503
    assert 'DEPENDENCY_UNAVAILABLE' in response.text
    assert 'private credentials' not in response.text
