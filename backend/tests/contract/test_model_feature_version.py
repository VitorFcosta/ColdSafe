"""Generated feature identifiers must cross activation/status/prediction unchanged."""
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from backend.app.domain.features import FeatureSpec
from backend.app.services.feature_inputs import features_version
from simulator.model import SCHEMA


@pytest.mark.parametrize('name', ['model_activation_requested', 'model_active', 'prediction_available_zero_rul'])
def test_generated_features_version_is_a_valid_bus_identifier(name):
    examples = json.loads(Path('contracts/examples/aiot.valid.json').read_text())
    example = next(item for item in examples if item['name'] == name)
    payload = copy.deepcopy(example['payload'])
    payload['data']['features_version'] = features_version(FeatureSpec())
    Draft202012Validator({**SCHEMA, '$ref': '#/$defs/bus_event'},
                         format_checker=FormatChecker()).validate(payload)
