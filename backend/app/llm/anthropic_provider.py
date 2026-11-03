import anthropic

from app.config import Settings
from app.llm.base import Message, ProviderNotConfiguredError, split_system


class AnthropicProvider:
    """Generation fallback (Anthropic has no embeddings API)."""

    name = "anthropic"

    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise ProviderNotConfiguredError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.llm_request_timeout_seconds, max_retries=0
        )
        self._model = settings.anthropic_chat_model

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        system, rest = split_system(messages)
        if json_mode:
            system = f"{system}\n\nRespond with a single valid JSON object and nothing else.".strip()
        response = self._client.messages.create(
            model=self._model,
            system=system or anthropic.NOT_GIVEN,
            messages=[{"role": m.role, "content": m.content} for m in rest],
            temperature=temperature,
            max_tokens=max_tokens or 4096,
        )
        return "".join(block.text for block in response.content if block.type == "text")
