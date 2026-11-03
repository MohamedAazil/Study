"""Supabase Auth JWT verification and role-based access helpers."""

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from app.config import Settings, get_settings
from app.db.supabase import get_db


class Role(str, Enum):
    student = "student"
    teacher = "teacher"
    parent = "parent"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    role: Role
    full_name: str | None = None
    token: str = ""


_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def decode_supabase_jwt(token: str, settings: Settings) -> dict:
    """Verify a Supabase access token.

    Supports legacy HS256 projects (``SUPABASE_JWT_SECRET``) and asymmetric
    signing keys (RS256/ES256) published on the project's JWKS endpoint.
    """
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "SUPABASE_JWT_SECRET not configured")
            key: object = settings.supabase_jwt_secret
        else:
            key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=[alg], audience=settings.supabase_jwt_audience)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Client, Depends(get_db)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    claims = decode_supabase_jwt(credentials.credentials, settings)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has no subject")

    rows = db.table("users").select("id,email,role,full_name").eq("id", user_id).limit(1).execute().data
    if not rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User profile not found")
    profile = rows[0]
    return CurrentUser(
        id=profile["id"],
        email=profile.get("email") or claims.get("email"),
        role=Role(profile["role"]),
        full_name=profile.get("full_name"),
        token=credentials.credentials,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_roles(*roles: Role):
    """Dependency factory: ``Depends(require_roles(Role.parent))``."""

    def _dependency(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(r.value for r in roles)}")
        return user

    return _dependency


def linked_student_ids(db: Client, parent_id: str) -> list[str]:
    rows = db.table("parent_student_links").select("student_id").eq("parent_id", parent_id).execute().data
    return [row["student_id"] for row in rows]


def can_view_student(db: Client, user: CurrentUser, student_id: str) -> bool:
    if user.role == Role.student:
        return user.id == student_id
    if user.role == Role.parent:
        return student_id in linked_student_ids(db, user.id)
    return user.role == Role.teacher


def resolve_student_id(db: Client, user: CurrentUser, student_id: str | None, *, write: bool = False) -> str:
    """Return the student a request targets, enforcing access.

    Students always act on themselves. Teachers and parents must name a
    student; parents are read-only and limited to linked children.
    """
    if user.role == Role.student:
        if student_id and student_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Students can only access their own data")
        return user.id
    if not student_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "student_id is required")
    if write and user.role == Role.parent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Parents have read-only access")
    if not can_view_student(db, user, student_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to access this student")
    return student_id
