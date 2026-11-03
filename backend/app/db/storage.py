from app.config import get_settings
from supabase import Client


def upload_file(db: Client, path: str, data: bytes, content_type: str) -> str:
    bucket = get_settings().supabase_storage_bucket
    db.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": "true"})
    return path


def download_file(db: Client, path: str) -> bytes:
    return db.storage.from_(get_settings().supabase_storage_bucket).download(path)


def remove_file(db: Client, path: str) -> None:
    db.storage.from_(get_settings().supabase_storage_bucket).remove([path])


def create_signed_url(db: Client, path: str, expires_in: int | None = None) -> str:
    settings = get_settings()
    expiry = expires_in or settings.signed_url_expiry_seconds
    result = db.storage.from_(settings.supabase_storage_bucket).create_signed_url(path, expiry)
    return result.get("signedURL") or result.get("signedUrl") or result["signed_url"]
