"""Seed demo data: student, parent, teacher, subjects, timetable, tasks and sample PDFs.

Usage (from backend/, after running the migration):
    python -m scripts.seed                 # seeds and ingests sample docs (needs OpenAI + Pinecone)
    python -m scripts.seed --skip-ingest   # DB + storage only

Demo logins (password for all: DemoPass123!):
    student@demo.study / parent@demo.study / teacher@demo.study
"""

import argparse
import logging
import uuid
from datetime import date, timedelta

import fitz

from app.db.storage import upload_file
from app.db.supabase import get_service_client
from app.ingestion.pipeline import ingest_document, namespace_for_kind
from supabase import Client

logger = logging.getLogger("seed")
PASSWORD = "DemoPass123!"
USERS = {
    "student": ("student@demo.study", "Sam Student"),
    "parent": ("parent@demo.study", "Pat Parent"),
    "teacher": ("teacher@demo.study", "Taylor Teacher"),
}
SUBJECTS = {"Mathematics": "#4f46e5", "Physics": "#0891b2", "Chemistry": "#16a34a", "English": "#db2777"}
WEEK = [  # (day, start, end, subject, room)
    (0, "09:00", "10:00", "Mathematics", "R101"), (0, "10:15", "11:15", "Physics", "Lab 1"),
    (1, "09:00", "10:00", "Chemistry", "Lab 2"), (1, "10:15", "11:15", "English", "R204"),
    (2, "09:00", "10:00", "Mathematics", "R101"), (2, "10:15", "11:15", "Chemistry", "Lab 2"),
    (3, "09:00", "10:00", "Physics", "Lab 1"), (3, "10:15", "11:15", "Mathematics", "R101"),
    (4, "09:00", "10:00", "English", "R204"), (4, "10:15", "11:15", "Physics", "Lab 1"),
]  # fmt: skip

TEXTBOOK_PAGES = [
    "Chapter 3: Newton's Laws of Motion\n\nNewton's first law states that an object remains at rest or in uniform "
    "motion in a straight line unless acted upon by a resultant external force. This property is called inertia.",
    "Newton's second law states that the resultant force on an object is equal to the rate of change of its "
    "momentum. For constant mass this gives F = ma, where F is in newtons, m in kilograms and a in m/s^2.",
    "Newton's third law states that when body A exerts a force on body B, body B exerts an equal and opposite "
    "force on body A. The two forces act on different bodies and are of the same type.",
]
PAST_PAPER_PAGES = [
    "Physics Paper 1 (2023) - Forces and Motion\n\nQ1. State Newton's first law of motion. [2 marks]\n"
    "Mark scheme: object stays at rest or constant velocity (1); unless a resultant force acts (1).\n\n"
    "Q2. A 1200 kg car accelerates at 2.5 m/s^2. Calculate the resultant force. [3 marks]\n"
    "Mark scheme: F = ma (1); F = 1200 x 2.5 (1); F = 3000 N with unit (1).",
    "Q3. Explain, using Newton's third law, why a swimmer moves forward. [3 marks]\n"
    "Mark scheme: swimmer pushes water backwards (1); water pushes swimmer forwards (1); "
    "forces equal in size and opposite in direction (1).\n\n"
    "Q4. Define inertia. [2 marks]\nMark scheme: tendency of an object to resist changes (1) in its motion (1).",
]


def make_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(56, 56, 540, 790), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def ensure_user(db: Client, role: str) -> str:
    email, name = USERS[role]
    existing = db.table("users").select("id").eq("email", email).limit(1).execute().data
    if existing:
        return existing[0]["id"]
    created = db.auth.admin.create_user(
        {
            "email": email,
            "password": PASSWORD,
            "email_confirm": True,
            "user_metadata": {"role": role, "full_name": name},
        }
    )
    user_id = created.user.id
    # The auth trigger creates the profile; upsert in case the trigger is missing.
    db.table("users").upsert({"id": user_id, "email": email, "full_name": name, "role": role}).execute()
    return user_id


def seed(skip_ingest: bool) -> None:
    db = get_service_client()
    student_id, parent_id, teacher_id = (ensure_user(db, r) for r in ("student", "parent", "teacher"))
    logger.info("users: student=%s parent=%s teacher=%s", student_id, parent_id, teacher_id)

    db.table("parent_student_links").upsert(
        {"parent_id": parent_id, "student_id": student_id}, on_conflict="parent_id,student_id"
    ).execute()
    db.table("notification_preferences").upsert(
        {"parent_id": parent_id, "in_app_enabled": True, "email_enabled": True}, on_conflict="parent_id"
    ).execute()

    subjects = (
        db.table("subjects")
        .upsert(
            [{"student_id": student_id, "name": n, "color": c} for n, c in SUBJECTS.items()],
            on_conflict="student_id,name",
        )
        .execute()
        .data
    )
    subject_ids = {s["name"]: s["id"] for s in subjects}

    db.table("timetables").update({"is_active": False}).eq("student_id", student_id).execute()
    timetable = (
        db.table("timetables")
        .insert({"student_id": student_id, "name": "Demo timetable", "source": "manual"})
        .execute()
        .data[0]
    )
    slots = (
        db.table("timetable_slots")
        .insert(
            [
                {
                    "timetable_id": timetable["id"],
                    "subject_id": subject_ids[subj],
                    "subject_name": subj,
                    "day_of_week": day,
                    "start_time": start,
                    "end_time": end,
                    "location": room,
                }
                for day, start, end, subj, room in WEEK
            ]
        )
        .execute()
        .data
    )

    today = date.today()
    tasks = []
    for offset in range(-1, 3):
        due = today + timedelta(days=offset)
        day_slots = [s for s in slots if s["day_of_week"] == due.weekday()]
        for i, slot in enumerate(day_slots):
            tasks.append(
                {
                    "student_id": student_id,
                    "created_by": teacher_id if i == 0 else student_id,
                    "subject_id": slot["subject_id"],
                    "slot_id": slot["id"],
                    "title": f"{slot['subject_name']}: review today's lesson notes",
                    "due_date": due.isoformat(),
                    "completed": offset < 0,
                }
            )
        tasks.append(
            {
                "student_id": student_id,
                "created_by": student_id,
                "title": "Pack school bag",
                "due_date": due.isoformat(),
                "completed": offset < 0,
            }
        )
    db.table("tasks").insert(tasks).execute()
    logger.info("seeded %s slots and %s tasks", len(slots), len(tasks))

    docs = [
        ("Physics Textbook - Chapter 3", "textbook", TEXTBOOK_PAGES, "Physics"),
        ("Physics Past Paper 2023", "past_paper", PAST_PAPER_PAGES, "Physics"),
    ]
    for title, kind, pages, subject in docs:
        if db.table("documents").select("id").eq("title", title).eq("owner_id", teacher_id).execute().data:
            continue
        doc_id = str(uuid.uuid4())
        filename = f"{title.lower().replace(' ', '_').replace('-', '')}.pdf"
        data = make_pdf(pages)
        path = upload_file(db, f"{teacher_id}/{doc_id}/{filename}", data, "application/pdf")
        db.table("documents").insert(
            {
                "id": doc_id,
                "owner_id": teacher_id,
                "subject_id": None,
                "title": title,
                "filename": filename,
                "kind": kind,
                "namespace": namespace_for_kind(kind),
                "storage_path": path,
                "size_bytes": len(data),
                "is_shared": True,
            }
        ).execute()
        logger.info("uploaded %s (%s, subject %s)", title, kind, subject)
        if not skip_ingest:
            ingest_document(doc_id, db)
    logger.info("done. Log in with %s / %s", USERS["student"][0], PASSWORD)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--skip-ingest", action="store_true", help="Do not embed/upsert sample docs to Pinecone")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    seed(args.skip_ingest)
