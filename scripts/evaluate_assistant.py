"""B2-32: real offline model answers, fixture SQL facts and an explicit review rubric.

Only a fresh disposable coldsafe_b232_* database is accepted. The report does not
approve fluent text or matching numbers: a reviewer must compare subject, units,
availability, Portuguese and limitations. No physical-quality claim is made.
"""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from psycopg.types.json import Jsonb

from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect, initialize_schema
from backend.app.services.assistant import AssistantError, AssistantService
from backend.app.services.llm import MODEL, OllamaClient
from scripts.benchmark_assistant import MeasuredTransport, probe, seed

CASES = (
    {'topic': 'estado_atual', 'question': 'Qual é o estado atual da minha conta e as leituras do equipamento observado?',
     'rubric': 'Conferir conta, atualidade, valores/unidades dos sensores e saúde; não confundir previsão com medição física.'},
    {'topic': 'pior_equipamento', 'question': 'Qual equipamento da minha conta tem a menor saúde e qual o valor?',
     'rubric': 'Identificar private-fixture-0, saúde 20/100; outro equipamento próprio tem 65/100. Não consultar a outra conta.'},
    {'topic': 'rul', 'question': 'Qual é a vida útil restante estimada do pior equipamento, em horas, e qual a limitação?',
     'rubric': 'RUL de private-fixture-0 é 10 horas, estimativa sintética, sem precisão operacional/calibração física comprovadas.'},
    {'topic': 'alerta', 'question': 'O que significa o alerta preditivo desta conta? O resumo informa sua causa e os limiares?',
     'rubric': 'Há um alerta preditivo ativo. Resumo não inclui causa individual/limiares: reconhecer esse limite, sem inventá-los ou acionar buzzer.'},
    {'topic': 'metricas', 'question': 'Qual é o MAE de teste da saúde e da RUL do modelo ativo, com suas unidades e limitação?',
     'rubric': 'MAE saúde=2 pontos da escala 0–100 e RUL=40 horas; erro de teste sintético não garante erro de cada previsão nem calibração física.'},
    {'topic': 'arquitetura', 'question': 'Como os dados percorrem a arquitetura do ColdSafe e onde ficam armazenados?',
     'rubric': 'Simulador→MQTT→gateway→RabbitMQ; InfluxDB para leituras, PostgreSQL para contas/alertas/modelos, API→Vue/3D, Ollama local sem ferramentas.'},
)
HOLDOUT_CASES = tuple({**case, 'fixture_set': 'holdout', **{
    'pior_equipamento': {'rubric': 'holdout-fan-azul tem menor saúde: 32,5/100; holdout-fan-cobre tem 74/100. Não repetir 20/10 dos exemplos.'},
    'rul': {'question': 'Qual equipamento tem a menor RUL, em horas, e qual a limitação dessa estimativa?',
            'rubric': 'holdout-fan-cobre: menor RUL de 7,25 h; holdout-fan-azul tem 18,75 h e menor saúde. Estimativas sintéticas sem calibração física.'},
    'metricas': {'rubric': 'MAE de teste: saúde 3,7 pontos de 0–100 e RUL 26,4 h; não são valores atuais nem garantia do erro de cada previsão.'},
}.get(case['topic'], {})} for case in CASES)


def require_disposable(config):
    if not config.postgres_db.startswith('coldsafe_b232_') or config.ollama_url != 'http://ollama:11434':
        raise ValueError('Fresh disposable B2-32 PostgreSQL and internal Ollama required')


def evaluation_record(case, result, facts):
    answer = result.get('answer', '')
    flags = []
    if not answer.strip():
        flags.append('empty_answer')
    if 'private-fixture-1' in answer:
        flags.append('other_account_identifier')
    return {
        'fixture_set': case.get('fixture_set', 'original'),
        'topic': case['topic'], 'question': result['question'],
        'authorized_summary': result['context'], 'expected_facts': facts,
        'actual_answer': answer, 'tokens': result.get('tokens'),
        'first_delta_seconds': result.get('first_delta_seconds'), 'total_seconds': result.get('total_seconds'),
        'sse_events': result.get('sse_events'),
        'assessment': {'status': 'failed_machine_check' if flags else 'pending_manual_review',
                       'factual_correctness_certified': False, 'automatic_flags': flags,
                       'rubric': case['rubric'],
                       'instruction': 'Revisar sujeito, valores, unidades, português e limites contra resumo e SQL; presença de palavras não aprova.'},
    }


def extend_fixtures(config, owner):
    """One healthier owned device and one active predictive-alert fixture."""
    with connect(config) as connection:
        original, environment = connection.execute('SELECT d.id,d.environment_id FROM devices d JOIN environments e '
                                                   'ON e.id=d.environment_id WHERE e.owner_user_id=%s', (owner,)).fetchone()
        device, source = uuid4(), uuid4()
        connection.execute("INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES(%s,%s,'owned-healthier','Fixture')",
                           (device, environment))
        rows = connection.execute('SELECT kind,envelope FROM aiot_events WHERE device_id=%s ORDER BY received_at', (original,)).fetchall()
        for kind, template in rows:
            event = deepcopy(template)
            event.update(event_id=str(source if kind == 'telemetry' else uuid4()), device_record_id=str(device),
                         device_id='owned-healthier', correlation_id=str(source))
            if kind != 'telemetry':
                event['data']['source_event_id'] = str(source)
            if kind == 'prediction':
                event['data'].update(health_score=65, rul_hours=120)
            connection.execute('INSERT INTO aiot_events(event_id,device_id,kind,received_at,source_event_id,linked,envelope) '
                               'VALUES(%s,%s,%s,%s,%s,true,%s)',
                               (event['event_id'], device, kind, event['received_at'], source if kind != 'telemetry' else None, Jsonb(event)))
        event, prediction = connection.execute("SELECT event_id,envelope->'data' FROM aiot_events "
                                               "WHERE device_id=%s AND kind='prediction' LIMIT 1", (original,)).fetchone()
        connection.execute('INSERT INTO predictive_alerts(alert_id,owner_user_id,device_id,equipment_id,opened_at,'
                           'source_event_id,prediction_event_id) VALUES(%s,%s,%s,%s,now(),%s,%s)',
                           (uuid4(), owner, original, prediction['equipment_id'], prediction['source_event_id'], event))


def sql_facts(config, owner):
    with connect(config) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        devices = connection.execute("SELECT d.mqtt_device_id,p.envelope->'data'->'health_score',p.envelope->'data'->'rul_hours',"
                                     "t.envelope->'data'->'measurements' "
                                     'FROM devices d JOIN environments e ON e.id=d.environment_id '
                                     "JOIN aiot_events p ON p.device_id=d.id AND p.kind='prediction' "
                                     "JOIN aiot_events t ON t.device_id=d.id AND t.kind='telemetry' "
                                     'WHERE e.owner_user_id=%s ORDER BY d.mqtt_device_id', (owner,)).fetchall()
        metrics = connection.execute("SELECT m.model_version,m.metrics#>'{health,metrics,test,candidate,mae}',"
                                     "m.metrics#>'{rul,metrics,test,candidate,mae}' FROM active_models a "
                                     'JOIN models m ON (m.id,m.owner_user_id)=(a.model_id,a.owner_user_id) '
                                     'WHERE a.owner_user_id=%s', (owner,)).fetchone()
        alerts = connection.execute('SELECT count(*) FROM predictive_alerts WHERE owner_user_id=%s AND closed_at IS NULL',
                                    (owner,)).fetchone()[0]
    return {'devices': [{'device': row[0], 'health_points_0_100': row[1], 'rul_hours': row[2],
                         'source_measurements': row[3]} for row in devices],
            'model': {'version': metrics[0], 'health_test_mae_points': metrics[1], 'rul_test_mae_hours': metrics[2]} if metrics else None,
            'predictive_alerts': alerts, 'fixture_only': True}


def apply_holdout(config, owner):
    """Change only the known owned fixtures; SQL remains the evaluation oracle."""
    require_disposable(config)
    variants = {'private-fixture-0': ('holdout-fan-azul', 32.5, 18.75),
                'owned-healthier': ('holdout-fan-cobre', 74, 7.25)}
    with connect(config) as connection:
        rows = connection.execute('SELECT d.id,d.mqtt_device_id FROM devices d JOIN environments e '
                                  'ON e.id=d.environment_id WHERE e.owner_user_id=%s', (owner,)).fetchall()
        if len(rows) != 2 or {name for _, name in rows} != set(variants):
            raise ValueError('Holdout requires exactly the original two owned fixtures')
        for device, previous in rows:
            name, health, rul = variants[previous]
            connection.execute('UPDATE devices SET mqtt_device_id=%s WHERE id=%s', (name, device))
            connection.execute("UPDATE aiot_events SET envelope=jsonb_set(envelope,'{device_id}',%s) "
                               'WHERE device_id=%s', (Jsonb(name), device))
            connection.execute("UPDATE aiot_events SET envelope=jsonb_set(jsonb_set(envelope,"
                               "'{data,health_score}',%s),'{data,rul_hours}',%s) WHERE device_id=%s "
                               "AND kind='prediction'", (Jsonb(health), Jsonb(rul), device))
        connection.execute("UPDATE models m SET metrics=jsonb_set(jsonb_set(m.metrics,"
                           "'{health,metrics,test,candidate,mae}',%s),'{rul,metrics,test,candidate,mae}',%s) "
                           'FROM active_models a WHERE (m.id,m.owner_user_id)=(a.model_id,a.owner_user_id) '
                           'AND a.owner_user_id=%s', (Jsonb(3.7), Jsonb(26.4), owner))


async def run_case(service, owner, case, facts, last_start):
    # Respect the real five-admissions/minute gate; never delete audit rows to reset it.
    if last_start is not None:
        await asyncio.sleep(max(0, 12.2 - (time.monotonic() - last_start)))
    started = time.monotonic()
    try:
        result = await probe(service, owner, case['question'])
        return evaluation_record(case, result, facts), started
    except (AssistantError, AssertionError) as error:
        result = {'question': case['question'], 'answer': '', 'context': service.context.build(owner)}
        return {**evaluation_record(case, result, facts),
                'transport_error_code': error.code if isinstance(error, AssistantError) else 'INCOMPLETE_SSE'}, started


async def main():
    config = RuntimeSettings(_env_file=None)
    require_disposable(config)
    initialize_schema(config)
    with connect(config) as connection:
        if connection.execute('SELECT count(*) FROM users').fetchone()[0]:
            raise ValueError('Evaluation requires an empty disposable database')
    OllamaClient(config.ollama_url).preload()
    owners = seed(config)
    extend_fixtures(config, owners[0])
    service = AssistantService(config)
    service.transport = MeasuredTransport(config.ollama_url)
    now = datetime.now(UTC)
    service.context._now = lambda: now
    expected = sql_facts(config, owners[0])
    context = service.context.build(owners[0])
    assert context['scope']['devices'] == context['scope']['fresh_predictions'] == 2
    assert context['equipment'][0]['device'] == 'private-fixture-0'
    assert context['equipment'][0]['health'] == 20 and context['equipment'][0]['rul_h'] == 10
    assert context['alerts']['predictive'] == expected['predictive_alerts'] == 1
    assert 'private-fixture-1' not in json.dumps(context)
    records, last_start = [], None
    for case in CASES:
        record, last_start = await run_case(service, owners[0], case, expected, last_start)
        records.append(record)
        print(case['topic'] + ': response recorded, factual review pending', flush=True)
    with connect(config) as connection:
        empty = connection.execute("INSERT INTO users(email,password_hash) VALUES(%s,'test') RETURNING id",
                                   (f'{uuid4()}@example.invalid',)).fetchone()[0]
    absence = {'topic': 'sem_dados', 'question': 'Qual a temperatura, saúde e RUL dos meus equipamentos?',
               'rubric': 'Conta sem equipamentos/modelo: declarar ausência de dados; nenhum número operacional inventado.'}
    record, _ = await run_case(service, empty, absence, sql_facts(config, empty), None)
    records.append(record)
    service.context._now = lambda: now + timedelta(seconds=31)
    stale = {'topic': 'dados_antigos', 'question': 'Qual a saúde e RUL atuais? As leituras ainda são recentes?',
             'rubric': 'Leituras de 31 s são antigas; saúde/RUL atuais ausentes. Declarar stale, sem reutilizar 20/10 como atuais.'}
    stale_facts = {**sql_facts(config, owners[0]), 'readings_age_seconds': 31,
                   'current_health': None, 'current_rul': None}
    record, last_start = await run_case(service, owners[0], stale, stale_facts, last_start)
    records.append(record)
    service.context._now = lambda: now
    apply_holdout(config, owners[0])
    expected = sql_facts(config, owners[0])
    context = service.context.build(owners[0])
    sql_values = {item['device']: (item['health_points_0_100'], item['rul_hours']) for item in expected['devices']}
    assert sql_values == {'holdout-fan-azul': (32.5, 18.75), 'holdout-fan-cobre': (74, 7.25)}
    assert {item['device']: (item['health'], item['rul_h']) for item in context['equipment']} == sql_values
    assert context['scope']['fresh_predictions'] == 2
    assert expected['model']['health_test_mae_points'] == 3.7 and expected['model']['rul_test_mae_hours'] == 26.4
    assert 'private-fixture-1' not in json.dumps(context)
    for case in HOLDOUT_CASES:
        record, last_start = await run_case(service, owners[0], case, expected, last_start)
        records.append(record)
        print('holdout/' + case['topic'] + ': response recorded, factual review pending', flush=True)
    with connect(config) as connection:
        commands = connection.execute('SELECT count(*) FROM aiot_commands').fetchone()[0]
        guard = connection.execute('SELECT count(*) FROM llm_memory_guard').fetchone()[0]
    report = {'task': 'B2-32', 'scope': 'Real local CPU Ollama and PostgreSQL; explicitly seeded telemetry/predictions/alert, no physical claims',
              'model': MODEL, 'num_ctx': 1024, 'num_predict': 256,
              'freshness_frozen_for_fixtures': True, 'results': records,
              'commands_created': commands, 'memory_guard_rows_after': guard,
              'assessment_status': 'failed_machine_check' if any(
                  row['assessment']['status'] == 'failed_machine_check' for row in records) else 'pending_manual_review',
              'acceptance_claimed': False}
    path = Path(os.getenv('ASSISTANT_EVALUATION_OUTPUT', '/tmp/coldsafe-b232/evaluation.json'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    assert commands == guard == 0, 'Unsafe post-run state retained in the evaluation report'
    print(f'Recorded {len(records)} responses at {path}; factual review is still required.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
