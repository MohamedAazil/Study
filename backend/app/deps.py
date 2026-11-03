"""Shared FastAPI dependencies for AI services (override in tests via app.dependency_overrides)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.db.supabase import get_db
from app.ingestion.vectorstore import VectorStore, get_vector_store
from app.llm import EmbeddingProvider, GenerationProvider, get_embedding_provider, get_generation_provider
from app.llm.base import ProviderNotConfiguredError
from supabase import Client


def llm_dep() -> GenerationProvider:
    try:
        return get_generation_provider()
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def embedder_dep() -> EmbeddingProvider:
    try:
        return get_embedding_provider()
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def vector_store_dep() -> VectorStore:
    try:
        return get_vector_store()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


DB = Annotated[Client, Depends(get_db)]
LLM = Annotated[GenerationProvider, Depends(llm_dep)]
Embedder = Annotated[EmbeddingProvider, Depends(embedder_dep)]
Store = Annotated[VectorStore, Depends(vector_store_dep)]
