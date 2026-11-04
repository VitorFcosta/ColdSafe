import re
from unittest.mock import Mock
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest

from backend.app.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(repository=Mock(), readiness_check=lambda: True))


def test_public_api_docs_use_only_local_assets_and_openapi(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assets = re.findall(r'''(?:src|href)=["']([^"']+)["']''', response.text)
    assert assets
    assert all(not urlsplit(url).scheme and not urlsplit(url).netloc for url in assets)
    assert set(assets) == {
        "/docs-assets/swagger-ui-bundle.js",
        "/docs-assets/swagger-ui.css",
        "/docs-assets/favicon-32x32.png",
    }
    assert re.search(r'"validatorUrl"\s*:\s*null\b', response.text)
    schema_url = re.search(r'''\burl:\s*["']([^"']+)["']''', response.text)
    assert schema_url is not None
    assert schema_url.group(1) == "/openapi.json"
    specification = client.get(schema_url.group(1))
    assert specification.status_code == 200
    assert "/health/live" in specification.json()["paths"]


def test_redoc_redirects_to_the_same_offline_documentation(client: TestClient) -> None:
    response = client.get("/redoc", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
