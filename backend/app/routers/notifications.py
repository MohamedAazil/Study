from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import CurrentUser, CurrentUserDep, Role, require_roles
from app.deps import DB
from app.schemas import NotificationPreferencesIn

router = APIRouter(prefix="/notifications", tags=["notifications"])

ParentUser = Annotated[CurrentUser, Depends(require_roles(Role.parent))]


@router.get("")
def list_notifications(user: CurrentUserDep, db: DB, unread_only: bool = False, limit: int = 50) -> list[dict]:
    query = db.table("notifications").select("*").eq("recipient_id", user.id)
    if unread_only:
        query = query.is_("read_at", "null")
    return query.order("created_at", desc=True).limit(min(limit, 200)).execute().data


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, user: CurrentUserDep, db: DB) -> dict:
    rows = (
        db.table("notifications")
        .update({"read_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", notification_id)
        .eq("recipient_id", user.id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return rows[0]


@router.get("/preferences")
def get_preferences(user: ParentUser, db: DB) -> dict:
    rows = db.table("notification_preferences").select("*").eq("parent_id", user.id).limit(1).execute().data
    return rows[0] if rows else {"parent_id": user.id, "in_app_enabled": True, "email_enabled": True}


@router.put("/preferences")
def update_preferences(body: NotificationPreferencesIn, user: ParentUser, db: DB) -> dict:
    row = {
        "parent_id": user.id,
        **body.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return db.table("notification_preferences").upsert(row, on_conflict="parent_id").execute().data[0]
