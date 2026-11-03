from app.agents.examiner import _force_total, select_questions, topic_breakdown


def q(marks, difficulty="medium", topic="Forces"):
    return {"question_text": f"{marks}m", "marks": marks, "mark_scheme": "ms", "difficulty": difficulty, "topic": topic}


def test_select_questions_hits_exact_total():
    chosen, exact = select_questions([q(5), q(3), q(4), q(6), q(2)], total=10, difficulty="medium")
    assert exact and sum(c["marks"] for c in chosen) == 10


def test_select_questions_prefers_matching_difficulty():
    candidates = [q(5, "easy"), q(5, "hard"), q(5, "hard"), q(5, "easy")]
    chosen, exact = select_questions(candidates, total=10, difficulty="hard")
    assert exact and {c["difficulty"] for c in chosen} == {"hard"}


def test_select_questions_reports_inexact():
    chosen, exact = select_questions([q(4), q(4)], total=10, difficulty="medium")
    assert not exact and sum(c["marks"] for c in chosen) == 8


def test_force_total_adjusts_last_question():
    fixed = _force_total([q(4), q(4)], 10)
    assert sum(x["marks"] for x in fixed) == 10 and "scaled" in fixed[-1]["mark_scheme"]


def test_topic_breakdown_sorted_weakest_first():
    rows = topic_breakdown(
        [
            {"topic": "Forces", "awarded_marks": 4, "max_marks": 4},
            {"topic": "Energy", "awarded_marks": 1, "max_marks": 4},
            {"topic": None, "awarded_marks": 1, "max_marks": 2},
        ]
    )
    assert [r["topic"] for r in rows] == ["Energy", "General", "Forces"]
    assert rows[0]["percentage"] == 25.0
