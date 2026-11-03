"""Document ingestion: storage -> text -> chunks -> embeddings -> Pinecone."""

import logging

from supabase import Client

from app.config import get_settings
from app.db.storage import download_file
from app.ingestion.chunking import chunk_pages
from app.ingestion.pdf import extract_pages
from app.ingestion.vectorstore import VectorRecord, VectorStore, get_vector_store
from app.llm import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)

NAMESPACE_BY_KIND = {"textbook": "materials", "material": "materials", "past_paper": "pastpapers"}


def namespace_for_kind(kind: str) -> str:
    settings = get_settings()
    base = NAMESPACE_BY_KIND[kind]
    return settings.pinecone_pastpapers_namespace if base == "pastpapers" else settings.pinecone_materials_namespace


def build_records(document: dict, pdf_bytes: bytes, embedder: EmbeddingProvider) -> tuple[list[VectorRecord], int]:
    settings = get_settings()
    pages = extract_pages(pdf_bytes)
    chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
    vectors = embedder.embed_documents([c.text for c in chunks]) if chunks else []
    records = []
    for chunk, values in zip(chunks, vectors, strict=True):
        metadata = {
            "doc_id": document["id"],
            "page": chunk.page,
            "storage_path": document["storage_path"],
            "chunk_index": chunk.index,
            "title": document["title"],
            "kind": document["kind"],
            "owner_id": document["owner_id"],
            "is_shared": bool(document.get("is_shared")),
            "text": chunk.text,
        }
        if document.get("subject_id"):
            metadata["subject_id"] = document["subject_id"]
        records.append(VectorRecord(id=f"{document['id']}#{chunk.index}", values=values, metadata=metadata))
    return records, len(pages)


def ingest_document(
    doc_id: str,
    db: Client,
    *,
    embedder: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
) -> None:
    rows = db.table("documents").select("*").eq("id", doc_id).limit(1).execute().data
    if not rows:
        logger.warning("ingest_document: %s not found", doc_id)
        return
    document = rows[0]
    db.table("documents").update({"status": "processing", "error": None}).eq("id", doc_id).execute()
    try:
        embedder = embedder or get_embedding_provider()
        store = store or get_vector_store()
        pdf_bytes = download_file(db, document["storage_path"])
        records, page_count = build_records(document, pdf_bytes, embedder)
        store.delete_document(document["namespace"], doc_id)
        store.upsert(document["namespace"], records)
        db.table("documents").update(
            {"status": "ready", "page_count": page_count, "chunk_count": len(records)}
        ).eq("id", doc_id).execute()
        logger.info("Ingested %s: %s chunks into %s", doc_id, len(records), document["namespace"])
    except Exception as exc:
        logger.exception("Ingestion failed for %s", doc_id)
        db.table("documents").update({"status": "failed", "error": str(exc)[:1000]}).eq("id", doc_id).execute()
