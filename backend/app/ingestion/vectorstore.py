"""Thin Pinecone wrapper. Vector ids are ``<doc_id>#<chunk_index>``."""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class VectorRecord:
    id: str
    values: list[float]
    metadata: dict[str, Any]


@dataclass
class VectorMatch:
    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    def __init__(self, index: Any):
        self._index = index

    def upsert(self, namespace: str, records: list[VectorRecord], batch_size: int = 100) -> None:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            self._index.upsert(
                vectors=[{"id": r.id, "values": r.values, "metadata": r.metadata} for r in batch],
                namespace=namespace,
            )

    def query(
        self, namespace: str, vector: list[float], top_k: int, metadata_filter: dict | None = None
    ) -> list[VectorMatch]:
        result = self._index.query(
            vector=vector, top_k=top_k, namespace=namespace, include_metadata=True, filter=metadata_filter or None
        )
        matches = result["matches"] if isinstance(result, dict) else result.matches
        return [
            VectorMatch(id=m["id"], score=float(m["score"]), metadata=dict(m.get("metadata") or {}))
            if isinstance(m, dict)
            else VectorMatch(id=m.id, score=float(m.score), metadata=dict(m.metadata or {}))
            for m in matches
        ]

    def delete_document(self, namespace: str, doc_id: str) -> None:
        for ids in self._index.list(prefix=f"{doc_id}#", namespace=namespace):
            if ids:
                self._index.delete(ids=list(ids), namespace=namespace)


@lru_cache
def get_vector_store() -> VectorStore:
    from pinecone import Pinecone, ServerlessSpec

    settings = get_settings()
    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY not set")
    pc = Pinecone(api_key=settings.pinecone_api_key)
    existing = {idx["name"] for idx in pc.list_indexes()}
    if settings.pinecone_index_name not in existing:
        logger.info("Creating Pinecone index %s (dim=%s)", settings.pinecone_index_name, settings.embedding_dimension)
        pc.create_index(
            name=settings.pinecone_index_name,
            dimension=settings.embedding_dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=settings.pinecone_cloud, region=settings.pinecone_region),
        )
    return VectorStore(pc.Index(settings.pinecone_index_name))
