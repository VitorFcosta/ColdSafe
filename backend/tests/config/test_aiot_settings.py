import pytest
from pydantic import ValidationError

from backend.tests.api.test_runtime_lifecycle import settings


def test_v3_is_opt_in_and_requires_private_config_when_enabled():
    original = settings()
    assert original.aiot_enabled is False
    with pytest.raises(ValidationError):
        type(original).model_validate({**original.model_dump(), 'aiot_enabled': True})
    configured = type(original).model_validate({
        **original.model_dump(), 'aiot_enabled': True,
        'aiot_catalog_path': '/catalog/catalog.json',
        'aiot_owner_user_id': '12345678-1234-1234-1234-123456789abc',
        'rabbitmq_commands_password': 'commands-private',
        'rabbitmq_delivery_password': 'delivery-private',
    })
    assert configured.aiot_catalog_path.name == 'catalog.json'
    assert 'commands-private' not in repr(configured)
