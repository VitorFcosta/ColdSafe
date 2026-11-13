from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
import psycopg
import pytest

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.models import create_models_router
from backend.app.runtime import build_runtime_app
from backend.app.security.tokens import SessionPrincipal
from backend.app.services.training_results import TrainingResultUnavailable
from backend.tests.api.test_runtime_lifecycle import settings


HEADERS = {'Authorization': 'Bearer test'}


@pytest.fixture
def api():
    principal = SessionPrincipal(uuid4(), uuid4(), 'admin@example.test', 'admin',
                                 datetime.now(UTC) + timedelta(hours=1))
    auth = AuthService(settings())
    auth.session_for_token = Mock(return_value=principal)
    model = {'id': uuid4(), 'version': 'private-version', 'eligible': True}
    activation = {'id': uuid4(), 'model_id': model['id'], 'status': 'ready'}
    service = Mock()
    service.request.return_value = service.get.return_value = activation
    service.active.return_value = model
    service.list_models.return_value = [model]
    app = create_app(repository=Mock(), readiness_check=lambda: True)
    auth.install_exception_handlers(app)
    app.include_router(create_models_router(auth, service))
    return TestClient(app), auth, service, principal, model, activation


def test_admin_requests_durable_activation_without_running_loader(api):
    client, _, service, principal, model, activation = api
    response = client.post('/api/v3/model-activations', headers=HEADERS,
                           json={'model_id': str(model['id'])})
    assert response.status_code == 202
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json() == {'success': True, 'data': {
        'id': str(activation['id']), 'model_id': str(model['id']), 'status': 'ready',
    }, 'meta': {'schema_version': 3}}
    service.request.assert_called_once_with(principal.user_id, model['id'])
    assert [call[0] for call in service.mock_calls] == ['request']


@pytest.mark.parametrize('payload', [
    {}, {'model_id': 'invalid'}, {'model_id': 3},
    {'model_id': str(uuid4()), 'owner_user_id': str(uuid4())},
    {'model_id': str(uuid4()), 'artifact_path': '/tmp/untrusted'},
])
def test_activation_rejects_untrusted_parameters(api, payload):
    client, _, service, *_ = api
    assert client.post('/api/v3/model-activations', headers=HEADERS,
                       json=payload).status_code == 422
    service.request.assert_not_called()


@pytest.mark.parametrize('role,expected', [(None, 401), ('viewer', 403), ('operator', 403)])
def test_activation_requires_current_admin(api, role, expected):
    client, auth, service, principal, model, _ = api
    auth.session_for_token.return_value = (SessionPrincipal(
        principal.session_id, principal.user_id, principal.email, role, principal.expires_at,
    ) if role else None)
    response = client.post('/api/v3/model-activations', headers=HEADERS,
                           json={'model_id': str(model['id'])})
    assert response.status_code == expected
    service.request.assert_not_called()


@pytest.mark.parametrize('path,method', [
    ('/api/v3/models', 'list_models'), ('/api/v3/models/active', 'active'),
    ('/api/v3/model-activations/{id}', 'get'),
])
def test_reads_are_private_and_uncached_for_viewer(api, path, method):
    client, auth, service, principal, _, activation = api
    auth.session_for_token.return_value = SessionPrincipal(
        principal.session_id, principal.user_id, principal.email, 'viewer', principal.expires_at,
    )
    response = client.get(path.format(id=activation['id']), headers=HEADERS)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json()['meta'] == {'schema_version': 3}
    getattr(service, method).assert_called_once_with(
        principal.user_id, *([activation['id']] if method == 'get' else []),
    )


@pytest.mark.parametrize('path', ['/api/v3/models', '/api/v3/models/active',
                                  '/api/v3/model-activations/{id}'])
@pytest.mark.parametrize('revoked', [False, True])
def test_model_reads_require_live_bearer_session(api, path, revoked):
    client, auth, service, _, _, activation = api
    if revoked:
        auth.session_for_token.return_value = None
    response = client.get(path.format(id=activation['id']) + '?token=test',
                          headers=HEADERS if revoked else {})
    assert response.status_code == 401
    assert service.mock_calls == []


def test_foreign_activation_returns_non_disclosing_404(api):
    client, _, service, principal, _, activation = api
    service.get.return_value = None
    response = client.get(f'/api/v3/model-activations/{activation["id"]}', headers=HEADERS)
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'MODEL_ACTIVATION_NOT_FOUND'
    assert str(activation['id']) not in response.text
    service.get.assert_called_once_with(principal.user_id, activation['id'])


def test_no_active_model_returns_null(api):
    client, _, service, *_ = api
    service.active.return_value = None
    assert client.get('/api/v3/models/active', headers=HEADERS).json()['data'] is None


@pytest.mark.parametrize('code,status', [('MODEL_NOT_FOUND', 404),
    ('MODEL_NOT_ELIGIBLE', 409), ('ACTIVATION_PENDING', 409)])
def test_rejected_candidates_have_visible_error(api, code, status):
    client, _, service, _, model, _ = api
    service.request.side_effect = HTTPException(status, code)
    response = client.post('/api/v3/model-activations', headers=HEADERS,
                           json={'model_id': str(model['id'])})
    assert response.status_code == status
    assert response.json()['error']['code'] == code


@pytest.mark.parametrize('method,path,operation', [
    ('post', '/api/v3/model-activations', 'request'),
    ('get', '/api/v3/model-activations/{id}', 'get'),
    ('get', '/api/v3/models/active', 'active'), ('get', '/api/v3/models', 'list_models'),
])
@pytest.mark.parametrize('error,code', [
    (psycopg.OperationalError('private credentials'), 'DEPENDENCY_UNAVAILABLE'),
    (TrainingResultUnavailable('private artifact path'), 'TRAINING_RESULT_UNAVAILABLE'),
])
def test_unavailable_services_return_sanitized_503(api, method, path, operation, error, code):
    client, _, service, _, model, activation = api
    getattr(service, operation).side_effect = error
    response = getattr(client, method)(path.format(id=activation['id']), headers=HEADERS,
        **({'json': {'model_id': str(model['id'])}} if method == 'post' else {}))
    assert response.status_code == 503
    assert response.json()['error']['code'] == code
    assert 'private credentials' not in response.text
    assert 'private artifact path' not in response.text


def test_model_publisher_shares_lifecycle_and_router_service():
    configured = settings().model_copy(update={'rabbitmq_api_password': SecretStr('private-api')})
    started, stopped = Event(), Event()

    def publish(shutdown):
        started.set()
        shutdown.wait(5)
        if shutdown.is_set():
            stopped.set()

    with patch('backend.app.runtime.MqttSubscriber'), patch('backend.app.runtime.create_influx_repository'), \
            patch('backend.app.runtime.initialize_schema'), \
            patch('backend.app.services.commands.CommandService.expire_pending'), \
            patch('backend.app.amqp.jobs.JobPublisher'), \
            patch('backend.app.amqp.models.ModelPublisher') as publisher, \
            patch('backend.app.services.models.ModelService') as service, \
            patch('backend.app.api.models.create_models_router', wraps=create_models_router) as router:
        publisher.return_value.run.side_effect = publish
        app = build_runtime_app(configured)
        with TestClient(app) as client:
            assert started.wait(2)
            assert '/api/v3/model-activations' in client.get('/openapi.json').json()['paths']
        assert stopped.is_set()
        publisher.return_value.close.assert_called_once_with()
        assert router.call_args.args[1] is service.return_value
        assert publisher.call_args.args[0] is service.return_value
        assert publisher.call_args.kwargs['role'] == 'api'
        service.assert_called_once_with(configured, artifact_root=configured.training_artifact_root)


def test_model_routes_remain_optional_without_api_credential():
    with patch('backend.app.runtime.MqttSubscriber'), patch('backend.app.runtime.create_influx_repository'):
        app = build_runtime_app(settings())
    paths = app.openapi()['paths']
    assert '/api/v3/models' not in paths
    assert '/api/v3/model-activations' not in paths
