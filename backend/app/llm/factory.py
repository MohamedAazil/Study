"""Provider factory with retry + ordered failover.

``GENERATION_PROVIDERS`` / ``EMBEDDING_PROVIDERS`` list providers in priority
order. Each call is retried with exponential backoff (tenacity) on the current
provider, then fails over to the next configured provider.

Embedding fallbacks are only used when their vector dimension matches
``EMBEDDING_DIMENSION`` (the Pinecone index dimension); mixing dimensions
would corrupt the index. Set ``EMBEDDING_DIMENSION=1024`` to make OpenAI
(truncated text-embedding-3-large) and Cohere v3 interchangeable.
"""

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import TypeVar

from tenacity import Retrying, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings
from app.llm.base import EmbeddingProvider, GenerationProvider, LLMError, Message, ProviderNotConfiguredError

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _openai(settings: Settings):
    from app.llm.openai_provider import OpenAIProvider

    return OpenAIProvider(settings)


def _anthropic(settings: Settings):
    from app.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(settings)


def _cohere(settings: Settings):
    from app.llm.cohere_provider import CohereProvider

    return CohereProvider(settings)


GENERATION_BUILDERS: dict[str, Callable[[Settings], GenerationProvider]] = {
    "openai": _openai,
    "anthropic": _anthropic,
    "cohere": _cohere,
}
EMBEDDING_BUILDERS: dict[str, Callable[[Settings], EmbeddingProvider]] = {
    "openai": _openai,
    "cohere": _cohere,
}


class _Failover:
    def __init__(self, providers: list, max_attempts: int, max_wait: float):
        if not providers:
            raise ProviderNotConfiguredError("No LLM providers configured; set at least OPENAI_API_KEY")
        self.providers = providers
        self._max_attempts = max_attempts
        self._max_wait = max_wait

    def _call(self, operation: str, fn: Callable[[object], T]) -> T:
        errors: list[str] = []
        for provider in self.providers:
            retrying = Retrying(
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential(multiplier=0.5, max=self._max_wait),
                reraise=True,
            )
            try:
                return retrying(fn, provider)
            except Exception as exc:  # noqa: BLE001 - any provider failure triggers failover
                logger.warning("%s failed on provider %s: %s", operation, provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
        raise LLMError(f"All providers failed for {operation}: {'; '.join(errors)}")


class FailoverGenerationProvider(_Failover):
    name = "failover"

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        return self._call(
            "generate",
            lambda p: p.generate(messages, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode),
        )


class FailoverEmbeddingProvider(_Failover):
    name = "failover"

    def __init__(self, providers: list, max_attempts: int, max_wait: float):
        super().__init__(providers, max_attempts, max_wait)
        self.dimension = providers[0].dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._call("embed_documents", lambda p: p.embed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._call("embed_query", lambda p: p.embed_query(text))


def _build(names: list[str], builders: dict[str, Callable], settings: Settings) -> list:
    providers = []
    for name in names:
        builder = builders.get(name.lower())
        if builder is None:
            logger.warning("Unknown provider %r ignored", name)
            continue
        try:
            providers.append(builder(settings))
        except ProviderNotConfiguredError as exc:
            logger.info("Skipping provider %s: %s", name, exc)
    return providers


def build_generation_provider(settings: Settings) -> FailoverGenerationProvider:
    providers = _build(settings.generation_providers, GENERATION_BUILDERS, settings)
    return FailoverGenerationProvider(providers, settings.llm_max_attempts, settings.llm_retry_max_wait_seconds)


def build_embedding_provider(settings: Settings) -> FailoverEmbeddingProvider:
    providers = []
    for provider in _build(settings.embedding_providers, EMBEDDING_BUILDERS, settings):
        if provider.dimension != settings.embedding_dimension:
            logger.warning(
                "Skipping embedding provider %s: dimension %s != EMBEDDING_DIMENSION %s",
                provider.name,
                provider.dimension,
                settings.embedding_dimension,
            )
            continue
        providers.append(provider)
    return FailoverEmbeddingProvider(providers, settings.llm_max_attempts, settings.llm_retry_max_wait_seconds)


@lru_cache
def get_generation_provider() -> GenerationProvider:
    return build_generation_provider(get_settings())


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return build_embedding_provider(get_settings())
