from openai import OpenAI

from app.config import Settings
from app.llm.base import Message, ProviderNotConfiguredError, batched

_NATIVE_DIMENSIONS = {"text-embedding-3-large": 3072, "text-embedding-3-small": 1536, "text-embedding-ada-002": 1536}


class OpenAIProvider:
    """Primary provider: GPT-4o for generation, text-embedding-3-large for embeddings."""

    name = "openai"

    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ProviderNotConfiguredError("OPENAI_API_KEY not set")
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_request_timeout_seconds, max_retries=0)
        self._chat_model = settings.openai_chat_model
        self._embedding_model = settings.openai_embedding_model
        # text-embedding-3-* support Matryoshka truncation via `dimensions`.
        self.dimension = settings.embedding_dimension
        self._send_dimensions = _NATIVE_DIMENSIONS.get(self._embedding_model) != self.dimension

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        kwargs: dict = {}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(
            model=self._chat_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in batched(texts, 96):
            kwargs = {"dimensions": self.dimension} if self._send_dimensions else {}
            response = self._client.embeddings.create(model=self._embedding_model, input=batch, **kwargs)
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]
