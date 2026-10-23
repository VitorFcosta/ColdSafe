"""B2-33: opt-in, disposable final Compose, real services and persistent volumes."""
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
from uuid import UUID

import httpx
import psycopg
import pytest
from backend.tests.infra.test_writer_integration import rows as influx_rows

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ('mosquitto', 'rabbitmq', 'postgres', 'influxdb', 'backend', 'frontend',
            'simulator', 'gateway', 'writer', 'generation', 'training', 'models', 'ollama', 'llm')
OVERLAYS = ('compose.yaml', 'compose.aiot.yaml', 'compose.jobs.yaml',
            'compose.inference.yaml', 'compose.ollama.yaml')
QUESTION = 'Quantos equipamentos tenho?'
pytestmark = pytest.mark.integration


def eventually(check, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(1)
    raise AssertionError('Final stack did not reach the expected state before timeout')


class Stack:
    def __init__(self, directory):
        self.directory = directory
        self.project = 'coldsafe-b233-' + secrets.token_hex(4)
        self.env_file = directory / '.env'
        self.values = {}
        self.token = None
        self.base = ['docker', 'compose', '-p', self.project, '--env-file', str(self.env_file)]
        for name in OVERLAYS:
            self.base += ['-f', str(ROOT / name)]
        self.base += ['-f', str(directory / 'override.yaml'), '--profile', 'aiot', '--profile', 'simulator']
        self.report = {'started_at': datetime.now(UTC).isoformat(), 'project': self.project,
                       'git': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                       'question': QUESTION, 'phases': [], 'resources': []}
        self.stop = Event()

    def clean(self, text):
        for key, value in self.values.items():
            if value and any(part in key for part in ('PASSWORD', 'TOKEN', 'SECRET')):
                text = text.replace(value, '[REDACTED]')
        return text.replace(self.token, '[REDACTED]') if self.token else text

    def command(self, *args, timeout=900, input=None):
        environment = {key: value for key, value in os.environ.items() if key not in self.values}
        if not self.values.get('INFLUXDB_TOKEN'):
            environment['INFLUXDB_TOKEN'] = 'bootstrap-not-used'
        result = subprocess.run([*self.base, *args], cwd=ROOT, env=environment,
                                text=True, input=input, capture_output=True, timeout=timeout)
        assert result.returncode == 0, self.clean(result.stdout + result.stderr)[-7000:]
        return result.stdout

    def save_env(self):
        self.env_file.write_text('\n'.join(f'{key}={value}' for key, value in self.values.items()) + '\n')
        self.env_file.chmod(0o600)

    def port(self, service, port):
        return self.command('port', service, str(port)).strip().rsplit(':', 1)[1]

    def request(self, method, path, data=None, expected=200):
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        response = httpx.request(method, self.url + path, json=data, headers=headers, timeout=30, trust_env=False)
        assert response.status_code == expected, f'{path}: {response.status_code} {self.clean(response.text)}'
        return response.json().get('data')

    def phase(self, name, **values):
        self.report['phases'].append({'name': name, 'at': datetime.now(UTC).isoformat(), **values})
        print(f'B2-33: {name}', flush=True)

    def resources(self):
        ids = self.command('ps', '-q').split()
        if not ids:
            return
        result = subprocess.run(['docker', 'inspect', *ids], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0
        for row in json.loads(result.stdout):
            name = row['Config']['Labels']['com.docker.compose.service']
            if name not in SERVICES:
                continue
            state = row['State']
            sample = {'at': datetime.now(UTC).isoformat(), 'service': name, 'id': row['Id'][:12],
                      'running': state['Running'], 'oom_killed': state['OOMKilled'],
                      'restarts': row['RestartCount'], 'health': state.get('Health', {}).get('Status')}
            if state['Running']:
                probe = subprocess.run(['docker', 'exec', row['Id'], 'sh', '-c',
                    'cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.events'],
                    capture_output=True, text=True, timeout=15)
                lines = probe.stdout.splitlines()
                if probe.returncode == 0 and len(lines) >= 2:
                    sample.update(current=int(lines[0]), peak=int(lines[1]),
                                  events={key: int(value) for key, value in (line.split() for line in lines[2:])})
                if name == 'ollama':
                    diagnostic = subprocess.run(['docker', 'exec', row['Id'], 'sh', '-c',
                        'cat /sys/fs/cgroup/cpu.stat /sys/fs/cgroup/cpu.pressure '
                        '/sys/fs/cgroup/memory.pressure /sys/fs/cgroup/memory.swap.current '
                        '/proc/pressure/memory'], capture_output=True, text=True, timeout=15)
                    sample['cpu_pressure_swap'] = diagnostic.stdout
                    sample['diagnostic_exit_code'] = diagnostic.returncode
            self.report['resources'].append(sample)

    def monitor(self):
        while not self.stop.wait(5):
            try:
                self.resources()
            except (AssertionError, subprocess.SubprocessError, ValueError, OSError) as error:
                self.report.setdefault('monitor_errors', []).append(type(error).__name__)

    def healthy(self):
        rows = [json.loads(line) for line in self.command('ps', '--format', 'json').splitlines() if line]
        return set(SERVICES) <= {row['Service'] for row in rows if row.get('Health') == 'healthy'}

    def summary(self):
        return self.request('GET', '/api/v3/monitoring/summary?device_id=sim-lab-01')

    def live(self):
        def check():
            result = self.summary()
            return result if result.get('persistence') == 'persisted' and result.get('freshness', {}).get('state') == 'fresh' else None
        return eventually(check)

    def led(self):
        start = time.monotonic()
        command = self.request('POST', '/api/v3/devices/sim-lab-01/led/commands', {'desired_state': True})
        identifier = command['data']['command_id'] if 'data' in command else command['command_id']
        def confirmed():
            row = self.request('GET', '/api/v3/commands/' + identifier)
            return row if row['data']['status'] == 'confirmed' else None
        eventually(confirmed, 35)
        return round(time.monotonic() - start, 3)

    def llm_ready(self):
        return eventually(lambda: self.request('GET', '/api/v3/llm/status')['state'] == 'ready', 300)

    def assistant(self):
        start = time.monotonic()
        first = None
        events = []
        errors = []
        chunks = []
        event = None
        with httpx.stream('POST', self.url + '/api/v3/llm/ask',
                          json={'question': QUESTION},
                          headers={'Authorization': 'Bearer ' + self.token}, timeout=140, trust_env=False) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith('event: '):
                    event = line[7:]
                    events.append(event)
                    if line[7:] == 'delta' and first is None:
                        first = time.monotonic() - start
                elif event == 'error' and line.startswith('data: '):
                    errors.append(json.loads(line[6:]))
                elif event == 'delta' and line.startswith('data: '):
                    chunks.append(json.loads(line[6:])['text'])
        metric = {'first_token_seconds': first, 'total_seconds': round(time.monotonic() - start, 3),
                  'delta_count': events.count('delta'), 'errors': errors, 'completed': 'done' in events,
                  'question': QUESTION, 'text': self.clean(''.join(chunks))}
        self.report.setdefault('assistant_requests', []).append(metric)
        assert 'done' in events and 'error' not in events, metric
        assert first is not None, 'Assistant completed without any text delta'
        answer = metric['text'].replace('*', '').replace('`', '').lower()
        assert re.search(r'\b(?:1|um)\s+equipamento\b', answer), metric
        return {'first_token_seconds': first, 'total_seconds': round(time.monotonic() - start, 3), 'events': events}

    def browser(self):
        script = '''import {chromium, expect} from '@playwright/test';
const browser = await chromium.launch({headless:true, args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page = await browser.newPage();
  await page.addInitScript(session => sessionStorage.setItem('coldsafe-session', session), process.env.COLDSAFE_STACK_SESSION);
  const headings = [];
  for (const route of ['/dashboard','/digital-twin','/insights','/laboratory','/training','/messaging','/assistant']) {
    await page.goto(process.env.COLDSAFE_STACK_URL + route);
    await expect(page.locator('main h1')).toBeVisible({timeout:30000});
    expect(new URL(page.url()).pathname).toBe(route);
    headings.push({route, heading:await page.locator('main h1').innerText()});
  }
  console.log(JSON.stringify(headings));
} finally {await browser.close();}'''
        session = {'token': self.token, 'expires_at': '2099-01-01T00:00:00Z',
                   'dashboard_selection': {'environmentId': self.catalog['environment_id'],
                                           'deviceUuid': self.catalog['device_record_id'], 'period': '1h'}}
        environment = {**os.environ, 'COLDSAFE_STACK_SESSION': json.dumps(session), 'COLDSAFE_STACK_URL': self.url}
        result = subprocess.run([os.environ.get('COLDSAFE_NODE_BINARY', 'node'), '--input-type=module', '-e', script],
                                cwd=ROOT / 'frontend', env=environment, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, self.clean(result.stdout + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def stored(self, event_id):
        return influx_rows({'url': 'http://127.0.0.1:' + self.port('influxdb', 8086),
                           'org': self.values['DOCKER_INFLUXDB_INIT_ORG'], 'values': self.values}, event_id=event_id)

    def job_done(self, identifier):
        def check():
            row = self.request('GET', '/api/v3/jobs/' + identifier)
            assert row['status'] not in ('failed', 'cancelled'), row
            return row if row['status'] == 'completed' else None
        return eventually(check, 1200)


def prepare(stack):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/generate-secrets.py'),
                             '--env-file', str(stack.env_file)], capture_output=True, text=True)
    assert result.returncode == 0
    stack.values = dict(line.split('=', 1) for line in stack.env_file.read_text().splitlines()
                        if line and not line.startswith('#'))
    catalog_dir = stack.directory / 'catalog'
    catalog_dir.mkdir(mode=0o755)
    stack.directory.chmod(0o755)
    catalog = json.loads((ROOT / 'simulator/catalog.example.json').read_text())
    stack.catalog = catalog
    (catalog_dir / 'catalog.json').write_text(json.dumps(catalog))
    stack.values.update(INFLUXDB_TOKEN='bootstrap-not-used', SIMULATOR_CATALOG_DIR=str(catalog_dir),
                        GATEWAY_OWNER_USER_ID='00000000-0000-4000-8000-000000000001',
                        WRITER_OWNER_USER_ID='00000000-0000-4000-8000-000000000001')
    stack.save_env()
    (stack.directory / 'override.yaml').write_text('''services:
  frontend:
    ports: !override ["127.0.0.1::8080"]
  postgres:
    ports: ["127.0.0.1::5432"]
    networks: [coldsafe-internal, coldsafe-edge]
  influxdb:
    ports: ["127.0.0.1::8086"]
    networks: [coldsafe-internal, coldsafe-edge]
''')
    stack.command('config', '--quiet')
    stack.command('up', '-d', '--build', '--wait', '--wait-timeout', '180',
                  'postgres', 'influxdb', 'rabbitmq', 'mosquitto')
    stack.values['INFLUXDB_TOKEN'] = ''
    stack.save_env()
    bootstrap = [sys.executable, str(ROOT / 'scripts/bootstrap-influx.py'), '--env-file', str(stack.env_file),
                 '--project-name', stack.project, '--compose-file', str(ROOT / 'compose.yaml'),
                 '--compose-file', str(stack.directory / 'override.yaml')]
    environment = {key: value for key, value in os.environ.items() if key not in stack.values}
    for _ in range(2):
        result = subprocess.run(bootstrap, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, stack.clean(result.stdout + result.stderr)
        current = stack.env_file.read_bytes()
        if _ == 0:
            before = current
        else:
            assert before == current, 'Bootstrap must preserve existing credentials byte for byte'
    stack.values = dict(line.split('=', 1) for line in stack.env_file.read_text().splitlines()
                        if line and not line.startswith('#'))
    stack.password = secrets.token_urlsafe(24)
    owner = stack.command('run', '--rm', '--no-deps', '--build', '-T', 'backend', 'python', '-c',
        'import sys; from backend.app.config.settings import RuntimeSettings; '
        'from backend.app.repositories.postgres import initialize_schema; '
        'from backend.app.api.auth import AuthService; s=RuntimeSettings(); initialize_schema(s); '
        'print(AuthService(s).register("stack@example.invalid",sys.stdin.read()))', input=stack.password).strip().splitlines()[-1]
    owner = str(UUID(owner))
    stack.values.update(GATEWAY_OWNER_USER_ID=owner, WRITER_OWNER_USER_ID=owner)
    stack.save_env()
    stack.pg = {'host': '127.0.0.1', 'port': stack.port('postgres', 5432),
                'dbname': stack.values['POSTGRES_DB'], 'user': stack.values['POSTGRES_USER'],
                'password': stack.values['POSTGRES_PASSWORD']}
    with psycopg.connect(**stack.pg) as connection:
        connection.execute("UPDATE users SET role='admin' WHERE id=%s", (owner,))
        connection.execute('INSERT INTO environments(id,owner_user_id,name) VALUES(%s,%s,%s)',
                           (catalog['environment_id'], owner, 'Stack test'))
        connection.execute('INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES(%s,%s,%s,%s)',
                           (catalog['device_record_id'], catalog['environment_id'], catalog['device_id'], 'Simulator'))
        connection.execute('INSERT INTO environment_rules(environment_id) VALUES(%s)', (catalog['environment_id'],))
    stack.phase('clean_bootstrap_idempotent')
    stack.command('--profile', 'llm-setup', 'run', '--rm', '--no-deps', 'ollama-prepare', timeout=1800)
    stack.phase('weights_prepared')


def exercise(stack):
    stack.command('up', '-d', '--build', '--wait', '--wait-timeout', '300')
    stack.url = 'http://127.0.0.1:' + stack.port('frontend', 8080)
    stack.token = stack.request('POST', '/api/v1/auth/login',
                                {'email': 'stack@example.invalid', 'password': stack.password})['token']
    stack.phase('all_services_healthy', count=len(SERVICES))
    stack.report['ollama_inventory'] = json.loads(stack.command('exec', '-T', 'backend', 'python', '-c',
        'import json; from backend.app.services.llm import OllamaClient; '
        'print(json.dumps(OllamaClient("http://ollama:11434").request("/api/tags")))'))
    live = stack.live()
    stack.phase('live_telemetry_led', event_id=live['telemetry']['event_id'], led_seconds=stack.led())
    stack.llm_ready()
    stack.phase('assistant_preloaded', **stack.assistant())
    stack.phase('browser_routes', pages=stack.browser())
    exercise_security(stack)
    stack.command('stop', 'writer')
    time.sleep(5)
    stack.command('start', 'writer')
    stack.live()
    stack.phase('writer_recovered')
    for broker in ('mosquitto', 'rabbitmq'):
        stack.command('restart', broker)
        eventually(stack.healthy, 180)
        stack.live()
        stack.phase(broker + '_recovered', led_seconds=stack.led())
    stack.command('stop', 'ollama')
    eventually(lambda: stack.request('GET', '/api/v3/llm/status')['state'] == 'unavailable')
    stack.live()
    stack.command('start', 'ollama')
    stack.llm_ready()
    stack.phase('ollama_recovered', **stack.assistant())
    start = time.monotonic()
    first = stack.request('POST', '/api/v3/jobs', {'job_type': 'generation', 'total_units': 1_000_000}, expected=202)
    second = stack.request('POST', '/api/v3/jobs', {'job_type': 'generation', 'total_units': 1_000_000, 'seed': 43}, expected=202)
    def running():
        with psycopg.connect(**stack.pg) as connection:
            count = connection.execute("SELECT count(*) FROM jobs WHERE status='running'").fetchone()[0]
        assert count <= 1
        return count == 1
    eventually(running)
    stack.live()
    stack.phase('jobs_serialized', led_seconds=stack.led())
    generated = stack.job_done(first['id'])
    stack.job_done(second['id'])
    stack.phase('generation_completed', rows=1_000_000, seconds=round(time.monotonic() - start, 3))
    start = time.monotonic()
    training = stack.request('POST', '/api/v3/jobs',
        {'job_type': 'training', 'dataset_id': generated['result_id']}, expected=202)
    eventually(running)
    stack.live()
    stack.led()
    trained = stack.job_done(training['id'])
    stack.phase('training_completed', seconds=round(time.monotonic() - start, 3))
    activation = stack.request('POST', '/api/v3/model-activations', {'model_id': trained['result_id']}, expected=202)
    def activated():
        row = stack.request('GET', '/api/v3/model-activations/' + activation['id'])
        assert row['status'] != 'failed', row
        return row['status'] == 'active'
    eventually(activated)
    active = stack.request('GET', '/api/v3/models/active')
    stack.llm_ready()
    stack.phase('model_activated_assistant_reloaded', **stack.assistant())
    history = stack.request('GET', '/api/v3/readings?device_id=sim-lab-01&limit=5')
    stored = stack.stored(history[0]['telemetry']['event_id'])
    assert len(stored) == 1
    dataset = stack.request('GET', '/api/v3/datasets/' + generated['result_id'])
    stack.command('down')
    stack.command('up', '-d', '--wait', '--wait-timeout', '300')
    stack.url = 'http://127.0.0.1:' + stack.port('frontend', 8080)
    stack.pg['port'] = stack.port('postgres', 5432)
    assert stack.request('GET', '/api/v3/models/active') == active
    assert stack.request('GET', '/api/v3/datasets/' + generated['result_id']) == dataset
    stack.job_done(training['id'])
    stack.live()
    restored = stack.request('GET', '/api/v3/readings?device_id=sim-lab-01&limit=1000')
    assert {row['telemetry']['event_id'] for row in history} <= {row['telemetry']['event_id'] for row in restored}
    assert stack.stored(history[0]['telemetry']['event_id']) == stored
    stack.llm_ready()
    stack.phase('volumes_preserved_before_last_assistant')
    stack.phase('volumes_restart_preserved', led_seconds=stack.led(), **stack.assistant())
    assert stack.healthy()
    stack.resources()
    assert not any(row['oom_killed'] or row.get('events', {}).get('oom_kill', 0)
                   for row in stack.report['resources'])


def exercise_security(stack):
    """B2-34: real HTTP/SQL, current roles, ownership and revoked sessions."""
    checks = []

    def request(method, path, expected, token=None, data=None):
        response = httpx.request(method, stack.url + path, json=data,
            headers={'Authorization': 'Bearer ' + token} if token else {},
            timeout=30, trust_env=False)
        assert response.status_code == expected, (path, response.status_code)
        checks.append({'method': method, 'path': path, 'status': expected})
        return response

    request('GET', '/api/v3/models', 401)
    request('GET', '/api/v3/models', 401, token='invalid')
    password = secrets.token_urlsafe(24)
    request('POST', '/api/v1/auth/register', 201,
            data={'email': 'other-stack@example.invalid', 'password': password})
    login = request('POST', '/api/v1/auth/login', 200,
        data={'email': 'other-stack@example.invalid', 'password': password}).json()['data']
    other = login['token']
    request('GET', '/api/v3/monitoring/summary?device_id=sim-lab-01', 404, other)
    request('POST', '/api/v3/devices/sim-lab-01/led/commands', 404, other,
            {'desired_state': True})
    with psycopg.connect(**stack.pg) as connection:
        owner = connection.execute('SELECT owner_user_id FROM environments WHERE id=%s',
                                    (stack.catalog['environment_id'],)).fetchone()[0]
        commands_before = connection.execute('SELECT count(*) FROM aiot_commands').fetchone()[0]
        connection.execute("UPDATE users SET role='viewer' WHERE id=%s", (owner,))
    try:
        request('GET', '/api/v3/monitoring/summary?device_id=sim-lab-01', 200, stack.token)
        request('POST', '/api/v3/devices/sim-lab-01/led/commands', 403, stack.token,
                {'desired_state': False})
        request('POST', '/api/v3/jobs', 403, stack.token,
                {'job_type': 'generation', 'total_units': 1_000_000})
        request('GET', '/api/v3/messaging', 403, stack.token)
        with psycopg.connect(**stack.pg) as connection:
            assert connection.execute('SELECT count(*) FROM aiot_commands').fetchone()[0] == commands_before
            connection.execute("UPDATE users SET role='operator' WHERE id=%s", (owner,))
        request('POST', '/api/v3/jobs', 403, stack.token,
                {'job_type': 'generation', 'total_units': 1_000_000})
    finally:
        with psycopg.connect(**stack.pg) as connection:
            connection.execute("UPDATE users SET role='admin' WHERE id=%s", (owner,))
    request('GET', '/api/v3/messaging', 200, stack.token)
    request('POST', '/api/v1/auth/logout', 200, other)
    request('GET', '/api/v3/models', 401, other)
    with psycopg.connect(**stack.pg) as connection:
        assert connection.execute('SELECT count(*) FROM audit_events').fetchone()[0] > 0
    stack.phase('security_http_sql', checks=checks, denied_commands_created=0)


def test_final_stack_clean_start_recovery_persistence_and_capacity():
    if os.environ.get('COLDSAFE_STACK_INTEGRATION') != '1':
        pytest.skip('Set COLDSAFE_STACK_INTEGRATION=1 for disposable full-stack checks')
    with tempfile.TemporaryDirectory(prefix='coldsafe-b233-') as directory:
        stack = Stack(Path(directory))
        monitor = Thread(target=stack.monitor, daemon=True)
        try:
            prepare(stack)
            monitor.start()
            exercise(stack)
            stack.report['result'] = 'passed'
        except BaseException as error:
            stack.report.update(result='failed', failure=stack.clean(str(error))[-7000:])
            raise
        finally:
            stack.stop.set()
            if monitor.ident is not None:
                monitor.join(timeout=45)
            try:
                stack.resources()
                stack.report['logs'] = stack.clean(stack.command('logs', '--no-color', '--tail', '12'))[-12000:]
                stack.report['ollama_logs'] = stack.clean(stack.command('logs', '--no-color', 'ollama'))
            finally:
                # Only this uniquely named project's newly created resources are disposable.
                stack.command('down', '--volumes', '--remove-orphans')
                stack.report['cleaned_up'] = True
                stack.report['ended_at'] = datetime.now(UTC).isoformat()
                evidence = os.environ.get('COLDSAFE_STACK_EVIDENCE')
                if evidence:
                    Path(evidence).write_text(json.dumps(stack.report, indent=2) + '\n')
