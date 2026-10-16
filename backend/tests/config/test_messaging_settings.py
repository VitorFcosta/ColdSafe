import pytest
from pydantic import ValidationError

from backend.tests.api.test_runtime_lifecycle import settings


def test_messaging_is_optional_and_monitor_secret_is_redacted(monkeypatch):
    original = settings()
    assert original.rabbitmq_monitor_password is None
    assert original.rabbitmq_management_port == 15672
    monkeypatch.setenv('RABBITMQ_MONITOR_PASSWORD', 'private-monitor-password')
    monkeypatch.setenv('RABBITMQ_MANAGEMENT_PORT', '15673')
    configured = settings()
    assert configured.rabbitmq_monitor_password.get_secret_value() == 'private-monitor-password'
    assert configured.rabbitmq_management_port == 15673
    assert 'private-monitor-password' not in repr(configured)


@pytest.mark.parametrize('field,value', [('rabbitmq_monitor_password', ''),
    ('rabbitmq_management_port', 0), ('rabbitmq_management_port', 65536)])
def test_invalid_management_configuration_fails_early(field, value):
    original = settings()
    with pytest.raises(ValidationError):
        type(original).model_validate({**original.model_dump(), field: value})
