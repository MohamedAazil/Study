from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import CurrentUser, CurrentUserDep, Role, linked_student_ids, require_roles
from app.deps import DB
from app.schemas import LinkParentRequest, ProfileUpdate, UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserProfile)
def me(user: CurrentUserDep) -> UserProfile:
    return UserProfile(id=user.id, email=user.email, full_name=user.full_name, role=user.role.value)


@router.patch("/me", response_model=UserProfile)
def update_me(body: ProfileUpdate, user: CurrentUserDep, db: DB) -> UserProfile:
    db.table("users").update({"full_name": body.full_name}).eq("id", user.id).execute()
    return UserProfile(id=user.id, email=user.email, full_name=body.full_name, role=user.role.value)


@router.get("/students", response_model=list[UserProfile])
def list_students(
    user: Annotated[CurrentUser, Depends(require_roles(Role.parent, Role.teacher))], db: DB
) -> list[dict]:
    """Parents: linked children. Teachers: all students."""
    query = db.table("users").select("id,email,full_name,role").eq("role", "student")
    if user.role == Role.parent:
        ids = linked_student_ids(db, user.id)
        if not ids:
            return []
        query = query.in_("id", ids)
    return query.order("full_name").execute().data


@router.post("/links", status_code=status.HTTP_201_CREATED)
def link_parent(
    body: LinkParentRequest,
    user: Annotated[CurrentUser, Depends(require_roles(Role.student, Role.teacher))],
    db: DB,
) -> dict:
    """Students link a parent account by email; teachers may link on behalf of any student."""
    student_id = user.id if user.role == Role.student else body.student_id
    if not student_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "student_id is required")
    parents = db.table("users").select("id,role").eq("email", body.parent_email.lower()).limit(1).execute().data
    if not parents or parents[0]["role"] != Role.parent.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No parent account with that email")
    parent_id = parents[0]["id"]
    row = (
        db.table("parent_student_links")
        .upsert({"parent_id": parent_id, "student_id": student_id}, on_conflict="parent_id,student_id")
        .execute()
        .data[0]
    )
    db.table("notification_preferences").upsert({"parent_id": parent_id}, on_conflict="parent_id").execute()
    return row
