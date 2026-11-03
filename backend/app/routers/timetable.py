import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.auth import CurrentUserDep, resolve_student_id
from app.db.storage import upload_file
from app.deps import DB, LLM
from app.ingestion.pdf import PDFParseError
from app.ingestion.timetable_parser import ParsedSlot, parse_timetable_pdf
from app.schemas import ManualTimetableIn, SubjectIn
from supabase import Client

router = APIRouter(prefix="/timetable", tags=["timetable"])

MAX_PDF_BYTES = 20 * 1024 * 1024


@router.get("/subjects")
def list_subjects(user: CurrentUserDep, db: DB, student_id: str | None = None) -> list[dict]:
    sid = resolve_student_id(db, user, student_id)
    return db.table("subjects").select("*").eq("student_id", sid).order("name").execute().data


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(body: SubjectIn, user: CurrentUserDep, db: DB) -> dict:
    sid = resolve_student_id(db, user, body.student_id, write=True)
    return (
        db.table("subjects")
        .upsert({"student_id": sid, "name": body.name.strip(), "color": body.color}, on_conflict="student_id,name")
        .execute()
        .data[0]
    )


def _subject_ids(db: Client, student_id: str, names: set[str]) -> dict[str, str]:
    existing = db.table("subjects").select("id,name").eq("student_id", student_id).execute().data
    by_name = {s["name"].lower(): s["id"] for s in existing}
    missing = [n for n in names if n.lower() not in by_name]
    if missing:
        created = db.table("subjects").insert([{"student_id": student_id, "name": n} for n in missing]).execute().data
        by_name.update({s["name"].lower(): s["id"] for s in created})
    return by_name


def _save_timetable(
    db: Client, student_id: str, name: str, source: str, slots: list[dict], storage_path: str | None = None
) -> dict:
    subjects = _subject_ids(db, student_id, {s["subject_name"] for s in slots})
    db.table("timetables").update({"is_active": False}).eq("student_id", student_id).eq("is_active", True).execute()
    timetable = (
        db.table("timetables")
        .insert({"student_id": student_id, "name": name, "source": source, "source_storage_path": storage_path})
        .execute()
        .data[0]
    )
    rows = [
        {
            "timetable_id": timetable["id"],
            "subject_id": s.get("subject_id") or subjects.get(s["subject_name"].lower()),
            "subject_name": s["subject_name"],
            "day_of_week": s["day_of_week"],
            "start_time": str(s["start_time"]),
            "end_time": str(s["end_time"]),
            "location": s.get("location"),
            "teacher_name": s.get("teacher_name"),
        }
        for s in slots
    ]
    saved = db.table("timetable_slots").insert(rows).execute().data
    return {"timetable": timetable, "slots": saved}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_timetable(
    user: CurrentUserDep,
    db: DB,
    llm: LLM,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()] = "My timetable",
    student_id: Annotated[str | None, Form()] = None,
) -> dict:
    sid = resolve_student_id(db, user, student_id, write=True)
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Timetable must be a PDF")
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF too large (max 20MB)")
    try:
        parsed, method = parse_timetable_pdf(data, llm)
    except PDFParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if not parsed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not find a timetable in this PDF. Try manual entry instead."
        )
    path = upload_file(db, f"{sid}/timetables/{uuid.uuid4()}.pdf", data, "application/pdf")
    result = _save_timetable(db, sid, name, "pdf", [s.as_dict() for s in parsed], storage_path=path)
    return {**result, "parse_method": method}


@router.post("/manual", status_code=status.HTTP_201_CREATED)
def manual_timetable(body: ManualTimetableIn, user: CurrentUserDep, db: DB, student_id: str | None = None) -> dict:
    sid = resolve_student_id(db, user, student_id, write=True)
    slots = [
        ParsedSlot(
            s.day_of_week, s.start_time.strftime("%H:%M"), s.end_time.strftime("%H:%M"),
            s.subject_name.strip(), s.location, s.teacher_name,
        ).as_dict() | {"subject_id": s.subject_id}
        for s in body.slots
    ]  # fmt: skip
    return _save_timetable(db, sid, body.name, "manual", slots)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def attach_tasks(slots: list[dict], tasks: list[dict], monday: date) -> list[dict]:
    """Attach each task to its explicit slot, else to the first slot of the same subject that weekday."""
    by_slot: dict[str, list[dict]] = {s["id"]: [] for s in slots}
    for task in tasks:
        weekday = date.fromisoformat(task["due_date"]).weekday()
        target = task.get("slot_id") if task.get("slot_id") in by_slot else None
        if target is None and task.get("subject_id"):
            target = next(
                (s["id"] for s in slots if s["day_of_week"] == weekday and s.get("subject_id") == task["subject_id"]),
                None,
            )
        if target is not None:
            by_slot[target].append(task)
    return [
        {**s, "date": (monday + timedelta(days=s["day_of_week"])).isoformat(), "tasks": by_slot[s["id"]]} for s in slots
    ]


@router.get("")
def get_timetable(
    user: CurrentUserDep,
    db: DB,
    student_id: str | None = None,
    week_of: Annotated[date | None, Query(description="Any date in the week to show")] = None,
) -> dict:
    sid = resolve_student_id(db, user, student_id)
    timetables = db.table("timetables").select("*").eq("student_id", sid).eq("is_active", True).limit(1).execute().data
    monday = week_start(week_of or date.today())
    if not timetables:
        return {"timetable": None, "week_start": monday.isoformat(), "slots": []}
    timetable = timetables[0]
    slots = (
        db.table("timetable_slots")
        .select("*")
        .eq("timetable_id", timetable["id"])
        .order("day_of_week")
        .order("start_time")
        .execute()
        .data
    )
    tasks = (
        db.table("tasks")
        .select("*")
        .eq("student_id", sid)
        .gte("due_date", monday.isoformat())
        .lte("due_date", (monday + timedelta(days=6)).isoformat())
        .execute()
        .data
    )
    return {"timetable": timetable, "week_start": monday.isoformat(), "slots": attach_tasks(slots, tasks, monday)}
