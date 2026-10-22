"""Evaluation records evidence; keyword presence never certifies LLM correctness."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
