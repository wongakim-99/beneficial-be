import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.domains.agent.repository.chat_session_repository import ChatSessionRepository
from app.domains.agent.schema.agent_schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AgentProfileResponse,
    ChatRequest,
    ChatResponse,
    ChatStatusResponse,
    ChatSessionResponse,
    WeakConceptResponse,
)
from app.domains.agent.service.agent_service import (
    AgentService,
    ChatSessionService,
    get_chat_service,
)
from app.domains.auth.dependency.auth_dependencies import get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.progress.dependency.learning_record_dependencies import get_learning_record_service
from app.domains.progress.service.learning_record_service import LearningRecordService
from app.infrastructure.rag.retriever import RagRetriever
from app.infrastructure.rag.service import RagService
from app.infrastructure.db.mongo.mongo_client import get_mongo_client
from app.infrastructure.external.openai_client import get_openai_client
from app.infrastructure.monitoring.call_log_repository import (
    AgentCallLogRepository,
    get_call_log_repository,
    record_agent_call,
)

router = APIRouter(tags=["agent"])
agent_router = APIRouter(prefix="/agent", tags=["agent"])
legacy_chat_router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_session_service() -> ChatSessionService:
    return ChatSessionService(ChatSessionRepository(get_mongo_client()))


def get_agent_service(
    session_service: ChatSessionService = Depends(get_chat_session_service),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
) -> AgentService:
    rag_service = RagService(retriever=RagRetriever(), openai_client=get_openai_client())
    return AgentService(
        session_service=session_service,
        rag_service=rag_service,
        learning_record_service=learning_record_service,
        openai_client=get_openai_client(),
    )


@agent_router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    body: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    call_log_repository: AgentCallLogRepository = Depends(get_call_log_repository),
):
    started = time.perf_counter()
    success = True
    result = None
    try:
        result = await agent_service.chat(
            user_id=current_user.user_id,
            message=body.message,
            session_id=body.session_id,
        )
        return AgentChatResponse(**result)
    except Exception:
        success = False
        raise
    finally:
        record_agent_call(
            call_log_repository,
            user_id=current_user.user_id,
            endpoint="agent_chat",
            action=(result or {}).get("agent_action"),
            used_tools=(result or {}).get("used_tools", []),
            success=success,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


@agent_router.get("/session/{session_id}", response_model=ChatSessionResponse)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    session_service: ChatSessionService = Depends(get_chat_session_service),
):
    session = session_service.get(session_id, current_user.user_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션을 찾을 수 없습니다.",
        )
    return ChatSessionResponse(**session.model_dump())


@agent_router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    session_service: ChatSessionService = Depends(get_chat_session_service),
):
    deleted = session_service.delete(session_id, current_user.user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션을 찾을 수 없습니다.",
        )


@agent_router.get("/profile/me", response_model=AgentProfileResponse)
def get_my_agent_profile(
    current_user: User = Depends(get_current_user),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
):
    if current_user.role == "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="학생에게는 약점 프로파일을 직접 제공하지 않습니다.",
        )

    profile = learning_record_service.get_weakness_profile(current_user.user_id)
    return AgentProfileResponse(
        user_id=profile.user_id,
        weak_concepts=[
            WeakConceptResponse(**wc.model_dump()) for wc in profile.weak_concepts
        ],
    )


@legacy_chat_router.post("/", response_model=ChatResponse)
async def chat_with_rag(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    call_log_repository: AgentCallLogRepository = Depends(get_call_log_repository),
):
    started = time.perf_counter()
    success = True
    try:
        top_k = 5
        collection_name = None
        chat_service = get_chat_service()
        response = await chat_service.chat_with_rag(
            prompt=request.prompt,
            collection_name=collection_name,
            top_k=top_k,
        )
        return ChatResponse(
            status="success",
            prompt=request.prompt,
            response=response,
            collection_used=collection_name or "all",
            top_k=top_k,
        )
    except Exception as e:
        success = False
        raise HTTPException(status_code=500, detail=f"채팅 실패: {str(e)}")
    finally:
        record_agent_call(
            call_log_repository,
            user_id=current_user.user_id,
            endpoint="chat_rag",
            success=success,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


@legacy_chat_router.get("/status", response_model=ChatStatusResponse)
async def get_chat_status(current_user: User = Depends(get_current_user)):
    try:
        chat_service = get_chat_service()
        collections_info = {}
        for collection_name in ["korean_word_problems", "card_check", "pdf_documents"]:
            collection = chat_service.vector_db.get_collection(collection_name)
            if collection:
                collections_info[collection_name] = {
                    "document_count": collection.count(),
                    "status": "available",
                }
            else:
                collections_info[collection_name] = {
                    "document_count": 0,
                    "status": "not_available",
                }

        return ChatStatusResponse(
            status="success",
            chat_system="active",
            rag_system="available",
            collections=collections_info,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 확인 실패: {str(e)}")


router.include_router(agent_router)
router.include_router(legacy_chat_router)
