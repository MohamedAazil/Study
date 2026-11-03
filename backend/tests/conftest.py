import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "PINECONE_API_KEY", "RESEND_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-test-secret-test-secret-123")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
