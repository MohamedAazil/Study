"""Examiner agent (LangGraph).

Generation graph:  retrieve -> extract -> select --(exact total?)--> END
                                                  \\-> adapt -> END
Grading graph:     grade -> focus_report -> persist -> END
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.ingestion.vectorstore import VectorStore
from app.llm import EmbeddingProvider, GenerationProvider, Message
from app.llm.base import parse_json_response

logger = logging.getLogger(__name__)


class ExaminerError(RuntimeError):
    pass


@dataclass
class ExaminerDeps:
    llm: GenerationProvider
    embedder: EmbeddingProvider | None = None
    store: VectorStore | None = None
    namespace: str = "pastpapers"
    top_k: int = 20


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
class ExamGenState(TypedDict, total=False):
    student_id: str
    topic: str
    total_marks: int
    difficulty: str
    sources: list[dict]
    candidates: list[dict]
    questions: list[dict]
    exact: bool
    instructions: str


_EXTRACT_PROMPT = """You are an experienced examiner. From the numbered past-paper excerpts, extract
self-contained exam questions together with their mark schemes. Only use questions that are relevant
to the requested topic. If an excerpt contains a question but its mark scheme is elsewhere in the
excerpts, pair them. If no mark scheme exists, write a concise, examiner-style one from the excerpts.

Return JSON: {"questions": [{"question_text": str, "marks": int, "mark_scheme": str,
"topic": str (specific sub-topic), "difficulty": "easy"|"medium"|"hard", "source": int (excerpt number)}]}"""

_ADAPT_PROMPT = """You are an examiner assembling a practice paper. Using the candidate questions,
produce a paper whose marks sum to EXACTLY {total} at {difficulty} difficulty. You may drop questions,
split multi-part questions, or re-allocate marks, but you must update each mark scheme so it awards
exactly the stated marks. Keep each question's "source" number.

Return JSON: {{"questions": [{{"question_text": str, "marks": int, "mark_scheme": str, "topic": str,
"difficulty": str, "source": int}}]}}"""

DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


def select_questions(candidates: list[dict], total: int, difficulty: str) -> tuple[list[dict], bool]:
    """Subset-sum over marks maximising difficulty match; exact total preferred."""
    target_rank = DIFFICULTY_RANK.get(difficulty, 1)

    def fit(q: dict) -> int:
        return 2 - abs(DIFFICULTY_RANK.get(q.get("difficulty", "medium"), 1) - target_rank)

    # best[s] = (score, indices) for the best subset summing to s
    best: dict[int, tuple[int, list[int]]] = {0: (0, [])}
    for i, q in enumerate(candidates):
        marks = int(q.get("marks") or 0)
        if marks <= 0 or marks > total:
            continue
        for s, (score, idxs) in sorted(best.items(), reverse=True):
            new_sum = s + marks
            if new_sum > total:
                continue
            new_score = score + fit(q)
            if new_sum not in best or new_score > best[new_sum][0]:
                best[new_sum] = (new_score, [*idxs, i])
    if total in best:
        return [candidates[i] for i in best[total][1]], True
    reachable = max((s for s in best if s > 0), default=0)
    return [candidates[i] for i in best.get(reachable, (0, []))[1]], False


def _force_total(questions: list[dict], total: int) -> list[dict]:
    """Deterministic last resort: adjust the final question so marks sum to ``total``."""
    if not questions:
        return questions
    diff = total - sum(int(q["marks"]) for q in questions)
    last = dict(questions[-1])
    if int(last["marks"]) + diff <= 0:
        return questions
    last["marks"] = int(last["marks"]) + diff
    last["mark_scheme"] = f"{last['mark_scheme']}\n(Marks scaled to {last['marks']} to fit the paper total.)"
    return [*questions[:-1], last]


def _normalise_questions(raw: Any, sources: list[dict]) -> list[dict]:
    items = raw.get("questions", []) if isinstance(raw, dict) else []
    out = []
    for item in items:
        try:
            marks = int(item["marks"])
            text = str(item["question_text"]).strip()
            scheme = str(item.get("mark_scheme") or "").strip()
        except (KeyError, TypeError, ValueError):
            continue
        if marks <= 0 or not text or not scheme:
            continue
        src_idx = item.get("source")
        source = sources[src_idx - 1] if isinstance(src_idx, int) and 1 <= src_idx <= len(sources) else {}
        out.append(
            {
                "question_text": text,
                "marks": marks,
                "mark_scheme": scheme,
                "topic": str(item.get("topic") or "").strip() or None,
                "difficulty": str(item.get("difficulty") or "medium").lower(),
                "source": src_idx,
                "source_doc_id": source.get("doc_id"),
                "source_page": source.get("page"),
                "source_storage_path": source.get("storage_path"),
            }
        )
    return out


def build_generation_graph(deps: ExaminerDeps):
    def retrieve(state: ExamGenState) -> ExamGenState:
        if deps.embedder is None or deps.store is None:
            raise ExaminerError("Vector store not configured")
        topic = state["topic"]
        access = {"$or": [{"owner_id": {"$eq": state["student_id"]}}, {"is_shared": {"$eq": True}}]}
        seen: dict[str, dict] = {}
        for query in (topic, f"{topic} exam question with mark scheme", f"{topic} marking scheme answers"):
            for m in deps.store.query(deps.namespace, deps.embedder.embed_query(query), deps.top_k, access):
                if m.id not in seen and m.metadata.get("text"):
                    seen[m.id] = {**m.metadata, "score": m.score}
        sources = sorted(seen.values(), key=lambda s: s["score"], reverse=True)[: deps.top_k]
        if not sources:
            raise ExaminerError(f"No past-paper material found for '{topic}'. Upload past papers first.")
        return {"sources": sources}

    def extract(state: ExamGenState) -> ExamGenState:
        excerpts = "\n\n".join(
            f"[{i}] ({s.get('title')}, page {s.get('page')})\n{s['text']}" for i, s in enumerate(state["sources"], 1)
        )
        response = deps.llm.generate(
            [
                Message("system", _EXTRACT_PROMPT),
                Message("user", f"Topic: {state['topic']}\nTarget difficulty: {state['difficulty']}\n\n{excerpts}"),
            ],
            temperature=0.2,
            json_mode=True,
        )
        candidates = _normalise_questions(parse_json_response(response), state["sources"])
        if not candidates:
            raise ExaminerError("Could not extract any questions for this topic from past papers.")
        return {"candidates": candidates}

    def select(state: ExamGenState) -> ExamGenState:
        questions, exact = select_questions(state["candidates"], state["total_marks"], state["difficulty"])
        return {"questions": questions, "exact": exact}

    def adapt(state: ExamGenState) -> ExamGenState:
        payload = [
            {k: q[k] for k in ("question_text", "marks", "mark_scheme", "topic", "difficulty", "source")}
            for q in state["candidates"]
        ]
        try:
            response = deps.llm.generate(
                [
                    Message("system", _ADAPT_PROMPT.format(total=state["total_marks"], difficulty=state["difficulty"])),
                    Message("user", f"Candidate questions:\n{payload}"),
                ],
                temperature=0.2,
                json_mode=True,
            )
            adapted = _normalise_questions(parse_json_response(response), state["sources"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("adapt node failed, using deterministic fallback: %s", exc)
            adapted = []
        if adapted and sum(q["marks"] for q in adapted) == state["total_marks"]:
            return {"questions": adapted, "exact": True}
        base = adapted or state["questions"] or state["candidates"][:1]
        return {"questions": _force_total(base, state["total_marks"]), "exact": True}

    def finalise(state: ExamGenState) -> ExamGenState:
        return {
            "instructions": (
                f"Answer all questions. Total: {state['total_marks']} marks. "
                f"Topic: {state['topic']}. Difficulty: {state['difficulty']}."
            )
        }

    graph = StateGraph(ExamGenState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("extract", extract)
    graph.add_node("select", select)
    graph.add_node("adapt", adapt)
    graph.add_node("finalise", finalise)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "extract")
    graph.add_edge("extract", "select")
    graph.add_conditional_edges("select", lambda s: "finalise" if s["exact"] else "adapt")
    graph.add_edge("adapt", "finalise")
    graph.add_edge("finalise", END)
    return graph.compile()


def generate_exam(
    deps: ExaminerDeps, *, student_id: str, topic: str, total_marks: int, difficulty: str
) -> ExamGenState:
    return build_generation_graph(deps).invoke(
        {"student_id": student_id, "topic": topic, "total_marks": total_marks, "difficulty": difficulty}
    )


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
class GradingState(TypedDict, total=False):
    exam: dict
    questions: list[dict]  # rows from exam_questions
    answer_script: str
    grades: list[dict]
    total_awarded: float
    total_available: int
    focus_report: dict


_GRADE_PROMPT = """You are a strict but fair examiner. Mark the student's answer script against each
question's mark scheme. Award marks only for points that match the mark scheme (allow equivalent
wording). Half marks are not allowed unless the mark scheme says so. Locate each answer in the script
by its question number; if an answer is missing, award 0.

Return JSON: {"grades": [{"question": int (question number), "awarded_marks": number,
"feedback": str (what earned/lost marks, 1-3 sentences)}]}"""

_FOCUS_PROMPT = """You are a study coach. Given per-topic exam performance, write a short focus report.
Return JSON: {"summary": str (2-3 sentences), "focus_areas": [{"topic": str, "advice": str}]}
Order focus_areas from weakest to strongest; include only topics below 80%."""


def topic_breakdown(grades: list[dict]) -> list[dict]:
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for g in grades:
        key = g.get("topic") or "General"
        totals[key][0] += float(g["awarded_marks"])
        totals[key][1] += float(g["max_marks"])
    rows = [
        {"topic": t, "awarded": a, "available": m, "percentage": round(100 * a / m, 1) if m else 0.0}
        for t, (a, m) in totals.items()
    ]
    return sorted(rows, key=lambda r: r["percentage"])


def build_grading_graph(deps: ExaminerDeps, persist: Callable[[GradingState], None] | None = None):
    def grade(state: GradingState) -> GradingState:
        questions = sorted(state["questions"], key=lambda q: q["position"])
        paper = "\n\n".join(
            f"Question {q['position']} [{q['marks']} marks]\n{q['question_text']}\nMark scheme:\n{q['mark_scheme']}"
            for q in questions
        )
        response = deps.llm.generate(
            [
                Message("system", _GRADE_PROMPT),
                Message("user", f"PAPER\n{paper}\n\nSTUDENT ANSWER SCRIPT\n{state['answer_script'][:30000]}"),
            ],
            temperature=0,
            json_mode=True,
        )
        raw = parse_json_response(response)
        by_number = {}
        for item in raw.get("grades", []) if isinstance(raw, dict) else []:
            try:
                by_number[int(item["question"])] = item
            except (KeyError, TypeError, ValueError):
                continue
        grades = []
        for q in questions:
            item = by_number.get(q["position"], {})
            try:
                awarded = float(item.get("awarded_marks", 0))
            except (TypeError, ValueError):
                awarded = 0.0
            grades.append(
                {
                    "question_id": q["id"],
                    "position": q["position"],
                    "awarded_marks": max(0.0, min(awarded, float(q["marks"]))),
                    "max_marks": int(q["marks"]),
                    "feedback": item.get("feedback") or "No answer found for this question.",
                    "topic": q.get("topic"),
                }
            )
        return {
            "grades": grades,
            "total_awarded": sum(g["awarded_marks"] for g in grades),
            "total_available": sum(g["max_marks"] for g in grades),
        }

    def focus_report(state: GradingState) -> GradingState:
        breakdown = topic_breakdown(state["grades"])
        report: dict[str, Any] = {"topics": breakdown, "summary": "", "focus_areas": []}
        try:
            response = deps.llm.generate(
                [
                    Message("system", _FOCUS_PROMPT),
                    Message(
                        "user",
                        f"Exam topic: {state['exam'].get('topic')}\nScore: {state['total_awarded']}/"
                        f"{state['total_available']}\nPer-topic: {breakdown}\n"
                        f"Feedback: {[g['feedback'] for g in state['grades']]}",
                    ),
                ],
                temperature=0.3,
                json_mode=True,
            )
            data = parse_json_response(response)
            report["summary"] = str(data.get("summary", ""))
            report["focus_areas"] = list(data.get("focus_areas", []))
        except Exception as exc:  # noqa: BLE001
            logger.warning("focus report LLM call failed: %s", exc)
            weak = [r for r in breakdown if r["percentage"] < 80]
            report["summary"] = f"You scored {state['total_awarded']:g}/{state['total_available']}."
            report["focus_areas"] = [
                {"topic": r["topic"], "advice": f"Revise {r['topic']} ({r['percentage']}%)."} for r in weak
            ]
        return {"focus_report": report}

    def persist_node(state: GradingState) -> GradingState:
        if persist is not None:
            persist(state)
        return {}

    graph = StateGraph(GradingState)
    graph.add_node("grade", grade)
    graph.add_node("focus_report", focus_report)
    graph.add_node("persist", persist_node)
    graph.set_entry_point("grade")
    graph.add_edge("grade", "focus_report")
    graph.add_edge("focus_report", "persist")
    graph.add_edge("persist", END)
    return graph.compile()
