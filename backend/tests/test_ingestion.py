from app.ingestion.chunking import chunk_pages
from app.ingestion.pdf import PageText
from app.ingestion.pipeline import build_records, namespace_for_kind
from app.ingestion.timetable_parser import parse_day, parse_grid, parse_time_range


class FakeEmbedder:
    name = "fake"
    dimension = 3

    def embed_documents(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_chunks_never_span_pages():
    pages = [PageText(1, "alpha " * 400), PageText(2, ""), PageText(3, "gamma " * 50)]
    chunks = chunk_pages(pages, chunk_size=500, chunk_overlap=50)
    assert {c.page for c in chunks} == {1, 3}
    assert all(("gamma" in c.text) == (c.page == 3) for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_namespaces_by_kind():
    assert namespace_for_kind("textbook") == "materials"
    assert namespace_for_kind("material") == "materials"
    assert namespace_for_kind("past_paper") == "pastpapers"


def test_vector_metadata_has_required_fields(monkeypatch):
    pages = [PageText(1, "Newton's first law."), PageText(2, "Newton's second law: F = ma.")]
    monkeypatch.setattr("app.ingestion.pipeline.extract_pages", lambda data: pages)
    doc = {"id": "doc-1", "storage_path": "u1/doc-1.pdf", "title": "Physics", "kind": "textbook", "owner_id": "u1"}
    records, page_count = build_records(doc, b"%PDF", FakeEmbedder())
    assert page_count == 2
    assert [r.metadata["page"] for r in records] == [1, 2]
    for r in records:
        assert r.metadata["doc_id"] == "doc-1"
        assert r.metadata["storage_path"] == "u1/doc-1.pdf"
        assert r.id.startswith("doc-1#")


def test_parse_time_range_variants():
    assert parse_time_range("09:00 - 09:45") == ("09:00", "09:45")
    assert parse_time_range("1:30-2:15") == ("13:30", "14:15")
    assert parse_time_range("11am to 12pm") == ("11:00", "12:00")
    assert parse_time_range("Lunch") is None


def test_parse_day():
    assert parse_day("Monday") == 0
    assert parse_day("FRI") == 4
    assert parse_day("Period") is None


def test_parse_grid_days_across_top():
    table = [
        ["Time", "Monday", "Tuesday"],
        ["08:00-09:00", "Maths\nMr Khan\nR12", "Physics"],
        ["09:00-09:30", "Break", "break"],
        ["09:30-10:30", "English", "Chemistry"],
    ]
    slots = parse_grid(table)
    assert len(slots) == 4
    first = slots[0]
    assert (first.day_of_week, first.start_time, first.subject_name) == (0, "08:00", "Maths")
    assert first.teacher_name == "Mr Khan" and first.location == "R12"


def test_parse_grid_days_down_side():
    table = [["", "8:00-9:00", "9:00-10:00"], ["Mon", "Maths", "Biology"], ["Wed", "History", "Art"]]
    assert {(s.day_of_week, s.subject_name) for s in parse_grid(table)} == {
        (0, "Maths"),
        (0, "Biology"),
        (2, "History"),
        (2, "Art"),
    }
