from unittest.mock import patch

import pytest

from backend.tests.api.test_jobs_api import api, HEADERS


def test_datasets_list_is_private_bounded_metadata(api):
    client, _, service, principal, _ = api
    service.repository.list_datasets.return_value = []
    response = client.get('/api/v3/datasets', headers=HEADERS)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json() == {'success': True, 'data': [], 'meta': {'schema_version': 3}}
    service.repository.list_datasets.assert_called_once_with(principal.user_id)


@pytest.mark.parametrize('status,expected', [('queued', 409), ('running', 409), ('failed', 409)])
def test_training_result_waits_for_completed_owned_job(api, status, expected):
    client, _, service, _, job = api
    service.get.return_value = job | {'job_type': 'training', 'status': status}
    with patch('backend.app.api.jobs.read_training_result') as read:
        response = client.get(f'/api/v3/jobs/{job["id"]}/result', headers=HEADERS)
    assert response.status_code == expected
    read.assert_not_called()


def test_result_checks_owner_before_files_or_model(api):
    client, _, service, _, job = api
    service.get.return_value = None
    with patch('backend.app.api.jobs.read_training_result') as read:
        assert client.get(f'/api/v3/jobs/{job["id"]}/result', headers=HEADERS).status_code == 404
    service.repository.get_model.assert_not_called()
    read.assert_not_called()


def test_result_requires_auth(api):
    client, _, service, _, job = api
    assert client.get(f'/api/v3/jobs/{job["id"]}/result').status_code == 401
    service.get.assert_not_called()


def test_completed_result_is_private_and_sanitizes_corruption(api):
    from uuid import uuid4
    from backend.app.services.training_results import TrainingResultUnavailable
    client, _, service, principal, job = api
    dataset_id, model_id = uuid4(), uuid4()
    service.get.return_value = job | {'job_type': 'training', 'status': 'completed',
        'result_id': model_id, 'dataset_id': dataset_id}
    service.repository.get_model.return_value = {'id': model_id, 'owner_user_id': principal.user_id,
        'dataset_id': dataset_id, 'training_job_id': job['id']}
    service.repository.get_dataset.return_value = {'id': dataset_id, 'owner_user_id': principal.user_id}
    with patch('backend.app.api.jobs.read_training_result', side_effect=TrainingResultUnavailable('private/pickle')):
        response = client.get(f'/api/v3/jobs/{job["id"]}/result', headers=HEADERS)
    assert response.status_code == 503
    assert 'private/pickle' not in response.text
    with patch('backend.app.api.jobs.read_training_result', return_value={'eligible': False}):
        response = client.get(f'/api/v3/jobs/{job["id"]}/result', headers=HEADERS)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json()['data']['eligible'] is False


def test_result_rechecks_model_links_before_reading_disk(api):
    from uuid import uuid4
    client, _, service, _, job = api
    service.get.return_value = job | {'job_type': 'training', 'status': 'completed'}
    service.repository.get_model.return_value = {'owner_user_id': uuid4()}
    with patch('backend.app.api.jobs.read_training_result') as read:
        assert client.get(f'/api/v3/jobs/{job["id"]}/result', headers=HEADERS).status_code == 404
    read.assert_not_called()


@pytest.mark.parametrize('role', ['viewer', 'operator'])
def test_training_submission_requires_admin(api, role):
    from backend.app.security.tokens import SessionPrincipal
    from uuid import uuid4
    client, auth, service, principal, _ = api
    auth.session_for_token.return_value = SessionPrincipal(
        principal.session_id, principal.user_id, principal.email, role, principal.expires_at)
    response = client.post('/api/v3/jobs', headers=HEADERS,
        json={'job_type': 'training', 'dataset_id': str(uuid4())})
    assert response.status_code == 403
    service.create.assert_not_called()
