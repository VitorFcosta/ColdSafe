from copy import deepcopy

import pytest

from backend.app.services.predictive_alerts import DEFAULT_RULES, advance_streak, validate_rules


def state():
    return {'critical_streak': 0, 'recovery_streak': 0, 'health_score': None,
            'rul_hours': None, 'trend': 'unknown'}


def test_three_critical_and_ten_recovered_with_dead_band_and_zero_rul():
    current = state()
    for index in range(3):
        current, transition = advance_streak(current, 90, 0, False, DEFAULT_RULES)
        assert transition == ('opened' if index == 2 else None)
    current, transition = advance_streak(current, 35, 30, True, DEFAULT_RULES)
    assert transition is None and current['recovery_streak'] == 0
    for index in range(10):
        current, transition = advance_streak(current, 40, 48, True, DEFAULT_RULES)
        assert transition == ('closed' if index == 9 else None)


def test_unavailable_resets_streak_and_trend_without_closing():
    current, _ = advance_streak(state(), 20, 10, False, DEFAULT_RULES)
    current, transition = advance_streak(current, None, None, True, DEFAULT_RULES)
    assert transition is None
    assert current['critical_streak'] == current['recovery_streak'] == 0
    assert current['trend'] == 'unknown'


def test_trend_and_streak_do_not_mutate_input():
    original = state()
    saved = deepcopy(original)
    current, _ = advance_streak(original, 50, 100, False, DEFAULT_RULES)
    assert original == saved
    current, _ = advance_streak(current, 49, 100, False, DEFAULT_RULES)
    assert current['trend'] == 'declining'
    current, _ = advance_streak(current, 50, 101, False, DEFAULT_RULES)
    assert current['trend'] == 'improving'
    current, _ = advance_streak(current, 50, 101, False, DEFAULT_RULES)
    assert current['trend'] == 'stable'


@pytest.mark.parametrize('changes', [
    {'health_critical': -1}, {'health_recovery': 101}, {'health_recovery': 30},
    {'rul_critical_hours': -1}, {'rul_recovery_hours': 24},
    {'rul_recovery_hours': float('inf')}, {'health_critical': float('nan')},
    {'health_critical': True}, {'open_count': 0}, {'close_count': 101},
    {'open_count': 3.0}, {'extra': 1},
    {'rul_recovery_hours': 10 ** 1000}, {'open_count': 10 ** 1000},
])
def test_invalid_thresholds_rejected(changes):
    with pytest.raises(ValueError):
        validate_rules({**DEFAULT_RULES, **changes})


def test_rule_validation_requires_every_field_and_retains_valid_values():
    assert validate_rules(DEFAULT_RULES) == DEFAULT_RULES
    with pytest.raises(ValueError):
        validate_rules({'open_count': 3})
