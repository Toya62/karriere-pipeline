import pytest

@pytest.fixture(autouse=True)
def default_isolate_db(monkeypatch):
    """Keep test suite hermetic by default so unit tests do not hit production DB or live Telegram."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
