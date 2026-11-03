from datetime import date

from app.notifications.eod_job import build_report, render_email


def test_build_report_counts_and_summary():
    tasks = [
        {"id": "1", "title": "Read ch.3", "subject_id": "s1", "completed": True},
        {"id": "2", "title": "Worksheet <b>", "subject_id": None, "completed": False},
    ]
    report = build_report("stu", date(2026, 11, 4), tasks, {"s1": "Physics"})
    assert (report["total_tasks"], report["completed_tasks"], report["completion_rate"]) == (2, 1, 50.0)
    assert report["details"][0]["subject"] == "Physics"
    assert "Pending: Worksheet" in report["summary"]


def test_empty_day():
    report = build_report("stu", date(2026, 11, 4), [], {})
    assert report["completion_rate"] == 0.0 and "No tasks" in report["summary"]


def test_email_escapes_html():
    report = build_report("stu", date(2026, 11, 4), [{"id": "1", "title": "<script>", "completed": False}], {})
    subject, body = render_email("Sam", report)
    assert "Sam" in subject and "<script>" not in body
