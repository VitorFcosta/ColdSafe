from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest

from backend.app.api.auth import AuthService
from backend.app.api.jobs import create_jobs_router
from backend.app.security.tokens import SessionPrincipal
from backend.tests.api.test_runtime_lifecycle import settings


@pytest.fixture
def api():
    owner = uuid4()
    principal = SessionPrincipal(uuid4(), owner, 'admin@example.test', 'admin',
                                 datetime.now(UTC) + timedelta(hours=1))
    auth = AuthService(settings())
    auth.session_for_token = Mock(return_value=principal)
    now = datetime.now(UTC)
    job = {'id': uuid4(), 'job_type': 'generation', 'status': 'queued',
           'owner_user_id': owner, 'config': {'job_type': 'generation', 'total_units': 1_000_000},
           'completed_units': 0, 'total_units': 1_000_000, 'result_id': None,
           'error_code': None, 'created_at': now, 'updated_at': now,
           'environment_id': None, 'dataset_id': None}
    service = Mock()
    service.create.return_value = job
    service.get.return_value = job
    app = FastAPI()
    app.include_router(create_jobs_router(auth, service))
    auth.install_exception_handlers(app)
    return TestClient(app), auth, service, principal, job


HEADERS = {'Authorization': 'Bearer test'}


def test_generation_is_accepted_without_executing_heavy_work(api):
    client, _, service, principal, job = api
    response = client.post('/api/v3/jobs', headers=HEADERS,
                           json={'job_type': 'generation', 'total_units': 1_000_000})
    assert response.status_code == 202
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json()['data']['id'] == str(job['id'])
    assert response.json()['data']['status'] == 'queued'
    assert response.json()['meta']['schema_version'] == 3
    from backend.app.domain.jobs import GenerationInput
    service.create.assert_called_once_with(principal.user_id, GenerationInput(**{
        'job_type': 'generation', 'total_units': 1_000_000, 'seed': 42, 'environment_id': None,
    }).model_dump())
    assert [call[0] for call in service.mock_calls] == ['create']


def test_training_passes_only_validated_ids(api):
    client, _, service, principal, _ = api
    dataset, environment = uuid4(), uuid4()
    response = client.post('/api/v3/jobs', headers=HEADERS, json={
        'job_type': 'training', 'dataset_id': str(dataset), 'environment_id': str(environment),
    })
    assert response.status_code == 202
    service.create.assert_called_once_with(principal.user_id, {
        'job_type': 'training', 'dataset_id': dataset, 'environment_id': environment,
    })


@pytest.mark.parametrize('role,expected', [(None, 401), ('viewer', 403), ('operator', 403)])
def test_only_admin_can_create_jobs(api, role, expected):
    client, auth, service, principal, _ = api
    auth.session_for_token.return_value = (SessionPrincipal(
        principal.session_id, principal.user_id, principal.email, role, principal.expires_at,
    ) if role else None)
    response = client.post('/api/v3/jobs', headers=HEADERS if role else {},
                           json={'job_type': 'generation', 'total_units': 1_000_000})
    assert response.status_code == expected
    service.create.assert_not_called()


@pytest.mark.parametrize('payload', [
    {'job_type': 'generation', 'total_units': 999_999},
    {'job_type': 'generation', 'total_units': 2_000_001},
    {'job_type': 'generation', 'total_units': '1000000'},
    {'job_type': 'generation', 'total_units': 1_000_000.0},
    {'job_type': 'generation', 'total_units': True},
    {'job_type': 'generation', 'total_units': 1_000_000, 'seed': -1},
    {'job_type': 'generation', 'total_units': 1_000_000, 'seed': 2**32},
    {'job_type': 'generation', 'total_units': 1_000_000, 'seed': True},
    {'job_type': 'generation', 'total_units': 1_000_000, 'seed': '42'},
    {'job_type': 'generation', 'total_units': 1_000_000, 'owner_user_id': str(uuid4())},
    {'job_type': 'generation', 'total_units': 1_000_000, 'environment_id': 'invalid'},
    {'job_type': 'training'},
    {'job_type': 'training', 'dataset_id': 'invalid'},
    {'job_type': 'training', 'dataset_id': str(uuid4()), 'total_units': 2},
    {'job_type': 'unknown'},
])
def test_job_parameters_reject_coercion_unknown_fields_and_unsafe_limits(api, payload):
    client, _, service, _, _ = api
    assert client.post('/api/v3/jobs', headers=HEADERS, json=payload).status_code == 422
    service.create.assert_not_called()


@pytest.mark.parametrize('total,seed', [(1_000_000, 0), (2_000_000, 2**32 - 1)])
def test_generation_accepts_boundary_values(api, total, seed):
    client, _, _, _, _ = api
    assert client.post('/api/v3/jobs', headers=HEADERS, json={
        'job_type': 'generation', 'total_units': total, 'seed': seed,
    }).status_code == 202


def test_read_is_private_and_uncached_even_for_viewer(api):
    client, auth, service, principal, job = api
    auth.session_for_token.return_value = SessionPrincipal(
        principal.session_id, principal.user_id, principal.email, 'viewer', principal.expires_at,
    )
    response = client.get(f'/api/v3/jobs/{job["id"]}', headers=HEADERS)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    service.get.assert_called_once_with(principal.user_id, job['id'])


@pytest.mark.parametrize('suffix', ['', '/events'])
def test_foreign_job_returns_404_and_does_not_leak_progress(api, suffix):
    client, _, service, principal, job = api
    service.get.return_value = None
    response = client.get(f'/api/v3/jobs/{job["id"]}{suffix}', headers=HEADERS)
    assert response.status_code == 404
    assert str(job['id']) not in response.text
    service.get.assert_called_once_with(principal.user_id, job['id'])


@pytest.mark.parametrize('suffix', ['', '/events'])
def test_reads_require_bearer_not_query_token(api, suffix):
    client, _, service, _, job = api
    response = client.get(f'/api/v3/jobs/{job["id"]}{suffix}?token=test')
    assert response.status_code == 401
    service.get.assert_not_called()


def test_sse_emits_current_persisted_progress_and_closes_on_revocation(api):
    client, auth, service, principal, job = api
    auth.session_for_token.side_effect = [principal, principal, None]
    with patch('backend.app.api.jobs.asyncio.sleep', new_callable=AsyncMock) as sleep:
        response = client.get(f'/api/v3/jobs/{job["id"]}/events', headers=HEADERS)
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/event-stream')
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.text.count('event: job_progress') == 1
    assert str(job['id']) in response.text
    assert 'test' not in response.text
    assert auth.session_for_token.call_count == 3
    assert all(call.args[0] == principal.user_id for call in service.get.call_args_list)
    sleep.assert_awaited_once_with(1)


def test_sse_emits_only_changed_progress_and_finishes_with_persisted_result(api):
    client, _, service, _, job = api
    finished = {**job, 'status': 'completed', 'completed_units': job['total_units'],
                'result_id': uuid4(), 'updated_at': job['updated_at'] + timedelta(seconds=1)}
    service.get.side_effect = [job, job, job, finished]
    with patch('backend.app.api.jobs.asyncio.sleep', new_callable=AsyncMock):
        response = client.get(f'/api/v3/jobs/{job["id"]}/events', headers=HEADERS)
    assert response.text.count('event: job_progress') == 2
    assert str(finished['result_id']) in response.text


def test_sse_stops_when_job_ownership_is_lost(api):
    client, _, service, _, job = api
    service.get.side_effect = [job, None]
    response = client.get(f'/api/v3/jobs/{job["id"]}/events', headers=HEADERS)
    assert response.status_code == 200
    assert response.text == ''


def test_sse_reports_database_outage_without_exposing_connection_details(api):
    client, _, service, _, job = api
    service.get.side_effect = [job, psycopg.OperationalError('private credentials')]
    response = client.get(f'/api/v3/jobs/{job["id"]}/events', headers=HEADERS)
    assert response.status_code == 200
    assert 'event: error' in response.text
    assert 'DEPENDENCY_UNAVAILABLE' in response.text
    assert 'private credentials' not in response.text


@pytest.mark.parametrize('method,path', [('get', '/api/v3/jobs/{id}'), ('post', '/api/v3/jobs')])
def test_rest_database_outage_returns_sanitized_503(api, method, path):
    client, _, service, _, job = api
    service.get.side_effect = service.create.side_effect = psycopg.OperationalError('private credentials')
    response = getattr(client, method)(path.format(id=job['id']), headers=HEADERS,
                                       **({'json': {'job_type': 'generation', 'total_units': 1_000_000}} if method == 'post' else {}))
    assert response.status_code == 503
    assert 'private credentials' not in response.text


def test_sse_sends_keepalive_while_waiting_for_durable_progress(api):
    client, auth, _, principal, job = api
    auth.session_for_token.side_effect = [principal] * 17 + [None]
    with patch('backend.app.api.jobs.asyncio.sleep', new_callable=AsyncMock):
        response = client.get(f'/api/v3/jobs/{job["id"]}/events', headers=HEADERS)
    assert response.text.count('event: job_progress') == 1
    assert response.text.count(': keep-alive') == 1
