import pytest

from app.config import Settings
from app.llm import factory
from app.llm.base import LLMError, Message, ProviderNotConfiguredError, parse_json_response


class FakeGen:
    def __init__(self, name, fail_times=0):
        self.name = name
        self.fail_times = fail_times
        self.calls = 0

    def generate(self, messages, *, temperature=0.2, max_tokens=None, json_mode=False):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"{self.name} down")
        return f"{self.name}:{messages[-1].content}"


class FakeEmb:
    def __init__(self, name, dimension):
        self.name = name
        self.dimension = dimension


MSG = [Message("user", "hi")]


def test_retries_then_succeeds_on_primary():
    primary = FakeGen("openai", fail_times=1)
    fallback = FakeGen("anthropic")
    provider = factory.FailoverGenerationProvider([primary, fallback], max_attempts=2, max_wait=0)
    assert provider.generate(MSG) == "openai:hi"
    assert primary.calls == 2 and fallback.calls == 0


def test_fails_over_in_order():
    primary = FakeGen("openai", fail_times=99)
    fallback = FakeGen("anthropic")
    provider = factory.FailoverGenerationProvider([primary, fallback], max_attempts=2, max_wait=0)
    assert provider.generate(MSG) == "anthropic:hi"
    assert primary.calls == 2


def test_all_providers_failing_raises():
    provider = factory.FailoverGenerationProvider(
        [FakeGen("openai", 99), FakeGen("cohere", 99)], max_attempts=1, max_wait=0
    )
    with pytest.raises(LLMError, match="openai.*cohere"):
        provider.generate(MSG)


def test_no_configured_providers_raises():
    with pytest.raises(ProviderNotConfiguredError):
        factory.build_generation_provider(Settings(generation_providers="openai,anthropic"))


def test_order_comes_from_config(monkeypatch):
    monkeypatch.setitem(factory.GENERATION_BUILDERS, "openai", lambda s: FakeGen("openai"))
    monkeypatch.setitem(factory.GENERATION_BUILDERS, "cohere", lambda s: FakeGen("cohere"))
    provider = factory.build_generation_provider(Settings(generation_providers="cohere,openai"))
    assert [p.name for p in provider.providers] == ["cohere", "openai"]


def test_embedding_fallback_with_wrong_dimension_is_skipped(monkeypatch):
    monkeypatch.setitem(factory.EMBEDDING_BUILDERS, "openai", lambda s: FakeEmb("openai", 3072))
    monkeypatch.setitem(factory.EMBEDDING_BUILDERS, "cohere", lambda s: FakeEmb("cohere", 1024))
    provider = factory.build_embedding_provider(Settings(embedding_providers="openai,cohere", embedding_dimension=3072))
    assert [p.name for p in provider.providers] == ["openai"]


def test_parse_json_response_handles_code_fences():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
