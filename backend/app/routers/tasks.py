from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status

from app.auth import CurrentUser, CurrentUserDep, Role, can_view_student, resolve_student_id
from app.deps import DB
from app.schemas import TaskIn, TaskUpdate
from supabase import Client

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _match_slot(db: Client, student_id: str, subject_id: str, due: date) -> str | None:
    """Link a task to the student's timetable slot for that subject on that weekday, if any."""
    timetables = (
        db.table("timetables").select("id").eq("student_id", student_id).eq("is_active", True).limit(1).execute().data
    )
    if not timetables:
        return None
    slots = (
        db.table("timetable_slots")
        .select("id")
        .eq("timetable_id", timetables[0]["id"])
        .eq("subject_id", subject_id)
        .eq("day_of_week", due.weekday())
        .order("start_time")
        .limit(1)
        .execute()
        .data
    )
    return slots[0]["id"] if slots else None


def _get_task(db: Client, user: CurrentUser, task_id: str, *, write: bool) -> dict:
    rows = db.table("tasks").select("*").eq("id", task_id).limit(1).execute().data
    if not rows or not can_view_student(db, user, rows[0]["student_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    if write and user.role == Role.parent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Parents have read-only access")
    return rows[0]


@router.get("")
def list_tasks(
    user: CurrentUserDep,
    db: DB,
    date: date | None = None,  # noqa: A002 - matches the public ?date= query param
    student_id: str | None = None,
    subject_id: str | None = None,
    completed: bool | None = None,
) -> list[dict]:
    sid = resolve_student_id(db, user, student_id)
    query = db.table("tasks").select("*").eq("student_id", sid)
    if date:
        query = query.eq("due_date", date.isoformat())
    if subject_id:
        query = query.eq("subject_id", subject_id)
    if completed is not None:
        query = query.eq("completed", completed)
    return query.order("due_date").order("created_at").execute().data


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(body: TaskIn, user: CurrentUserDep, db: DB) -> dict:
    sid = resolve_student_id(db, user, body.student_id, write=True)
    slot_id = body.slot_id or (_match_slot(db, sid, body.subject_id, body.due_date) if body.subject_id else None)
    row = {
        "student_id": sid,
        "created_by": user.id,
        "title": body.title.strip(),
        "description": body.description,
        "due_date": body.due_date.isoformat(),
        "subject_id": body.subject_id,
        "slot_id": slot_id,
    }
    return db.table("tasks").insert(row).execute().data[0]


@router.get("/{task_id}")
def get_task(task_id: str, user: CurrentUserDep, db: DB) -> dict:
    return _get_task(db, user, task_id, write=False)


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskUpdate, user: CurrentUserDep, db: DB) -> dict:
    task = _get_task(db, user, task_id, write=True)
    changes = body.model_dump(exclude_unset=True, mode="json")
    if "completed" in changes:
        changes["completed_at"] = datetime.now(timezone.utc).isoformat() if changes["completed"] else None
    if ("subject_id" in changes or "due_date" in changes) and "slot_id" not in changes:
        subject_id = changes.get("subject_id", task.get("subject_id"))
        due = date.fromisoformat(changes.get("due_date", task["due_date"]))
        changes["slot_id"] = _match_slot(db, task["student_id"], subject_id, due) if subject_id else None
    if not changes:
        return task
    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    return db.table("tasks").update(changes).eq("id", task_id).execute().data[0]


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, user: CurrentUserDep, db: DB) -> Response:
    _get_task(db, user, task_id, write=True)
    db.table("tasks").delete().eq("id", task_id).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
