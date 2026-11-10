import pytest

@pytest.fixture(autouse=True)
def default_isolate_db(monkeypatch):
    """Keep test suite hermetic by default so unit tests do not accidentally hit production DB."""
    monkeypatch.setenv("DATABASE_URL", "")
