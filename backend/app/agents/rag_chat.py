"""Grounded RAG chat agent (LangChain) over the ``materials`` namespace only."""

import re
from dataclasses import dataclass
from operator import itemgetter
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompt_values import PromptValue
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnableLambda, RunnableParallel, RunnablePassthrough

from app.config import get_settings
from app.ingestion.vectorstore import VectorStore
from app.llm import EmbeddingProvider, GenerationProvider, Message

NO_CONTEXT_ANSWER = (
    "I couldn't find anything about that in your textbooks or study materials. "
    "Try rephrasing, or upload the relevant material to your library."
)

SYSTEM_PROMPT = """You are a patient study tutor. Answer the student's question using ONLY the
numbered context excerpts from their textbooks and study materials.

Rules:
- Cite every factual statement with the excerpt number in square brackets, e.g. [1] or [2][3].
- If the excerpts do not contain the answer, say so plainly; do not use outside knowledge.
- Explain clearly and step by step, at the student's level. Use short paragraphs or lists."""

_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


class MaterialsRetriever(BaseRetriever):
    """Retrieves chunks from Pinecone using the configured embedding provider."""

    embedder: Any
    store: Any
    namespace: str
    top_k: int = 6
    metadata_filter: dict | None = None

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        vector = self.embedder.embed_query(query)
        matches = self.store.query(self.namespace, vector, self.top_k, self.metadata_filter)
        return [
            Document(page_content=m.metadata.get("text", ""), metadata={**m.metadata, "score": m.score, "id": m.id})
            for m in matches
            if m.metadata.get("text")
        ]


@dataclass
class Citation:
    index: int
    doc_id: str
    page: int
    excerpt: str
    storage_path: str
    title: str | None
    score: float


@dataclass
class ChatResult:
    answer: str
    citations: list[Citation]


def format_context(docs: list[Document]) -> str:
    return "\n\n".join(
        f"[{i}] (source: {d.metadata.get('title', 'document')}, page {d.metadata.get('page')})\n{d.page_content}"
        for i, d in enumerate(docs, start=1)
    )


def cited_indices(answer: str, max_index: int) -> list[int]:
    found: list[int] = []
    for group in _CITATION_RE.findall(answer):
        for raw in group.split(","):
            n = int(raw.strip())
            if 1 <= n <= max_index and n not in found:
                found.append(n)
    return sorted(found)


def _to_messages(prompt_value: PromptValue) -> list[Message]:
    role_map = {"system": "system", "human": "user", "ai": "assistant"}
    return [Message(role_map.get(m.type, "user"), str(m.content)) for m in prompt_value.to_messages()]


def history_messages(history: list[dict]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for turn in history[-10:]:
        cls = AIMessage if turn.get("role") == "assistant" else HumanMessage
        out.append(cls(content=turn.get("content", "")))
    return out


def build_chat_chain(llm: GenerationProvider, retriever: BaseRetriever) -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("history"),
            ("human", "Context excerpts:\n{context}\n\nQuestion: {question}"),
        ]
    )
    generate = RunnableLambda(lambda pv: llm.generate(_to_messages(pv), temperature=0.1))
    answer_chain = (
        RunnableLambda(
            lambda x: {"context": format_context(x["docs"]), "question": x["question"], "history": x["history"]}
        )
        | prompt
        | generate
        | StrOutputParser()
    )
    return RunnableParallel(
        docs=itemgetter("question") | retriever,
        question=itemgetter("question"),
        history=itemgetter("history"),
    ) | RunnablePassthrough.assign(
        answer=RunnableLambda(lambda x: answer_chain.invoke(x) if x["docs"] else NO_CONTEXT_ANSWER)
    )


def run_chat(
    question: str,
    *,
    user_id: str,
    llm: GenerationProvider,
    embedder: EmbeddingProvider,
    store: VectorStore,
    history: list[dict] | None = None,
    subject_id: str | None = None,
    document_ids: list[str] | None = None,
) -> ChatResult:
    settings = get_settings()
    conditions: list[dict] = [{"$or": [{"owner_id": {"$eq": user_id}}, {"is_shared": {"$eq": True}}]}]
    if subject_id:
        conditions.append({"subject_id": {"$eq": subject_id}})
    if document_ids:
        conditions.append({"doc_id": {"$in": document_ids}})
    retriever = MaterialsRetriever(
        embedder=embedder,
        store=store,
        namespace=settings.pinecone_materials_namespace,
        top_k=settings.chat_top_k,
        metadata_filter=conditions[0] if len(conditions) == 1 else {"$and": conditions},
    )
    result = build_chat_chain(llm, retriever).invoke({"question": question, "history": history_messages(history or [])})
    docs: list[Document] = result["docs"]
    citations = [
        Citation(
            index=i,
            doc_id=docs[i - 1].metadata["doc_id"],
            page=int(docs[i - 1].metadata.get("page", 1)),
            excerpt=docs[i - 1].page_content,
            storage_path=docs[i - 1].metadata.get("storage_path", ""),
            title=docs[i - 1].metadata.get("title"),
            score=float(docs[i - 1].metadata.get("score", 0.0)),
        )
        for i in cited_indices(result["answer"], len(docs))
    ]
    return ChatResult(answer=result["answer"], citations=citations)
