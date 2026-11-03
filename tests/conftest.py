import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.model import build_bundle


@pytest.fixture(scope="session")
def bundle():
    return build_bundle()


@pytest.fixture(scope="session")
def client(bundle):
    with TestClient(create_app(bundle)) as test_client:
        yield test_client
