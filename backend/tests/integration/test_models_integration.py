"""B2-24: real private registry, atomic swaps and durable broker delivery."""
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4, uuid5

from fastapi import HTTPException
import pytest
from psycopg.types.json import Jsonb

from backend.app.repositories.postgres import connect, initialize_schema
from backend.app.services.models import ModelService
from backend.app.services.training_results import build_package, read_training_result
from backend.tests.integration.test_aiot_migrations_integration import database
from backend.tests.infra.test_rabbitmq_integration import broker, connect as amqp_connect
from backend.tests.services.test_training import package

pytestmark = pytest.mark.integration


@pytest.fixture
def registry(database, package, tmp_path):
    initialize_schema(database)
    root, original, job, dataset = package
    owner = job['owner_user_id']
    stranger = uuid4()
    with connect(database) as conn:
        for identifier in (owner, stranger):
            conn.execute("INSERT INTO users(id,email,password_hash,role) VALUES(%s,%s,'test','admin')",
                         (identifier, f'{identifier}@example.invalid'))
        conn.execute("INSERT INTO jobs(id,owner_user_id,job_type,total_units) VALUES(%s,%s,'generation',720)",
                     (dataset['generation_job_id'], owner))
        conn.execute("INSERT INTO datasets(id,owner_user_id,generation_job_id,name,features_version,row_count) "
                     "VALUES(%s,%s,%s,'fixture',%s,720)",
                     (dataset['id'], owner, dataset['generation_job_id'], original['features_version']))
        conn.execute("UPDATE jobs SET status='completed',completed_units=720,result_dataset_id=%s WHERE id=%s",
                     (dataset['id'], dataset['generation_job_id']))
    service = ModelService(database, artifact_root=tmp_path / 'models')
    service.artifact_root.mkdir()

    def register():
        current = job | {'id': uuid4(), 'status': 'completed'}
        identifier = uuid5(current['id'], 'training-package-v1')
        directory = service.artifact_root / str(identifier)
        shutil.copytree(root / 'attempt', directory)
        info = build_package(directory, current, dataset, identifier)
        (directory / 'manifest.json').write_text(json.dumps(info))
        model = original | {'id': identifier, 'training_job_id': current['id'],
            'model_version': info['model_version'], 'artifact_key': f'{identifier}/manifest.json'}
        result = read_training_result(service.artifact_root, model, current, dataset)
        metrics = {'eligible': result['eligible'], **{target: {
            'status': result[target]['status'], 'metrics': result[target]['metrics']}
            for target in ('health', 'rul')}}
        with connect(database) as conn:
            conn.execute("INSERT INTO jobs(id,owner_user_id,job_type,dataset_id,total_units) "
                         "VALUES(%s,%s,'training',%s,2)", (current['id'], owner, dataset['id']))
            conn.execute('INSERT INTO models(id,owner_user_id,dataset_id,training_job_id,model_version,'
                         'features_version,artifact_key,metrics) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                         (identifier, owner, dataset['id'], current['id'], model['model_version'],
                          model['features_version'], model['artifact_key'], Jsonb(metrics)))
            conn.execute("UPDATE jobs SET status='completed',completed_units=2,result_model_id=%s WHERE id=%s",
                         (identifier, current['id']))
        return model, directory

    return service, database, owner, stranger, register


def test_atomic_pair_activation_rollback_and_private_status(registry):
    service, config, owner, stranger, register = registry
    first, _ = register()
    second, _ = register()
    assert service.active(owner) is None
    assert len(service.list_models(owner)) == 2
    assert service.list_models(stranger) == []
    activation = service.request(owner, first['id'])
    assert activation['status'] == 'ready' and service.active(owner) is None
    assert service.get(stranger, activation['id']) is None
    assert service.execute(activation['id'])
    assert service.active(owner)['model_id'] == first['id']
    assert service.get(owner, activation['id'])['status'] == 'active'
    replacement = service.request(owner, second['id'])
    assert replacement['previous_model_id'] == first['id']
    assert service.execute(replacement['id'])
    assert service.active(owner)['model_id'] == second['id']
    rollback = service.request(owner, first['id'])
    assert service.execute(rollback['id'])
    assert service.active(owner)['model_id'] == first['id']
    assert service.execute(replacement['id'])  # Old duplicate must not restore second.
    assert service.active(owner)['model_id'] == first['id']
    assert service.loaded[owner].model_id == first['id']
    with connect(config) as conn:
        assert conn.execute('SELECT count(*) FROM model_activations').fetchone() == (3,)


@pytest.mark.parametrize('kind', ['missing', 'corrupt', 'incompatible'])
def test_load_failure_preserves_previous_and_is_visible(registry, kind):
    service, _, owner, _, register = registry
    first, _ = register()
    initial = service.request(owner, first['id'])
    assert service.execute(initial['id'])
    second, directory = register()
    activation = service.request(owner, second['id'])
    if kind == 'missing':
        (directory / 'rul/model.pkl').unlink()
    elif kind == 'corrupt':
        (directory / 'rul/model.pkl').write_bytes(b'incomplete')
    else:
        from backend.app.services.health_training import _sha256
        path = directory / 'health/report.json'
        report = json.loads(path.read_text())
        report['versions']['sklearn'] = '0.0.0'
        path.write_text(json.dumps(report))
        manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['reports']['health']['sha256'] = _sha256(path)
        (directory / 'manifest.json').write_text(json.dumps(manifest))
    assert service.execute(activation['id'])
    state = service.get(owner, activation['id'])
    assert (state['status'], state['error_code']) == ('failed', 'MODEL_LOAD_FAILED')
    assert service.active(owner)['model_id'] == first['id']
    assert service.loaded[owner].model_id == first['id']
    # Durable metadata survives a new process/service object.
    restarted = ModelService(service.settings, artifact_root=service.artifact_root)
    assert restarted.get(owner, activation['id']) == state
    assert restarted.active(owner)['model_version'] == first['model_version']


def test_gate_scope_missing_version_pending_and_revoked_admin(registry):
    service, config, owner, stranger, register = registry
    model, directory = register()
    for account, identifier in ((stranger, model['id']), (owner, uuid4())):
        with pytest.raises(HTTPException) as error:
            service.request(account, identifier)
        assert error.value.status_code == 404
    with connect(config) as conn:
        conn.execute("UPDATE models SET metrics=jsonb_set(metrics,'{eligible}','false') WHERE id=%s", (model['id'],))
    with pytest.raises(HTTPException, match='MODEL_NOT_ELIGIBLE'):
        service.request(owner, model['id'])
    with connect(config) as conn:
        conn.execute("UPDATE models SET metrics=jsonb_set(metrics,'{eligible}','true') WHERE id=%s", (model['id'],))
    request = service.request(owner, model['id'])
    with pytest.raises(HTTPException, match='ACTIVATION_PENDING'):
        service.request(owner, model['id'])
    assert service.execute(request['id'])
    with connect(config) as conn:
        conn.execute("UPDATE users SET role='viewer' WHERE id=%s", (owner,))
    from backend.app.api.auth import AuthError
    with pytest.raises(AuthError):
        service.request(owner, model['id'])


def test_concurrent_load_serializes_owner(registry, monkeypatch):
    service, _, owner, _, register = registry
    model, _ = register()
    request = service.request(owner, model['id'])
    entered, release = Event(), Event()
    from backend.app.services import models
    original = models.load_model_bundle

    def slow(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(models, 'load_model_bundle', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.execute, request['id'])
        try:
            assert entered.wait(5)
            assert service.get(owner, request['id'])['status'] == 'loading'
            assert service.active(owner) is None
            other = ModelService(service.settings, artifact_root=service.artifact_root)
            assert other.execute(request['id']) is False
        finally:
            release.set()
        assert future.result(timeout=10)


def test_interrupted_loading_replays_in_new_service_without_duplicate_status(registry, monkeypatch):
    from backend.app.services import models
    service, config, owner, _, register = registry
    model, _ = register()
    request = service.request(owner, model['id'])

    class Interrupted(BaseException):
        pass

    with monkeypatch.context() as patch:
        patch.setattr(models, 'load_model_bundle', lambda *_: (_ for _ in ()).throw(Interrupted()))
        with pytest.raises(Interrupted):
            service.execute(request['id'])
    assert service.get(owner, request['id'])['status'] == 'loading'
    restarted = ModelService(config, artifact_root=service.artifact_root)
    assert restarted.execute(request['id'])
    assert restarted.active(owner)['model_id'] == model['id']
    assert [event['data']['status'] for event in restarted.pending_outputs('inference')] == ['loading', 'active']


def test_pointer_status_and_outbox_roll_back_together(registry, monkeypatch):
    service, _, owner, _, register = registry
    model, _ = register()
    request = service.request(owner, model['id'])
    enqueue = service._enqueue

    def interrupt(connection, row, model, kind):
        enqueue(connection, row, model, kind)
        if row['status'] == 'active':
            raise RuntimeError('Interrupted transaction')

    with monkeypatch.context() as patch:
        patch.setattr(service, '_enqueue', interrupt)
        with pytest.raises(RuntimeError, match='Interrupted transaction'):
            service.execute(request['id'])
    assert service.active(owner) is None
    assert service.get(owner, request['id'])['status'] == 'loading'
    assert [event['data']['status'] for event in service.pending_outputs('inference')] == ['loading']
    assert service.execute(request['id'])
    assert service.active(owner)['model_id'] == model['id']


def test_changed_registered_version_fails_with_original_request_identity(registry):
    service, config, owner, _, register = registry
    model, _ = register()
    request = service.request(owner, model['id'])
    with connect(config) as conn:
        conn.execute("UPDATE models SET model_version='incompatible-change' WHERE id=%s", (model['id'],))
    assert service.execute(request['id'])
    assert service.active(owner) is None
    statuses = service.pending_outputs('inference')
    assert [event['data']['status'] for event in statuses] == ['loading', 'failed']
    assert all(event['data']['model_version'] == model['model_version'] for event in statuses)


def test_real_http_session_roles_isolation_and_visible_status(registry):
    import secrets
    from unittest.mock import Mock
    from fastapi.testclient import TestClient
    from backend.app.api.app import create_app
    from backend.app.api.auth import AuthService
    from backend.app.api.catalog import CatalogService
    from backend.app.api.models import create_models_router
    service, config, owner, stranger, register = registry
    model, _ = register()
    auth = AuthService(config)
    password = secrets.token_urlsafe(24)
    with connect(config) as conn:
        conn.execute('UPDATE users SET password_hash=%s', (auth._passwords.hash(password),))
    headers = [{'Authorization': 'Bearer ' + auth.login(f'{account}@example.invalid', password, ip='test')[0]}
               for account in (owner, stranger)]
    app = create_app(repository=Mock(), readiness_check=lambda: True, auth=auth, catalog=CatalogService(config))
    app.include_router(create_models_router(auth, service))
    with TestClient(app) as client:
        assert client.get('/api/v3/models').status_code == 401
        assert client.get('/api/v3/models', headers=headers[1]).json()['data'] == []
        assert client.post('/api/v3/model-activations', headers=headers[1],
                           json={'model_id': str(model['id'])}).status_code == 404
        response = client.post('/api/v3/model-activations', headers=headers[0],
                               json={'model_id': str(model['id'])})
        assert response.status_code == 202
        identifier = UUID(response.json()['data']['id'])
        assert client.get(f'/api/v3/model-activations/{identifier}', headers=headers[1]).status_code == 404
        assert service.execute(identifier)
        assert client.get('/api/v3/models/active', headers=headers[0]).json()['data']['model_id'] == str(model['id'])
        assert client.get(f'/api/v3/model-activations/{identifier}', headers=headers[0]).json()['data']['status'] == 'active'
        with connect(config) as conn:
            conn.execute("UPDATE users SET role='viewer' WHERE id=%s", (owner,))
        assert client.post('/api/v3/model-activations', headers=headers[0],
                           json={'model_id': str(model['id'])}).status_code == 403
        assert auth.logout(headers[0]['Authorization'].split(' ', 1)[1])
        assert client.get('/api/v3/models/active', headers=headers[0]).status_code == 401


def test_real_amqp_private_activation_confirm_duplicate_and_status(registry, broker, monkeypatch):
    import psycopg
    from backend.app.amqp.models import ModelPublisher, ModelWorker
    from backend.tests.contract.test_aiot_contract import check_model_semantics
    from jsonschema import Draft202012Validator, FormatChecker
    from simulator.model import SCHEMA
    service, _, owner, _, register = registry
    model, _ = register()
    request = service.request(owner, model['id'])
    requested = service.get_requested(request['id'])
    publisher = ModelPublisher(service, host='127.0.0.1', port=broker['port'], password=broker['passwords']['api'])
    with amqp_connect(broker, 'api') as channel:
        with monkeypatch.context() as patch:
            patch.setattr(service, 'mark_published', lambda *_: (_ for _ in ()).throw(psycopg.OperationalError('lost confirmation')))
            with pytest.raises(psycopg.OperationalError):
                publisher.flush_outputs(channel)
        assert len(service.pending_outputs('api')) == 1
        publisher.flush_outputs(channel)
    worker = ModelWorker(service, host='127.0.0.1', port=broker['port'], password=broker['passwords']['inference'])
    try:
        with amqp_connect(broker, 'inference') as channel:
            worker.step(channel)
            worker.step(channel)
            assert channel.basic_get('coldsafe.model-activation', auto_ack=False)[0] is None
        assert service.get(owner, request['id'])['status'] == 'active'
        assert service.pending_outputs('inference') == []
        statuses = []
        with amqp_connect(broker, 'delivery') as channel:
            while True:
                method, _, body = channel.basic_get('coldsafe.delivery', auto_ack=True)
                if method is None:
                    break
                event = json.loads(body)
                if event['type'] == 'model_status':
                    Draft202012Validator({**SCHEMA, '$ref': '#/$defs/model_status_event'},
                                         format_checker=FormatChecker()).validate(event)
                    check_model_semantics(event, requested)
                    statuses.append(event['data']['status'])
        assert statuses == ['loading', 'active']
    finally:
        worker.close()
