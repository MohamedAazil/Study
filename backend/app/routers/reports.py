from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, CurrentUserDep, Role, linked_student_ids, require_roles, resolve_student_id
from app.deps import DB
from app.notifications.base import get_notifier
from app.notifications.eod_job import run_end_of_day
from app.schemas import EODRunRequest

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily")
def daily_reports(
    user: CurrentUserDep,
    db: DB,
    student_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = 30,
) -> list[dict]:
    """Daily reports for one student, or for all linked children when a parent omits student_id."""
    if user.role == Role.parent and not student_id:
        ids = linked_student_ids(db, user.id)
        if not ids:
            return []
        query = db.table("daily_reports").select("*").in_("student_id", ids)
    else:
        query = db.table("daily_reports").select("*").eq("student_id", resolve_student_id(db, user, student_id))
    if start:
        query = query.gte("report_date", start.isoformat())
    if end:
        query = query.lte("report_date", end.isoformat())
    return query.order("report_date", desc=True).limit(min(limit, 365)).execute().data


@router.post("/daily/run")
def run_daily_reports(
    body: EODRunRequest, _: Annotated[CurrentUser, Depends(require_roles(Role.teacher))], db: DB
) -> dict:
    """Manually trigger the end-of-day job (normally run by cron / scheduler)."""
    result = run_end_of_day(db, get_notifier(), body.report_date)
    return result.__dict__
