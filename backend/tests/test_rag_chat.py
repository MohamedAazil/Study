from app.agents.rag_chat import run_chat
from app.ingestion.vectorstore import VectorMatch


class FakeStore:
    def __init__(self):
        self.calls = []

    def query(self, namespace, vector, top_k, metadata_filter=None):
        self.calls.append((namespace, metadata_filter))
        return [
            VectorMatch(
                "d1#0",
                0.9,
                {"doc_id": "d1", "page": 7, "storage_path": "t/d1.pdf", "title": "Physics", "text": "F = ma."},
            )
        ]


class FakeEmbedder:
    name = "fake"
    dimension = 3

    def embed_query(self, text):
        return [0.0, 0.0, 1.0]


class FakeLLM:
    name = "fake"

    def generate(self, messages, **kwargs):
        return "Force equals mass times acceleration [1]."


def test_chat_uses_materials_namespace_and_returns_citations():
    store = FakeStore()
    result = run_chat("What is F?", user_id="u1", llm=FakeLLM(), embedder=FakeEmbedder(), store=store)
    namespace, metadata_filter = store.calls[0]
    assert namespace == "materials"
    assert "u1" in str(metadata_filter)
    assert len(result.citations) == 1
    c = result.citations[0]
    assert (c.doc_id, c.page, c.storage_path) == ("d1", 7, "t/d1.pdf")
    assert "F = ma" in c.excerpt
