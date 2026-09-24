from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.catalog import ThresholdInput, create_catalog_router


class FakeCatalog:
    def create_environment(self, user_id, name):
        return {"id": str(uuid4()), "name": name, "owner_user_id": str(user_id)}


def test_catalog_route_accepts_trimmed_name_and_uses_authenticated_user() -> None:
    user_id = uuid4()
    app = FastAPI()
    app.include_router(create_catalog_router(FakeCatalog(), lambda: user_id))

    response = TestClient(app).post("/api/v1/environments", json={"name": "  Câmara A  "})

    assert response.status_code == 201
    assert response.json()["data"]["name"] == "Câmara A"
    assert response.json()["data"]["owner_user_id"] == str(user_id)


@pytest.mark.parametrize(
    "values",
    [
        {"min_c": 8, "max_c": 2, "attention_margin_c": 0.5},
        {"min_c": 2, "max_c": 8, "attention_margin_c": 3},
        {"min_c": 2, "max_c": 8, "attention_margin_c": -0.1},
        {"min_c": 2, "max_c": 8, "attention_margin_c": 0.555},
    ],
)
def test_invalid_thresholds_are_rejected(values: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        ThresholdInput.model_validate(values)
