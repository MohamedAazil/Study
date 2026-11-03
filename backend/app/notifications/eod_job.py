"""End-of-day job: aggregate task completion -> daily_reports -> parent notifications."""

import html
import logging
from dataclasses import dataclass, field
from datetime import date

from app.config import get_settings
from app.notifications.base import EmailMessage, Notifier
from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class EODResult:
    report_date: str
    reports: int = 0
    in_app: int = 0
    emails: int = 0
    errors: list[str] = field(default_factory=list)


def build_report(student_id: str, report_date: date, tasks: list[dict], subjects: dict[str, str]) -> dict:
    total = len(tasks)
    completed = sum(1 for t in tasks if t["completed"])
    rate = round(100 * completed / total, 2) if total else 0.0
    details = [
        {
            "task_id": t["id"],
            "title": t["title"],
            "subject": subjects.get(t.get("subject_id") or "", None),
            "completed": t["completed"],
        }
        for t in tasks
    ]
    if total == 0:
        summary = "No tasks were scheduled today."
    else:
        pending = [d["title"] for d in details if not d["completed"]]
        summary = f"Completed {completed} of {total} tasks ({rate:g}%)."
        if pending:
            summary += f" Pending: {', '.join(pending[:5])}{'…' if len(pending) > 5 else ''}."
    return {
        "student_id": student_id,
        "report_date": report_date.isoformat(),
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_rate": rate,
        "summary": summary,
        "details": details,
    }


def render_email(student_name: str, report: dict) -> tuple[str, str]:
    subject = f"{student_name}'s study report for {report['report_date']}"
    rows = "".join(
        f"<li>{'✅' if d['completed'] else '⬜'} {html.escape(d['title'])}"
        f"{' — ' + html.escape(d['subject']) if d.get('subject') else ''}</li>"
        for d in report["details"]
    )
    link = f"{get_settings().frontend_url}/parent"
    body = (
        f"<h2>{html.escape(subject)}</h2><p>{html.escape(report['summary'])}</p>"
        f"<ul>{rows}</ul><p><a href='{link}'>Open the parent dashboard</a></p>"
    )
    return subject, body


def run_end_of_day(db: Client, notifier: Notifier, report_date: date | None = None) -> EODResult:
    report_date = report_date or date.today()
    result = EODResult(report_date=report_date.isoformat())
    students = db.table("users").select("id,email,full_name").eq("role", "student").execute().data
    links = db.table("parent_student_links").select("parent_id,student_id").execute().data
    parents = {p["id"]: p for p in db.table("users").select("id,email,full_name").eq("role", "parent").execute().data}
    prefs = {p["parent_id"]: p for p in db.table("notification_preferences").select("*").execute().data}

    for student in students:
        try:
            tasks = (
                db.table("tasks")
                .select("id,title,subject_id,completed")
                .eq("student_id", student["id"])
                .eq("due_date", report_date.isoformat())
                .execute()
                .data
            )
            subject_rows = db.table("subjects").select("id,name").eq("student_id", student["id"]).execute().data
            report = build_report(student["id"], report_date, tasks, {s["id"]: s["name"] for s in subject_rows})
            saved = db.table("daily_reports").upsert(report, on_conflict="student_id,report_date").execute().data
            result.reports += 1
            report_id = saved[0]["id"] if saved else None
            name = student.get("full_name") or student.get("email") or "Your child"

            for link in (lk for lk in links if lk["student_id"] == student["id"]):
                parent = parents.get(link["parent_id"])
                if not parent:
                    continue
                pref = prefs.get(parent["id"], {"in_app_enabled": True, "email_enabled": True})
                if pref.get("in_app_enabled", True):
                    db.table("notifications").insert(
                        {
                            "recipient_id": parent["id"],
                            "student_id": student["id"],
                            "kind": "daily_report",
                            "title": f"{name}: daily report {report['report_date']}",
                            "body": report["summary"],
                            "data": {"report_id": report_id, "completion_rate": report["completion_rate"]},
                        }
                    ).execute()
                    result.in_app += 1
                if pref.get("email_enabled", True) and parent.get("email"):
                    subject, body = render_email(name, report)
                    notifier.send_email(
                        EmailMessage(to=parent["email"], subject=subject, html=body, text=report["summary"])
                    )
                    result.emails += 1
        except Exception as exc:  # noqa: BLE001 - one student's failure must not stop the batch
            logger.exception("EOD job failed for student %s", student["id"])
            result.errors.append(f"{student['id']}: {exc}")
    return result
