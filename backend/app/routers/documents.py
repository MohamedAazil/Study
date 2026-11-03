import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Response, UploadFile, status

from app.auth import CurrentUser, CurrentUserDep, Role, linked_student_ids
from app.config import get_settings
from app.db.storage import create_signed_url, remove_file, upload_file
from app.deps import DB
from app.ingestion.pipeline import ingest_document, namespace_for_kind
from app.ingestion.vectorstore import get_vector_store
from app.schemas import DocumentKind, SignedUrl
from supabase import Client

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


def _can_read(db: Client, user: CurrentUser, doc: dict) -> bool:
    if doc["owner_id"] == user.id or doc.get("is_shared"):
        return True
    return user.role == Role.parent and doc["owner_id"] in linked_student_ids(db, user.id)


def _get_document(db: Client, user: CurrentUser, doc_id: str) -> dict:
    rows = db.table("documents").select("*").eq("id", doc_id).limit(1).execute().data
    if not rows or not _can_read(db, user, rows[0]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return rows[0]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    background: BackgroundTasks,
    user: CurrentUserDep,
    db: DB,
    file: Annotated[UploadFile, File()],
    kind: Annotated[DocumentKind, Form()],
    title: Annotated[str | None, Form()] = None,
    subject_id: Annotated[str | None, Form()] = None,
    is_shared: Annotated[bool | None, Form()] = None,
) -> dict:
    if user.role == Role.parent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Parents cannot upload documents")
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF documents are supported")
    data = await file.read()
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Document too large (max 50MB)")

    doc_id = str(uuid.uuid4())
    filename = (file.filename or "document.pdf").replace("/", "_")
    storage_path = upload_file(db, f"{user.id}/{doc_id}/{filename}", data, "application/pdf")
    # Teacher uploads are shared with all students by default.
    shared = bool(is_shared) if is_shared is not None else user.role == Role.teacher
    row = {
        "id": doc_id,
        "owner_id": user.id,
        "subject_id": subject_id,
        "title": (title or filename.rsplit(".", 1)[0]).strip(),
        "filename": filename,
        "kind": kind,
        "namespace": namespace_for_kind(kind),
        "storage_path": storage_path,
        "mime_type": "application/pdf",
        "size_bytes": len(data),
        "is_shared": shared and user.role == Role.teacher,
        "status": "pending",
    }
    document = db.table("documents").insert(row).execute().data[0]
    background.add_task(ingest_document, doc_id, db)
    return document


@router.get("")
def list_documents(
    user: CurrentUserDep, db: DB, kind: DocumentKind | None = None, subject_id: str | None = None
) -> list[dict]:
    owners = [user.id]
    if user.role == Role.parent:
        owners += linked_student_ids(db, user.id)
    owner_list = ",".join(owners)
    query = db.table("documents").select("*").or_(f"owner_id.in.({owner_list}),is_shared.eq.true")
    if kind:
        query = query.eq("kind", kind)
    if subject_id:
        query = query.eq("subject_id", subject_id)
    return query.order("created_at", desc=True).execute().data


@router.get("/{doc_id}")
def get_document(doc_id: str, user: CurrentUserDep, db: DB) -> dict:
    return _get_document(db, user, doc_id)


@router.get("/{doc_id}/download", response_model=SignedUrl)
def download_document(doc_id: str, user: CurrentUserDep, db: DB) -> SignedUrl:
    doc = _get_document(db, user, doc_id)
    expires = get_settings().signed_url_expiry_seconds
    return SignedUrl(url=create_signed_url(db, doc["storage_path"], expires), expires_in=expires)


@router.post("/{doc_id}/reingest", status_code=status.HTTP_202_ACCEPTED)
def reingest_document(doc_id: str, background: BackgroundTasks, user: CurrentUserDep, db: DB) -> dict:
    doc = _get_document(db, user, doc_id)
    if doc["owner_id"] != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can re-ingest")
    background.add_task(ingest_document, doc_id, db)
    return {"id": doc_id, "status": "pending"}


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: str, user: CurrentUserDep, db: DB) -> Response:
    doc = _get_document(db, user, doc_id)
    if doc["owner_id"] != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can delete")
    try:
        get_vector_store().delete_document(doc["namespace"], doc_id)
    except RuntimeError:
        pass  # Pinecone not configured; nothing to clean up
    remove_file(db, doc["storage_path"])
    db.table("documents").delete().eq("id", doc_id).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
