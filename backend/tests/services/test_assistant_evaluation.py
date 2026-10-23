"""Evaluation records evidence; keyword presence never certifies LLM correctness."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.evaluate_assistant import CASES, evaluation_record, require_disposable, run_case


def test_six_required_topics_have_portuguese_questions_and_review_criteria():
    assert [case['topic'] for case in CASES] == [
        'estado_atual', 'pior_equipamento', 'rul', 'alerta', 'metricas', 'arquitetura',
    ]
    assert all(0 < len(case['question'].encode()) <= 256 and case['rubric'] for case in CASES)


@pytest.mark.parametrize('database,url', [
    ('coldsafe', 'http://ollama:11434'),
    ('coldsafe_b231_old', 'http://ollama:11434'),
    ('coldsafe_b232_test', 'https://example.invalid'),
])
def test_refuses_personal_database_or_nonlocal_model(database, url):
    with pytest.raises(ValueError):
        require_disposable(SimpleNamespace(postgres_db=database, ollama_url=url))


def test_accepts_only_scoped_disposable_configuration():
    require_disposable(SimpleNamespace(postgres_db='coldsafe_b232_test', ollama_url='http://ollama:11434'))


def test_fluent_or_numeric_keyword_answer_still_needs_factual_review():
    result = {'question': 'Qual a saúde?', 'answer': '20 10 MAE arquitetura. Está tudo perfeito.',
              'context': {'equipment': [{'health': 20, 'rul_h': 10}]}, 'sse_events': 4}
    record = evaluation_record(CASES[0], result, {'health': 20})
    assert record['assessment']['status'] == 'pending_manual_review'
    assert record['assessment']['factual_correctness_certified'] is False
    assert record['expected_facts'] == {'health': 20}
    assert record['actual_answer'] == result['answer']
    assert 'revis' in record['assessment']['instruction'].lower()


def test_empty_or_cross_account_answer_is_flagged_instead_of_approved():
    for answer, flag in [('', 'empty_answer'), ('A leitura de private-fixture-1 é 1.', 'other_account_identifier')]:
        record = evaluation_record(CASES[0], {'answer': answer, 'context': {}, 'question': 'estado'}, {})
        assert flag in record['assessment']['automatic_flags']
        assert record['assessment']['status'] == 'failed_machine_check'
        assert record['assessment']['factual_correctness_certified'] is False


def test_transport_failure_is_retained_as_failed_evidence(monkeypatch):
    from backend.app.services.assistant import AssistantError
    service = SimpleNamespace(context=SimpleNamespace(build=lambda _: {'equipment': []}))
    monkeypatch.setattr('scripts.evaluate_assistant.probe', AsyncMock(side_effect=AssistantError('LLM_BUSY')))
    record, _ = asyncio.run(run_case(service, 'owner', CASES[0], {}, None))
    assert record['transport_error_code'] == 'LLM_BUSY'
    assert record['assessment']['status'] == 'failed_machine_check'


def test_original_and_holdout_records_keep_their_fixture_identity_without_auto_approval():
    for fixture_set in ('original', 'holdout'):
        case = {**CASES[0], 'fixture_set': fixture_set}
        record = evaluation_record(case, {'question': case['question'], 'answer': '32,5 7,25 3,7 26,4',
                                         'context': {}}, {})
        assert record['fixture_set'] == fixture_set
        assert record['assessment']['status'] == 'pending_manual_review'
        assert record['assessment']['factual_correctness_certified'] is False


def test_holdout_covers_six_topics_and_distinguishes_lowest_rul_from_lowest_health():
    from scripts.evaluate_assistant import HOLDOUT_CASES
    assert [case['topic'] for case in HOLDOUT_CASES] == [case['topic'] for case in CASES]
    assert all(case['fixture_set'] == 'holdout' and 0 < len(case['question'].encode()) <= 256
               for case in HOLDOUT_CASES)
    rul = next(case for case in HOLDOUT_CASES if case['topic'] == 'rul')
    assert 'menor RUL' in rul['question']
    assert '7,25' in rul['rubric'] and '18,75' in rul['rubric']


def test_holdout_fixture_mutation_refuses_personal_database_before_connect(monkeypatch):
    from scripts.evaluate_assistant import apply_holdout
    connection = MagicMock()
    monkeypatch.setattr('scripts.evaluate_assistant.connect', connection)
    with pytest.raises(ValueError):
        apply_holdout(SimpleNamespace(postgres_db='coldsafe', ollama_url='http://ollama:11434'), 'owner')
    connection.assert_not_called()


@pytest.mark.parametrize('names', [[], ['private-fixture-0'], ['private-fixture-0', 'unexpected'],
                                  ['private-fixture-0', 'owned-healthier'] * 2])
def test_holdout_refuses_unexpected_owned_fixtures_without_writing(monkeypatch, names):
    from scripts.evaluate_assistant import apply_holdout
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = [(name + '-id', name) for name in names]
    monkeypatch.setattr('scripts.evaluate_assistant.connect', lambda _: connection)
    with pytest.raises(ValueError, match='original two owned fixtures'):
        apply_holdout(SimpleNamespace(postgres_db='coldsafe_b232_test', ollama_url='http://ollama:11434'), 'owner-a')
    assert all(not call.args[0].startswith('UPDATE') for call in connection.execute.call_args_list)


def test_holdout_parameterizes_renamed_envelopes_predictions_and_owned_model_metrics(monkeypatch):
    from scripts.evaluate_assistant import apply_holdout
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = [('device-a', 'private-fixture-0'),
                                                            ('device-b', 'owned-healthier')]
    monkeypatch.setattr('scripts.evaluate_assistant.connect', lambda _: connection)
    apply_holdout(SimpleNamespace(postgres_db='coldsafe_b232_test', ollama_url='http://ollama:11434'), 'owner-a')
    calls = connection.execute.call_args_list
    assert calls[0].args[1] == ('owner-a',)
    assert [call.args[1] for call in calls if call.args[0].startswith('UPDATE devices')] == [
        ('holdout-fan-azul', 'device-a'), ('holdout-fan-cobre', 'device-b')]
    events = [call.args[1] for call in calls if call.args[0].startswith('UPDATE aiot_events')]
    assert [(args[0].obj, args[-1]) for args in events[::2]] == [
        ('holdout-fan-azul', 'device-a'), ('holdout-fan-cobre', 'device-b')]
    assert [(args[0].obj, args[1].obj, args[2]) for args in events[1::2]] == [
        (32.5, 18.75, 'device-a'), (74, 7.25, 'device-b')]
    assert calls[-1].args[1][0].obj == 3.7 and calls[-1].args[1][1].obj == 26.4
    assert calls[-1].args[1][2] == 'owner-a'
    assert all('holdout-fan-' not in call.args[0] for call in calls)


@pytest.mark.parametrize('has_data', [True, False])
def test_sql_oracle_preserves_source_units_and_missing_values_in_read_only_owner_scope(monkeypatch, has_data):
    from scripts.evaluate_assistant import sql_facts
    connection = MagicMock()
    connection.__enter__.return_value = connection
    sensors = {'ambient_temperature': {'value': 7.25, 'unit': 'degC'}}
    connection.execute.return_value.fetchall.return_value = [('holdout-fan-azul', 32.5, 18.75, sensors)] if has_data else []
    connection.execute.return_value.fetchone.side_effect = [('fixture-v1', 3.7, 26.4) if has_data else None,
                                                           (1 if has_data else 0,)]
    monkeypatch.setattr('scripts.evaluate_assistant.connect', lambda _: connection)
    facts = sql_facts('config', 'owner-a')
    assert facts['devices'] == ([{'device': 'holdout-fan-azul', 'health_points_0_100': 32.5,
                                 'rul_hours': 18.75, 'source_measurements': sensors}] if has_data else [])
    assert facts['model'] == ({'version': 'fixture-v1', 'health_test_mae_points': 3.7,
                               'rul_test_mae_hours': 26.4} if has_data else None)
    assert facts['predictive_alerts'] == (1 if has_data else 0)
    assert connection.execute.call_args_list[0].args == ('SET TRANSACTION READ ONLY',)
    assert all(call.args[1] == ('owner-a',) for call in connection.execute.call_args_list[1:])


def test_main_keeps_original_cases_then_holdout_restores_freshness_and_owner_rate_history(monkeypatch, tmp_path):
    import json
    from scripts import evaluate_assistant as evaluation
    config = SimpleNamespace(postgres_db='coldsafe_b232_test', ollama_url='http://ollama:11434')
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.side_effect = [(0,), ('empty-owner',), (0,), (0,)]
    original = {'scope': {'devices': 2, 'fresh_predictions': 2}, 'alerts': {'predictive': 1},
                'equipment': [{'device': 'private-fixture-0', 'health': 20, 'rul_h': 10}]}
    holdout = {'scope': {'devices': 2, 'fresh_predictions': 2}, 'alerts': {'predictive': 1},
               'equipment': [{'device': 'holdout-fan-azul', 'health': 32.5, 'rul_h': 18.75},
                             {'device': 'holdout-fan-cobre', 'health': 74, 'rul_h': 7.25}]}
    service = SimpleNamespace(context=SimpleNamespace(build=MagicMock(side_effect=[original, holdout])))
    facts = {'predictive_alerts': 1}
    holdout_facts = {'predictive_alerts': 1, 'devices': [
        {'device': 'holdout-fan-azul', 'health_points_0_100': 32.5, 'rul_hours': 18.75},
        {'device': 'holdout-fan-cobre', 'health_points_0_100': 74, 'rul_hours': 7.25}],
        'model': {'health_test_mae_points': 3.7, 'rul_test_mae_hours': 26.4}}
    oracle = MagicMock(side_effect=[facts, {'devices': []}, facts, holdout_facts])
    mutation = MagicMock()
    observed = []

    async def capture(_service, owner, case, expected, last):
        started = len(observed) + 1
        observed.append({'owner': owner, 'topic': case['topic'], 'last': last,
                         'started': started, 'now': service.context._now(), 'facts': expected})
        return evaluation_record(case, {'question': case['question'], 'answer': 'Revisão pendente.',
                                       'context': {}}, expected), started

    monkeypatch.setattr(evaluation, 'RuntimeSettings', lambda **_: config)
    monkeypatch.setattr(evaluation, 'initialize_schema', MagicMock())
    monkeypatch.setattr(evaluation, 'connect', lambda _: connection)
    monkeypatch.setattr(evaluation, 'OllamaClient', MagicMock())
    monkeypatch.setattr(evaluation, 'seed', lambda _: ['owner-a', 'owner-b'])
    monkeypatch.setattr(evaluation, 'extend_fixtures', MagicMock())
    monkeypatch.setattr(evaluation, 'AssistantService', lambda _: service)
    monkeypatch.setattr(evaluation, 'MeasuredTransport', MagicMock())
    monkeypatch.setattr(evaluation, 'sql_facts', oracle)
    monkeypatch.setattr(evaluation, 'apply_holdout', mutation, raising=False)
    monkeypatch.setattr(evaluation, 'run_case', capture)
    monkeypatch.setattr(evaluation, 'MODEL', 'evaluated-model', raising=False)
    output = tmp_path / 'evaluation.json'
    monkeypatch.setenv('ASSISTANT_EVALUATION_OUTPUT', str(output))
    asyncio.run(evaluation.main())
    report = json.loads(output.read_text())
    assert len(report['results']) == 14
    assert [row['topic'] for row in report['results'][:8]] == [case['topic'] for case in CASES] + ['sem_dados', 'dados_antigos']
    assert [row['fixture_set'] for row in report['results']] == ['original'] * 8 + ['holdout'] * 6
    assert report['model'] == 'evaluated-model'
    mutation.assert_called_once_with(config, 'owner-a')
    assert oracle.call_args_list[-1].args == (config, 'owner-a')
    assert all(row['facts'] is holdout_facts for row in observed[8:])
    assert observed[7]['facts']['current_health'] is observed[7]['facts']['current_rul'] is None
    assert (observed[7]['now'] - observed[0]['now']).total_seconds() == 31
    assert all(row['now'] == observed[0]['now'] for row in observed[8:])
    assert observed[6]['owner'] == 'empty-owner' and observed[6]['last'] is None
    assert observed[7]['last'] == observed[5]['started']
    assert observed[8]['last'] == observed[7]['started']
    assert report['acceptance_claimed'] is False
