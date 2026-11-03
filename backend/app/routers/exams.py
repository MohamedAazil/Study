import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.agents.examiner import ExaminerDeps, ExaminerError, GradingState, build_grading_graph, generate_exam
from app.auth import CurrentUser, CurrentUserDep, Role, can_view_student, require_roles
from app.config import get_settings
from app.db.storage import upload_file
from app.deps import DB, LLM, Embedder, Store
from app.ingestion.pdf import PDFParseError, full_text
from app.llm import LLMError
from app.schemas import ExamGenerateRequest
from supabase import Client

router = APIRouter(prefix="/exams", tags=["exams"])

StudentUser = Annotated[CurrentUser, Depends(require_roles(Role.student))]
MAX_ANSWER_PDF_BYTES = 20 * 1024 * 1024


def _get_exam(db: Client, user: CurrentUser, exam_id: str) -> dict:
    rows = db.table("exams").select("*").eq("id", exam_id).limit(1).execute().data
    if not rows or not can_view_student(db, user, rows[0]["student_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam not found")
    return rows[0]


def _questions(db: Client, exam_id: str) -> list[dict]:
    return db.table("exam_questions").select("*").eq("exam_id", exam_id).order("position").execute().data


def _public_questions(questions: list[dict], reveal_schemes: bool) -> list[dict]:
    return [q if reveal_schemes else {k: v for k, v in q.items() if k != "mark_scheme"} for q in questions]


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def generate(body: ExamGenerateRequest, user: StudentUser, db: DB, llm: LLM, embedder: Embedder, store: Store) -> dict:
    settings = get_settings()
    deps = ExaminerDeps(
        llm=llm, embedder=embedder, store=store,
        namespace=settings.pinecone_pastpapers_namespace, top_k=settings.examiner_top_k,
    )  # fmt: skip
    try:
        state = generate_exam(
            deps, student_id=user.id, topic=body.topic, total_marks=body.total_marks, difficulty=body.difficulty
        )
    except ExaminerError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    exam = (
        db.table("exams")
        .insert(
            {
                "student_id": user.id,
                "topic": body.topic,
                "total_marks": body.total_marks,
                "difficulty": body.difficulty,
                "instructions": state.get("instructions"),
            }
        )
        .execute()
        .data[0]
    )
    rows = [
        {
            "exam_id": exam["id"],
            "position": i,
            "question_text": q["question_text"],
            "marks": q["marks"],
            "mark_scheme": q["mark_scheme"],
            "topic": q.get("topic"),
            "source_doc_id": q.get("source_doc_id"),
            "source_page": q.get("source_page"),
            "source_storage_path": q.get("source_storage_path"),
        }
        for i, q in enumerate(state["questions"], start=1)
    ]
    questions = db.table("exam_questions").insert(rows).execute().data
    return {**exam, "questions": _public_questions(questions, reveal_schemes=False)}


@router.get("")
def list_exams(user: CurrentUserDep, db: DB, student_id: str | None = None) -> list[dict]:
    sid = user.id if user.role == Role.student else student_id
    if not sid or not can_view_student(db, user, sid):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    return db.table("exams").select("*").eq("student_id", sid).order("created_at", desc=True).execute().data


@router.get("/{exam_id}")
def get_exam(exam_id: str, user: CurrentUserDep, db: DB) -> dict:
    exam = _get_exam(db, user, exam_id)
    return {**exam, "questions": _public_questions(_questions(db, exam_id), reveal_schemes=exam["status"] == "graded")}


def _answer_script(answer_text: str | None, answers: str | None, questions: list[dict]) -> str:
    parts: list[str] = []
    if answers:
        try:
            mapping = json.loads(answers)
        except json.JSONDecodeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "answers must be JSON") from exc
        by_id = {q["id"]: q["position"] for q in questions}
        for key, value in mapping.items():
            position = by_id.get(key) or (int(key) if str(key).isdigit() else None)
            if position and str(value).strip():
                parts.append(f"Question {position}:\n{str(value).strip()}")
    if answer_text and answer_text.strip():
        parts.append(answer_text.strip())
    return "\n\n".join(parts)


@router.post("/{exam_id}/submit")
async def submit(
    exam_id: str,
    user: StudentUser,
    db: DB,
    llm: LLM,
    submission_type: Annotated[Literal["text", "pdf", "image"], Form()],
    answer_text: Annotated[str | None, Form()] = None,
    answers: Annotated[str | None, Form(description='JSON {"<question_id or number>": "answer"}')] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    exam = _get_exam(db, user, exam_id)
    if exam["student_id"] != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your exam")
    if exam["status"] == "graded":
        raise HTTPException(status.HTTP_409_CONFLICT, "Exam already graded")
    if submission_type == "image":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Handwritten image submissions are not supported yet; use text or PDF.",
        )

    questions = _questions(db, exam_id)
    storage_path = None
    if submission_type == "pdf":
        if file is None or file.content_type not in ("application/pdf", "application/x-pdf"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A typed PDF file is required")
        data = await file.read()
        if len(data) > MAX_ANSWER_PDF_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF too large (max 20MB)")
        try:
            script = full_text(data)
        except PDFParseError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        storage_path = upload_file(db, f"{user.id}/submissions/{exam_id}/{uuid.uuid4()}.pdf", data, "application/pdf")
    else:
        script = _answer_script(answer_text, answers, questions)
    if not script.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Submission is empty")

    submission = (
        db.table("exam_submissions")
        .insert(
            {
                "exam_id": exam_id,
                "student_id": user.id,
                "submission_type": submission_type,
                "answer_text": script,
                "storage_path": storage_path,
            }
        )
        .execute()
        .data[0]
    )
    db.table("exams").update({"status": "submitted"}).eq("id", exam_id).execute()

    def persist(state: GradingState) -> None:
        db.table("grades").insert(
            [
                {
                    "submission_id": submission["id"],
                    "exam_id": exam_id,
                    "question_id": g["question_id"],
                    "awarded_marks": g["awarded_marks"],
                    "max_marks": g["max_marks"],
                    "feedback": g["feedback"],
                    "topic": g["topic"],
                }
                for g in state["grades"]
            ]
        ).execute()
        db.table("exam_submissions").update(
            {
                "total_awarded": state["total_awarded"],
                "total_available": state["total_available"],
                "focus_report": state["focus_report"],
                "graded_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", submission["id"]).execute()
        db.table("exams").update({"status": "graded"}).eq("id", exam_id).execute()

    try:
        state = build_grading_graph(ExaminerDeps(llm=llm), persist=persist).invoke(
            {"exam": exam, "questions": questions, "answer_script": script}
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Grading failed: {exc}") from exc
    return {
        "submission_id": submission["id"],
        "total_awarded": state["total_awarded"],
        "total_available": state["total_available"],
        "grades": state["grades"],
        "focus_report": state["focus_report"],
    }


@router.get("/{exam_id}/result")
def get_result(exam_id: str, user: CurrentUserDep, db: DB) -> dict:
    exam = _get_exam(db, user, exam_id)
    submissions = (
        db.table("exam_submissions")
        .select("*")
        .eq("exam_id", exam_id)
        .not_.is_("graded_at", "null")
        .order("graded_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not submissions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No graded submission yet")
    submission = submissions[0]
    grades = db.table("grades").select("*").eq("submission_id", submission["id"]).execute().data
    return {
        "exam": exam,
        "questions": _questions(db, exam_id),
        "submission": submission,
        "grades": grades,
        "focus_report": submission.get("focus_report"),
    }
