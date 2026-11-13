from dataclasses import replace

import pytest

from backend.tests.api.test_aiot_api import client_v3


RULES = {
    'health_critical': 30.0, 'health_recovery': 40.0,
    'rul_critical_hours': 24.0, 'rul_recovery_hours': 48.0,
    'open_count': 3, 'close_count': 10,
}


def test_insights_requires_session_and_propagates_owner():
    client, service, *_rest, state = client_v3()
    endpoint = '/api/v3/insights?device_id=owned'
    service.insights.return_value = {'device_id': 'owned', 'availability': 'no_data'}
    assert client.get(endpoint).status_code == 401
    result = client.get(endpoint, headers={'Authorization': 'Bearer owner'})
    assert result.status_code == 200
    assert result.json()['meta']['schema_version'] == 3
    assert result.json()['data']['availability'] == 'no_data'
    service.insights.assert_called_once_with(state['owner'], 'owned')
    service.insights.return_value = None
    assert client.get(endpoint, headers={'Authorization': 'Bearer owner'}).status_code == 404


def test_predictive_rules_require_operator_and_pass_validated_values():
    client, service, *_rest, state = client_v3()
    endpoint = '/api/v3/insights/rules?device_id=owned'
    headers = {'Authorization': 'Bearer owner'}
    assert client.put(endpoint, json=RULES).status_code == 401
    assert client.put(endpoint, headers=headers, json=RULES).status_code == 403
    service.update_predictive_rules.assert_not_called()
    state['principal'] = replace(state['principal'], role='operator')
    service.update_predictive_rules.return_value = RULES
    result = client.put(endpoint, headers=headers, json=RULES)
    assert result.status_code == 200
    assert result.json()['data'] == RULES
    service.update_predictive_rules.assert_called_once_with(state['owner'], 'owned', RULES)
    service.update_predictive_rules.return_value = None
    assert client.put(endpoint, headers=headers, json=RULES).status_code == 404
    service.update_predictive_rules.side_effect = PermissionError('FORBIDDEN')
    assert client.put(endpoint, headers=headers, json=RULES).status_code == 403


@pytest.mark.parametrize('changes', [
    {'health_critical': -1}, {'health_recovery': 101},
    {'health_critical': 40}, {'rul_critical_hours': -1},
    {'rul_recovery_hours': 24}, {'rul_recovery_hours': float('inf')},
    {'open_count': 0}, {'close_count': 101}, {'open_count': True},
    {'close_count': 1.5}, {'health_critical': '30'}, {'extra': 1},
])
def test_predictive_rules_validate_at_http_boundary(changes):
    client, service, *_rest, state = client_v3()
    state['principal'] = replace(state['principal'], role='operator')
    # Send raw JSON to exercise non-finite rejection without httpx serializing it.
    import json
    response = client.put('/api/v3/insights/rules?device_id=owned',
        headers={'Authorization': 'Bearer owner', 'Content-Type': 'application/json'},
        content=json.dumps(RULES | changes))
    assert response.status_code == 422
    service.update_predictive_rules.assert_not_called()


def test_predictive_rules_missing_fields_and_service_validation_are_explicit():
    client, service, *_rest, state = client_v3()
    state['principal'] = replace(state['principal'], role='admin')
    endpoint = '/api/v3/insights/rules?device_id=owned'
    headers = {'Authorization': 'Bearer owner'}
    assert client.put(endpoint, headers=headers, json={}).status_code == 422
    service.update_predictive_rules.side_effect = ValueError('invalid rules')
    assert client.put(endpoint, headers=headers, json=RULES).status_code == 422
