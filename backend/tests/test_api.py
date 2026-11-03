import time
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import CurrentUser, Role, decode_supabase_jwt, get_current_user
from app.config import get_settings
from app.db.supabase import get_db
from app.deps import llm_dep
from app.main import app


def _token(secret, **claims):
    payload = {"sub": "u1", "aud": "authenticated", "exp": int(time.time()) + 60, **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_decode_valid_hs256_token():
    settings = get_settings()
    assert decode_supabase_jwt(_token(settings.supabase_jwt_secret), settings)["sub"] == "u1"


@pytest.mark.parametrize(
    "token",
    [
        _token("wrong-secret-wrong-secret-wrong-secret"),
        _token("test-secret-test-secret-test-secret-123", aud="anon"),
        _token("test-secret-test-secret-test-secret-123", exp=1),
    ],
)
def test_decode_rejects_bad_tokens(token):
    with pytest.raises(HTTPException) as exc:
        decode_supabase_jwt(token, get_settings())
    assert exc.value.status_code == 401


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def _as(role: Role):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="stu-1", email="s@x", role=role, full_name="S", token="t"
    )


def test_requires_auth(client):
    app.dependency_overrides[get_db] = lambda: MagicMock()
    assert client.get("/tasks").status_code == 401


def test_health(client):
    assert client.get("/health").status_code == 200


def test_image_submission_rejected(client, monkeypatch):
    _as(Role.student)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[llm_dep] = lambda: MagicMock()
    exam = {"id": "e1", "student_id": "stu-1", "status": "generated"}
    monkeypatch.setattr("app.routers.exams._get_exam", lambda db, user, exam_id: exam)
    res = client.post("/exams/e1/submit", data={"submission_type": "image"})
    assert res.status_code == 422
    assert "image" in res.json()["detail"].lower()


def test_parent_cannot_generate_exam(client):
    _as(Role.parent)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    res = client.post("/exams/generate", json={"topic": "Forces", "total_marks": 10, "difficulty": "easy"})
    assert res.status_code == 403
