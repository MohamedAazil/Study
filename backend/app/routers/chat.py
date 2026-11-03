from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.rag_chat import run_chat
from app.auth import CurrentUser, Role, require_roles
from app.deps import LLM, Embedder, Store
from app.llm import LLMError
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: Annotated[CurrentUser, Depends(require_roles(Role.student, Role.teacher))],
    llm: LLM,
    embedder: Embedder,
    store: Store,
) -> ChatResponse:
    try:
        result = run_chat(
            body.message,
            user_id=user.id,
            llm=llm,
            embedder=embedder,
            store=store,
            history=[t.model_dump() for t in body.history],
            subject_id=body.subject_id,
            document_ids=body.document_ids,
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return ChatResponse(answer=result.answer, citations=[asdict(c) for c in result.citations])
