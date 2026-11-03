import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


class LLMError(RuntimeError):
    pass


class ProviderNotConfiguredError(LLMError):
    pass


@runtime_checkable
class GenerationProvider(Protocol):
    name: str

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_response(text: str) -> Any:
    """Parse JSON from an LLM response, tolerating code fences / leading prose."""
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1), default=-1)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if start == -1 or end <= start:
            raise LLMError(f"Model did not return JSON: {text[:200]!r}") from None
        return json.loads(cleaned[start : end + 1])


def split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    return system, [m for m in messages if m.role != "system"]


def batched(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
