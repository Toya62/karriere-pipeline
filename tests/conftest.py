import pytest

@pytest.fixture(autouse=True)
def default_isolate_db(monkeypatch):
    """Keep test suite hermetic by default so unit tests do not hit production DB or live Telegram."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    # Admin seed identity is env-only in src/db/database.py. Tests that build an
    # isolated temp DB rely on setup_db seeding a default admin user (applications
    # and evaluations have a user_id FK), so provide the identity here.
    monkeypatch.setenv("ADMIN_EMAIL", "pandeytoya22@gmail.com")
    monkeypatch.setenv("ADMIN_NAME", "Toyanath Pandey")
