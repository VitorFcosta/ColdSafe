"""B2-36: opt-in, ordered presentation against disposable real services.

An explicitly supplied private state attaches to the coordinator's B2-36 stack;
that coordinator owns cleanup. No clock, telemetry, predictions or browser API
responses are substituted. A fresh run needs at least one real hour of history.
"""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
from uuid import UUID

import httpx
from influxdb_client import InfluxDBClient
import psycopg
import pytest
from urllib3.exceptions import ReadTimeoutError

from backend.tests.infra.test_stack_integration import ROOT, SERVICES, Stack, eventually, prepare
from backend.tests.infra.test_writer_integration import FIELDS

pytestmark = pytest.mark.integration
INSIGHTS = '/api/v3/insights?device_id=sim-lab-01'
RULES = '/api/v3/insights/rules?device_id=sim-lab-01'
RUL_DROP_HOURS = 0.05


class Rehearsal:
    def __init__(self, stack, state, state_path):
        self.started_monotonic = time.monotonic()
        assert re.fullmatch(r'coldsafe-b236-[a-z0-9-]+', stack.project), 'Only disposable B2-36 projects are allowed'
        assert stack.base[stack.base.index('-p') + 1] == stack.project, 'Compose project and supplied state must match'
        origin = httpx.URL(stack.url)
        assert origin.host in ('127.0.0.1', 'localhost') and not origin.userinfo
        self.stack, self.state, self.state_path = stack, state, state_path
        self.report = {'task': 'B2-36', 'project': stack.project,
                       'started_at': datetime.now(UTC).isoformat(),
                       'git': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                       'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                       'runtime_diff_paths': ['backend/app', 'frontend', 'compose.ollama.yaml'],
                       'runtime_diff_sha256': sha256(subprocess.check_output(
                           ['git', 'diff', 'HEAD', '--', 'backend/app', 'frontend', 'compose.ollama.yaml'], cwd=ROOT)).hexdigest(),
                       'source_files_sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest()
                           for name in ('backend/tests/infra/test_rehearsal_integration.py',
                                        'frontend/e2e/helpers/final-rehearsal.mjs',
                                        'backend/tests/infra/test_stack_integration.py',
                                        'backend/tests/api/test_docs_offline.py')},
                       'attached': bool(os.environ.get('COLDSAFE_REHEARSAL_STATE')),
                       'phases': [], 'fault_samples': [], 'result': 'running'}
        self.saved_rules = None
        self.saved_thresholds = None

    def clean(self, value):
        text = self.stack.clean(str(value))
        for account in self.state.get('accounts', {}).values():
            for key in ('password', 'token'):
                if account.get(key):
                    text = text.replace(account[key], '[REDACTED]')
        if self.state.get('password'):
            text = text.replace(self.state['password'], '[REDACTED]')
        return text

    def save(self):
        evidence = os.environ.get('COLDSAFE_REHEARSAL_EVIDENCE')
        if evidence:
            destination = Path(evidence)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(self.clean(json.dumps(self.report, indent=2, default=str)) + '\n')

    def private(self, **values):
        self.state.update(values)
        self.state_path.write_text(json.dumps(self.state, default=str))
        self.state_path.chmod(0o600)

    def pin_frontend(self):
        directory = self.stack.directory.resolve()
        assert directory.name.startswith('coldsafe-b236-'), 'Frontend pinning requires this rehearsal temporary directory'
        override = directory / 'override.yaml'
        assert not override.is_symlink() and override.resolve().parent == directory
        port = int(self.stack.port('frontend', 8080))
        assert 1 <= port <= 65535
        contents = override.read_text()
        ephemeral, fixed = '127.0.0.1::8080', f'127.0.0.1:{port}:8080'
        changed = ephemeral in contents
        if changed:
            assert contents.count(ephemeral) == 1
            override.write_text(contents.replace(ephemeral, fixed))
        else:
            assert re.findall(r'127\.0\.0\.1:\d+:8080', contents) == [fixed], 'Unexpected frontend override binding'
        protected = self.stack.command('ps', '-q', 'backend', 'simulator').split()
        assert len(protected) == 2
        self.stack.command('up', '-d', '--no-build', '--no-deps', '--wait', '--wait-timeout', '60',
                           'frontend', timeout=90)
        assert int(self.stack.port('frontend', 8080)) == port, 'Frontend published port changed during pinning'
        assert self.stack.command('ps', '-q', 'backend', 'simulator').split() == protected
        self.stack.url = f'http://127.0.0.1:{port}'
        self.private(url=self.stack.url)
        self.report['frontend_port'] = {'host': '127.0.0.1', 'published': port, 'container': 8080,
                                        'stable_binding': True, 'override_changed': changed,
                                        'backend_simulator_ids_preserved': protected}
        self.save()

    def phase(self, number, name, **observations):
        self.report['phases'].append({'step': number, 'name': name,
                                      'at': datetime.now(UTC).isoformat(), **observations})
        self.save()
        print(f'B2-36: {number:02d} {name}', flush=True)

    def browser(self, phase, **values):
        self.private(**values)
        environment = {**os.environ, 'COLDSAFE_REHEARSAL_STATE': str(self.state_path)}
        result = subprocess.run([os.environ.get('COLDSAFE_NODE_BINARY', 'node'),
                                 'e2e/helpers/final-rehearsal.mjs', phase],
                                cwd=ROOT / 'frontend', env=environment, text=True,
                                capture_output=True, timeout=850)
        try:
            observation = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise AssertionError(f'Browser {phase} did not return safe JSON; exit={result.returncode}') from None
        self.report.setdefault('browser', []).append(observation)
        self.save()
        assert result.returncode == 0 and observation.get('status') == 'passed', self.clean(observation)
        return observation

    def request(self, method, path, data=None, expected=200, token=None):
        response = httpx.request(method, self.stack.url + path, json=data,
                                headers={'Authorization': 'Bearer ' + (token or self.stack.token)},
                                timeout=30, trust_env=False)
        assert response.status_code == expected, (path, response.status_code)
        return response.json().get('data')

    def control(self, action, *arguments):
        environment = {key: value for key, value in os.environ.items() if key not in self.stack.values}
        environment['MQTT_SIMULATOR_OPERATOR_PASSWORD'] = self.stack.values['MQTT_SIMULATOR_OPERATOR_PASSWORD']
        result = subprocess.run([*self.stack.base, 'run', '--rm', '--no-deps', '--entrypoint', 'python',
                                 '-e', 'MQTT_SIMULATOR_OPERATOR_PASSWORD', 'simulator',
                                 '-m', 'simulator.control', action, *arguments], cwd=ROOT,
                                env=environment, text=True, capture_output=True, timeout=90)
        assert result.returncode == 0, 'MQTT operational control failed: ' + action

    def roles(self):
        accounts = dict(self.state['accounts'])
        evidence = []
        for role in ('operator', 'viewer'):
            existing = accounts.get(role)
            email = existing['email'] if existing else f'{role}-b236@example.invalid'
            password = existing['password'] if existing else secrets.token_urlsafe(24)
            if not existing:
                self.request('POST', '/api/v1/auth/register', {'email': email, 'password': password}, 201)
            login = self.request('POST', '/api/v1/auth/login', {'email': email, 'password': password})
            token = login['token']
            me = self.request('GET', '/api/v1/auth/me', token=token)
            user_id = str(me['user_id'] if 'user_id' in me else me['id'])
            environment = ({'id': existing['environment_id']} if existing else
                           self.request('POST', '/api/v1/environments', {'name': f'Ensaio {role}'}, 201, token))
            self.request('PATCH', f'/api/v1/auth/users/{user_id}/role', {'role': role})
            assert self.request('GET', '/api/v1/auth/me', token=token)['role'] == role
            accounts[role] = {'email': email, 'password': password, 'token': token,
                              'user_id': user_id, 'environment_id': environment['id']}
            self.private(accounts=accounts)
            evidence.append({'role': role, 'user_id': user_id, 'environment_id': environment['id']})
        self.private(accounts=accounts)
        self.phase(2, 'three_private_roles', accounts=evidence, browser=self.browser('roles'))

    def telemetry(self):
        first = self.stack.live()['telemetry']
        second = eventually(lambda: (row if (row := self.stack.live()['telemetry'])['event_id'] != first['event_id'] else None))
        for row in (first, second):
            assert len(row['data']['measurements']) == 6
            assert len(row['data']['actuators']) == 2
            assert row['data']['equipment']['equipment_id'] == self.stack.catalog['equipment_id']
        self.phase(3, 'six_live_sensors_mqtt', events=[first, second])

    def queue(self, name):
        snapshot = self.request('GET', '/api/v3/messaging')
        return next(row for row in snapshot['queues'] if row['name'] == name)

    def messaging(self):
        before = self.queue('coldsafe.writer')
        self.stack.command('stop', 'writer')
        try:
            grown = eventually(lambda: (row if (row := self.queue('coldsafe.writer'))['messages'] >= before['messages'] + 5 else None), 90)
            browser = self.browser('messaging', expect_writer_backlog=True)
        finally:
            self.stack.command('start', 'writer')
        drained = eventually(lambda: (row if (row := self.queue('coldsafe.writer'))['messages'] < grown['messages'] else None), 120)
        self.stack.live()
        dlq = self.queue('coldsafe.dlq')
        samples = self.request('GET', '/api/v3/messaging/messages')
        self.phase(5, 'writer_backlog_and_recovery', before=before, stopped=grown,
                   resumed=drained, dlq_readonly=dlq, private_sample_counts={
                       key: len(samples[key]) for key in ('messages', 'dead_letters')}, browser=browser)

    def storage(self):
        reading = self.stack.live()['telemetry']
        read_timeouts = []
        def persisted():
            try:
                instant = datetime.fromisoformat(reading['received_at'].replace('Z', '+00:00'))
                with InfluxDBClient(url='http://127.0.0.1:' + self.stack.port('influxdb', 8086),
                                    org=self.stack.values['DOCKER_INFLUXDB_INIT_ORG'],
                                    token=self.stack.values['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN']) as client:
                    tables = client.query_api().query('''from(bucket: _bucket)
                        |> range(start: time(v: _start), stop: time(v: _stop))
                        |> filter(fn: (r) => r._measurement == "equipment_reading_v3" and r.event_id == _event)
                        |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")''',
                        params={'_bucket': 'telemetry_live', '_event': reading['event_id'],
                                '_start': (instant - timedelta(seconds=1)).isoformat(),
                                '_stop': (instant + timedelta(seconds=1)).isoformat()})
                    return [{key: value for key, value in record.values.items()
                             if key not in ('result', 'table', '_start', '_stop')}
                            for table in tables for record in table.records]
            except ReadTimeoutError:
                # This diagnostic read is idempotent; retain each timeout before retrying.
                read_timeouts.append(datetime.now(UTC).isoformat())
                self.report['storage_read_timeouts'] = read_timeouts
                self.save()
                return None
        points = eventually(persisted, 60)
        assert len(points) == 1
        assert all(FIELDS[name] in points[0] for name in reading['data']['measurements'])
        with psycopg.connect(**self.stack.pg) as connection:
            events = connection.execute('SELECT kind,linked FROM aiot_events WHERE event_id=%s OR source_event_id=%s',
                                        (reading['event_id'], reading['event_id'])).fetchall()
            audits = connection.execute('SELECT count(*) FROM audit_events').fetchone()[0]
            rules = connection.execute('SELECT temp_min_c,temp_max_c FROM environment_rules WHERE environment_id=%s',
                                       (self.stack.catalog['environment_id'],)).fetchone()
        assert any(kind == 'telemetry' for kind, _ in events)
        assert any(kind == 'telemetry_persisted' and linked for kind, linked in events)
        assert audits > 0 and rules
        self.phase(6, 'sql_influx_http_correlated', event_id=reading['event_id'],
                   received_at=reading['received_at'], influx=points, sql_events=events, audit_count=audits,
                   influx_query_read_timeouts=read_timeouts, influx_query_range_seconds=2)

    def actuators(self):
        path = f"/api/v1/environments/{self.stack.catalog['environment_id']}/rules"
        original = self.request('GET', path)
        self.saved_thresholds = (path, {key: original[key] for key in ('min_c', 'max_c', 'attention_margin_c')})
        before = self.stack.live()['telemetry']['data']['actuators']['led']['actual_state']
        try:
            # Deliberately broad normal range first; the measured current temperature then crosses the demo maximum.
            self.request('PUT', path, {'min_c': -100, 'max_c': 100, 'attention_margin_c': 1})
            eventually(lambda: not self.stack.live()['telemetry']['data']['actuators']['buzzer']['actual_state'], 60)
            temperature = self.stack.live()['telemetry']['data']['measurements']['ambient_temperature']['value']
            self.request('PUT', path, {'min_c': round(temperature - 20, 2),
                                      'max_c': round(temperature - 2, 2), 'attention_margin_c': 1})
            alarm = eventually(lambda: (row if (row := self.stack.live())['telemetry']['data']['actuators']['buzzer']['actual_state']
                                       and row['commands']['buzzer']['data']['status'] == 'confirmed' else None), 60)
            browser = self.browser('actuators', desired_led_state=not before)
            identifier = str(UUID(browser['command_id']))
            confirmed = eventually(lambda: (row if (row := self.request('GET', '/api/v3/commands/' + identifier))['data']['status'] == 'confirmed' else None), 35)
            assert confirmed['data']['desired_state'] == (not before)
            observed = eventually(lambda: (row if (row := self.stack.live())['telemetry']['data']['actuators']['led']['actual_state'] != before else None), 35)
            self.request('PUT', path, {'min_c': -100, 'max_c': 100, 'attention_margin_c': 1})
            eventually(lambda: not self.stack.live()['telemetry']['data']['actuators']['buzzer']['actual_state'], 60)
            self.phase(8, 'automatic_buzzer_manual_led', alarm=alarm['commands']['buzzer'],
                       led_command=confirmed, observed_event_id=observed['telemetry']['event_id'], browser=browser)
        finally:
            self.request('PUT', path, self.saved_thresholds[1])
            self.request('POST', '/api/v3/devices/sim-lab-01/led/commands', {'desired_state': before})
            self.saved_thresholds = None

    def jobs(self):
        started = time.monotonic()
        accepted = self.browser('laboratory', action='create', wait_for_completion=False)
        generation_id = accepted['job']['id']
        self.private(generation_job_id=generation_id, action='observe')
        generated = self.stack.job_done(generation_id)
        dataset = self.request('GET', '/api/v3/datasets/' + generated['result_id'])
        assert dataset['row_count'] >= 1_000_000 and generated['config']['seed'] == 42
        self.private(dataset_id=generated['result_id'])
        self.phase(9, 'million_rows_ui_generation', job=generated, dataset=dataset,
                   seconds=round(time.monotonic() - started, 3),
                   browser=self.browser('laboratory', action='observe', wait_for_completion=True))
        started = time.monotonic()
        accepted = self.browser('training', action='create', wait_for_completion=False)
        training_id = accepted['job']['id']
        self.private(training_job_id=training_id, action='observe')
        # A queued job can wait for the ongoing preload lock before it starts training.
        paused = eventually(lambda: (row if (row := self.request('GET', '/api/v3/llm/status'))['state'] == 'paused'
                                     and self.request('GET', f'/api/v3/jobs/{training_id}')['status'] == 'running'
                                     else None), 1200)
        queue_and_pause_seconds = round(time.monotonic() - started, 3)
        trained = self.stack.job_done(training_id)
        result = self.request('GET', f'/api/v3/jobs/{training_id}/result')
        for target in ('health', 'rul'):
            assert result[target]['status'] == 'eligible'
            assert set(result[target]['partition_rows']) == {'train', 'validation', 'test'}
            assert all(result[target]['partition_rows'].values())
            assert len(result[target]['diagnostics']['scatter']) > 0
            assert len(result[target]['diagnostics']['permutation']['features']) > 0
            for partition in ('validation', 'test'):
                assert set(result[target]['metrics'][partition]) == {'baseline', 'candidate'}
        observation = self.browser('training', action='observe', wait_for_completion=True)
        activation = self.request('POST', '/api/v3/model-activations', {'model_id': trained['result_id']}, 202)
        def activated():
            row = self.request('GET', '/api/v3/model-activations/' + activation['id'])
            assert row['status'] != 'failed', 'Real model activation failed'
            return row if row['status'] == 'active' else None
        active_request = eventually(activated, 180)
        active = self.request('GET', '/api/v3/models/active')
        assert str(active['model_id']) == trained['result_id']
        self.private(model_id=trained['result_id'], activation_id=activation['id'])
        self.phase(10, 'two_targets_trained_and_activated', job=trained, result=result,
                   active=active, activation=active_request, llm_during_training=paused,
                   queue_and_pause_seconds=queue_and_pause_seconds,
                   seconds=round(time.monotonic() - started, 3), browser=observation)

    def prediction(self):
        snapshot = self.request('GET', INSIGHTS)
        return snapshot if snapshot['availability'] == 'available' else None

    def fault(self):
        started = datetime.fromisoformat(self.state['warmup_started_at'].replace('Z', '+00:00'))
        remaining = max(0, 3610 - (datetime.now(UTC) - started).total_seconds())
        self.report['causal_warmup'] = {'started_at': started.isoformat(), 'remaining_seconds_at_step11': remaining,
                                         'windows_seconds': [900, 3600], 'simulator_step_seconds': 60}
        self.save()
        while remaining > 0:
            time.sleep(min(30, remaining))
            remaining = max(0, 3610 - (datetime.now(UTC) - started).total_seconds())
        baseline = eventually(self.prediction, 300)
        cutoff = baseline['prediction']['data']['input_received_at']
        with psycopg.connect(**self.stack.pg) as connection:
            span = connection.execute('SELECT count(*),min(received_at),max(received_at) FROM inference_events '
                                      'WHERE owner_user_id=%s AND equipment_id=%s AND received_at<=%s AND received_at>=%s',
                                      (self.stack.values['GATEWAY_OWNER_USER_ID'], self.stack.catalog['equipment_id'], cutoff, started)).fetchone()
            anchor = connection.execute('SELECT source_event_id,received_at FROM inference_events '
                                        'WHERE owner_user_id=%s AND equipment_id=%s '
                                        "AND received_at < %s::timestamptz - interval '3600 seconds' AND received_at >= %s "
                                        'ORDER BY received_at DESC LIMIT 1',
                                        (self.stack.values['GATEWAY_OWNER_USER_ID'], self.stack.catalog['equipment_id'], cutoff, started)).fetchone()
        assert span[0] > 0 and (span[2] - span[1]).total_seconds() >= 3600 and anchor
        self.report['causal_warmup']['sql_history'] = {'count': span[0], 'min_received_at': span[1],
            'max_received_at': span[2], 'anchor_event_id': str(anchor[0]), 'anchor_received_at': anchor[1],
            'prediction_event_id': baseline['prediction']['event_id'], 'input_received_at': cutoff,
            'model_id': baseline['prediction']['data']['model_id']}
        self.save()
        assert not baseline['active_alerts'], 'Unexpected baseline alert; investigate the live baseline before injecting'
        health = baseline['prediction']['data']['health_score']
        rul = baseline['prediction']['data']['rul_hours']
        assert health > 1, 'Baseline already degraded; no honest fault trajectory can be claimed'
        assert rul > RUL_DROP_HOURS, 'Baseline RUL is already at its floor; a decreasing RUL cannot honestly be demonstrated'
        self.saved_rules = dict(baseline['rules'])
        demo_rules = {**baseline['rules'], 'health_critical': round(health - 0.5, 5),
                      'health_recovery': min(100, round(health + 0.1, 5)),
                      'rul_critical_hours': 0, 'rul_recovery_hours': max(1, baseline['prediction']['data']['rul_hours'] + 1),
                      'open_count': 3, 'close_count': 10}
        self.request('PUT', RULES, demo_rules)
        before_fault = self.stack.live()['telemetry']
        assert not self.request('GET', INSIGHTS)['active_alerts'], 'Demo threshold opened an alert before fault injection'
        injected = datetime.now(UTC).isoformat()
        self.control('inject_fault', '--fault', 'bearing_wear')
        self.report['fault'] = {'baseline': baseline, 'original_rules': self.saved_rules,
                                 'baseline_telemetry': before_fault,
                                 'demonstration_rules': demo_rules, 'injected_at': injected,
                                 'degradation_acceptance': {'health_drop_points': 0.5,
                                     'rul_drop_hours': RUL_DROP_HOURS, 'vibration_increase_mm_s': 0.2},
                                 'threshold_choice': 'health baseline minus 0.5 points, fixed before injection; synthetic demonstration only'}
        self.save()
        deadline, final = time.monotonic() + 900, None
        while time.monotonic() < deadline:
            snapshot = self.prediction()
            if snapshot:
                prediction = snapshot['prediction']
                with psycopg.connect(**self.stack.pg) as connection:
                    streak = connection.execute('SELECT critical_streak,recovery_streak FROM predictive_state '
                                                'WHERE owner_user_id=%s', (self.stack.values['GATEWAY_OWNER_USER_ID'],)).fetchone()
                self.report['fault_samples'].append({'at': datetime.now(UTC).isoformat(), 'prediction': prediction,
                                                     'trend': snapshot['trend'], 'active_alerts': snapshot['active_alerts'],
                                                     'health_drop_points': health - prediction['data']['health_score'],
                                                     'rul_drop_hours': rul - prediction['data']['rul_hours'],
                                                     'streak': streak})
                self.save()
                injection_time = datetime.fromisoformat(injected)
                new_alerts = [alert for alert in snapshot['active_alerts']
                              if datetime.fromisoformat(alert['opened_at'].replace('Z', '+00:00')) >= injection_time]
                source_after_fault = datetime.fromisoformat(
                    prediction['data']['input_received_at'].replace('Z', '+00:00')) >= injection_time
                vibration = self.stack.live()['telemetry']['data']['measurements']['vibration']['value']
                baseline_vibration = before_fault['data']['measurements']['vibration']['value']
                if (new_alerts and source_after_fault and prediction['data']['health_score'] <= health - 0.5
                        and prediction['data']['rul_hours'] <= rul - RUL_DROP_HOURS
                        and vibration > baseline_vibration + 0.2):
                    final = snapshot
                    self.report['fault']['final_telemetry'] = self.stack.live()['telemetry']
                    self.report['fault']['observed_degradation'] = {
                        'health_baseline': health, 'health_final': prediction['data']['health_score'],
                        'rul_hours_baseline': rul, 'rul_hours_final': prediction['data']['rul_hours'],
                        'health_drop_points': health - prediction['data']['health_score'],
                        'rul_drop_hours': rul - prediction['data']['rul_hours'],
                        'vibration_baseline_mm_s': baseline_vibration, 'vibration_final_mm_s': vibration}
                    break
            time.sleep(5)
        assert final is not None, 'Live fault did not decrease both health and RUL and open a hysteresis alert in 900 seconds'
        self.private(require_prediction=True, require_alert=True, fault_evidence=final)
        observed = self.browser('fault')
        self.control('stop')
        try:
            stale = eventually(lambda: (row if (row := self.request('GET', INSIGHTS))['availability'] == 'stale' else None), 60)
            alert_ids = {alert['alert_id'] for alert in final['active_alerts']}
            assert alert_ids <= {alert['alert_id'] for alert in stale['active_alerts']}, 'Missing telemetry must not resolve predictive alerts'
            missing = self.browser('fault', require_prediction=False, require_alert=False)
            assert missing['insights']['availability'] == 'stale'
        finally:
            self.control('start')
        fresh = eventually(self.prediction, 90)
        self.phase(11, 'live_fault_prediction_hysteresis_twin_and_recovery', baseline=baseline,
                   fault=final, stale=stale, recovered=fresh, browser=observed,
                   stale_alert_ids_preserved=sorted(alert_ids))

    def assistant(self):
        self.stack.llm_ready()
        before = self.request('GET', INSIGHTS)
        context_before = self.assistant_context()
        result = self.browser('assistant', question='Informe saúde, RUL e alertas do sim-lab-01. Use Saúde: valor em pontos; RUL: valor em horas.')
        context_after = self.assistant_context()
        answer = result['assistant']['answer'].lower()
        assert not any(text in answer for text in ('led foi ligado', 'liguei o led', 'desliguei o led'))
        assert any(word in answer for word in ('saúde', 'saude'))
        assert any(word in answer for word in ('rul', 'vida útil', 'vida util', 'horas'))
        normalized = answer.replace('*', '').replace('`', '')
        labels = {'health': r'(?:saúde|saude|health)', 'rul_h': r'(?:rul|vida [úu]til(?: restante)?)'}
        for field in ('health', 'rul_h'):
            bounds = [context['equipment'][0][field] for context in (context_before, context_after)]
            assert all(value is not None for value in bounds), 'Assistant comparison needs current available predictions'
            numbers = [float(number.replace(',', '.')) for number in re.findall(
                labels[field] + r'\s*(?:estimad[ao]\s*)?(?::|é|de|está em)\s*(\d+(?:[.,]\d+)?)', normalized)]
            assert any(min(bounds) - 1 <= value <= max(bounds) + 1 for value in numbers), (
                'Assistant labelled numerical answer disagrees with the observed owner-scoped facts', field)
        assert 'alert' in answer and 'preditiv' in answer
        metrics = self.browser('assistant', question='Informe os MAEs de teste do modelo ativo neste formato: Saúde: valor; RUL: valor.')
        metric_answer = metrics['assistant']['answer'].lower().replace('*', '').replace('`', '')
        for target, label in (('health', labels['health']), ('rul', labels['rul_h'])):
            expected = context_after['model']['test_mae'][target]
            values = [float(number.replace(',', '.')) for number in re.findall(
                label + r'\s*(?:estimad[ao]\s*)?(?::|é|de|está em)\s*(\d+(?:[.,]\d+)?)', metric_answer)]
            assert any(abs(value - expected) <= 0.1 for value in values), 'Assistant MAE disagrees with active model'
        architecture = self.browser('assistant', question='Explique o caminho dos sensores até a interface e o papel do MQTT, RabbitMQ, InfluxDB e PostgreSQL.')
        architectural_answer = architecture['assistant']['answer'].lower()
        assert all(word in architectural_answer for word in ('mqtt', 'rabbitmq', 'influx', 'postgres'))
        self.phase(12, 'local_assistant_real_sse', authorized_snapshot_before=before, response=result['assistant'],
                   metrics_response=metrics['assistant'], architecture_response=architecture['assistant'],
                   context_before=context_before, context_after=context_after,
                   numerical_tolerance={'health_points': 1, 'rul_hours': 1, 'test_mae': 0.1},
                   semantic_approval='pending_external_review',
                   semantic_limit='Automatic checks are necessary but do not approve semantics: explicit external review '
                                  'must verify counts, labelled values and architectural claims against the recorded facts. '
                                  'Synthetic values do not certify physical diagnosis')

    def assistant_context(self):
        owner = str(UUID(self.stack.values['GATEWAY_OWNER_USER_ID']))
        source = ('import json; from uuid import UUID; '
                  'from backend.app.config.settings import RuntimeSettings; '
                  'from backend.app.services.assistant_context import AssistantContext; '
                  'print(json.dumps(AssistantContext(RuntimeSettings()).build(UUID("' + owner + '"))))')
        return json.loads(self.stack.command('exec', '-T', 'backend', 'python', '-c', source))

    def run(self):
        self.pin_frontend()
        assert self.stack.healthy()
        for path in ('/health/live', '/health/ready'):
            assert httpx.get(self.stack.url + path, timeout=30, trust_env=False).status_code == 200
        self.stack.llm_ready()
        self.phase(1, 'fourteen_healthy_and_preloaded', services=list(SERVICES))
        self.roles()
        self.telemetry()
        schema = httpx.get(self.stack.url + '/openapi.json', timeout=30, trust_env=False)
        assert schema.status_code == 200 and '/api/v3/monitoring/summary' in schema.json()['paths']
        self.phase(4, 'fastapi_rest_openapi', documented_routes=len(schema.json()['paths']), browser=self.browser('docs'))
        self.messaging()
        self.storage()
        self.phase(7, 'real_websocket_dashboard_and_http_recovery', browser=self.browser('dashboard'))
        self.actuators()
        self.jobs()
        self.fault()
        self.assistant()
        assert [row['step'] for row in self.report['phases']] == list(range(1, 13))


def test_final_presentation_in_professor_order_with_live_causal_fault():
    if os.environ.get('COLDSAFE_REHEARSAL_INTEGRATION') != '1':
        pytest.skip('Set COLDSAFE_REHEARSAL_INTEGRATION=1; a real rehearsal requires at least one hour')
    attached = os.environ.get('COLDSAFE_REHEARSAL_STATE')
    with tempfile.TemporaryDirectory(prefix='coldsafe-b236-') as temporary:
        if attached:
            path = Path(attached)
            state = json.loads(path.read_text())
            stack = Stack(Path(state['directory']))
            for key in ('project', 'base', 'url', 'token', 'password', 'catalog', 'values', 'pg'):
                setattr(stack, key, state[key])
        else:
            stack = Stack(Path(temporary))
            stack.project = 'coldsafe-b236-' + secrets.token_hex(4)
            stack.base[stack.base.index('-p') + 1] = stack.project
            try:
                prepare(stack)
                stack.values['SIMULATOR_STEP_SECONDS'] = '60'
                stack.save_env()
                stack.command('up', '-d', '--build', '--wait', '--wait-timeout', '420')
                stack.url = 'http://127.0.0.1:' + stack.port('frontend', 8080)
                stack.token = stack.request('POST', '/api/v1/auth/login',
                                            {'email': 'stack@example.invalid', 'password': stack.password})['token']
            except BaseException as error:
                try:
                    stack.report.update(result='failed', failure=stack.clean(str(error))[-4000:])
                    if evidence := os.environ.get('COLDSAFE_REHEARSAL_EVIDENCE'):
                        Path(evidence).write_text(json.dumps(stack.report, indent=2))
                finally:
                    stack.command('down', '--volumes', '--remove-orphans')
                raise
            path = Path(temporary) / 'state.json'
            state = {key: getattr(stack, key) for key in ('project', 'base', 'url', 'token', 'password', 'catalog', 'values', 'pg')}
            state.update(directory=temporary, output_dir=str(Path(temporary) / 'screenshots'),
                         warmup_started_at=datetime.now(UTC).isoformat(),
                         accounts={'admin': {'email': 'stack@example.invalid', 'password': stack.password}})
        rehearsal = Rehearsal(stack, state, path)
        try:
            rehearsal.run()
            rehearsal.report['result'] = 'passed'
        except BaseException as error:
            rehearsal.report.update(result='failed', failure=rehearsal.clean(error)[-4000:])
            raise
        finally:
            try:
                if rehearsal.saved_rules is not None:
                    rehearsal.request('PUT', RULES, rehearsal.saved_rules)
                    rehearsal.report['predictive_rules_restored'] = True
                if rehearsal.saved_thresholds is not None:
                    rehearsal.request('PUT', *rehearsal.saved_thresholds)
            except BaseException as error:
                rehearsal.report.update(result='failed', restoration_failure=rehearsal.clean(error)[-4000:])
                raise
            finally:
                try:
                    if not attached:
                        stack.command('down', '--volumes', '--remove-orphans')
                        rehearsal.report['cleaned_up'] = True
                finally:
                    rehearsal.report['ended_at'] = datetime.now(UTC).isoformat()
                    rehearsal.report['duration_seconds'] = round(time.monotonic() - rehearsal.started_monotonic, 3)
                    rehearsal.save()
