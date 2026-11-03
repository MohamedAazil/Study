import cohere

from app.config import Settings
from app.llm.base import Message, ProviderNotConfiguredError, batched

_EMBED_DIMENSIONS = {
    "embed-english-v3.0": 1024,
    "embed-multilingual-v3.0": 1024,
    "embed-english-light-v3.0": 384,
    "embed-multilingual-light-v3.0": 384,
}


class CohereProvider:
    """Generation + embedding fallback."""

    name = "cohere"

    def __init__(self, settings: Settings):
        if not settings.cohere_api_key:
            raise ProviderNotConfiguredError("COHERE_API_KEY not set")
        self._client = cohere.ClientV2(api_key=settings.cohere_api_key, timeout=settings.llm_request_timeout_seconds)
        self._chat_model = settings.cohere_chat_model
        self._embedding_model = settings.cohere_embedding_model
        self.dimension = _EMBED_DIMENSIONS.get(self._embedding_model, 1024)

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
        response = self._client.chat(
            model=self._chat_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            **kwargs,
        )
        return "".join(part.text for part in (response.message.content or []) if getattr(part, "text", None))

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in batched(texts, 96):
            response = self._client.embed(
                texts=batch, model=self._embedding_model, input_type=input_type, embedding_types=["float"]
            )
            vectors.extend(response.embeddings.float_)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "search_document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "search_query")[0]
