import secrets
from typing import Any, Dict, List, Optional

from app.common.security import utc_now
from app.common.logging.logging_config import get_logger
from app.domains.agent.model.agent_models import AgentDecision, ChatMessage, ChatSession
from app.domains.agent.repository.chat_session_repository import ChatSessionRepository
from app.domains.progress.model.progress_models import StudentWeaknessProfile
from app.domains.progress.service.learning_record_service import LearningRecordService
from app.infrastructure.db.vector.vector_db import get_vector_db
from app.infrastructure.embedding.embedding_model import get_embedding_model
from app.infrastructure.external.openai_client import OpenAIClient
from app.infrastructure.rag.retriever import RagRetriever
from app.infrastructure.rag.service import RagService
from app.infrastructure.search.hybrid_search import get_hybrid_search_service


INTERVENTION_COOLDOWN_TURNS = 3  # proactive hint 사이 최소 assistant 턴 수
RECENT_TURNS = 10                 # Agent가 참조할 최근 대화 수
logger = get_logger(__name__)


class ChatSessionService:
    def __init__(self, repository: ChatSessionRepository):
        self.repository = repository

    def get_or_create(self, user_id: str, session_id: Optional[str]) -> ChatSession:
        if session_id:
            doc = self.repository.find_by_session_id(session_id)
            if doc and doc.get("user_id") == user_id:
                return ChatSession(**doc)

        now = utc_now()
        session = ChatSession(
            session_id=f"sess_{secrets.token_urlsafe(16)}",
            user_id=user_id,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        self.repository.create(session.model_dump())
        return session

    def get(self, session_id: str, user_id: str) -> Optional[ChatSession]:
        doc = self.repository.find_by_session_id(session_id)
        if doc and doc.get("user_id") == user_id:
            return ChatSession(**doc)
        return None

    def append_message(self, session: ChatSession, message: ChatMessage) -> ChatSession:
        session.messages.append(message)
        session.updated_at = utc_now()

        if message.role == "assistant" and message.agent_action:
            session.last_agent_action = message.agent_action
            if message.agent_action in ("proactive_hint", "answer_with_rag"):
                session.last_intervention_at = message.created_at

        self.repository.update_session(
            session.session_id,
            [m.model_dump() for m in session.messages],
            session.updated_at,
            session.last_agent_action,
            session.last_intervention_at,
        )
        return session

    def get_recent_messages(self, session: ChatSession) -> List[ChatMessage]:
        return session.messages[-RECENT_TURNS:]

    def delete(self, session_id: str, user_id: str) -> bool:
        doc = self.repository.find_by_session_id(session_id)
        if not doc or doc.get("user_id") != user_id:
            return False
        return self.repository.delete(session_id)


class AgentService:
    def __init__(
        self,
        session_service: ChatSessionService,
        rag_service,
        learning_record_service: LearningRecordService,
        openai_client,
    ):
        self.session_service = session_service
        self.rag_service = rag_service
        self.learning_record_service = learning_record_service
        self.openai_client = openai_client

        from app.domains.agent.service.graph import build_agent_graph
        self._graph = build_agent_graph(self)

    async def chat(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> dict:
        from app.domains.agent.service.graph import AgentState
        initial: AgentState = {
            "user_id": user_id,
            "session_id": session_id,
            "user_message": message,
            "session": None,
            "weakness_profile": None,
            "recent_messages": [],
            "decision": None,
            "rag_context": "",
            "used_tools": [],
            "response": "",
        }
        result = await self._graph.ainvoke(initial)
        return {
            "session_id": result["session"].session_id,
            "response": result["response"],
            "agent_action": result["decision"].action,
            "target_concept": result["decision"].target_concept,
            "used_tools": result.get("used_tools", []),
            "weak_concepts": [
                wc.concept_key for wc in result["weakness_profile"].weak_concepts
            ],
        }

    def _decide(
        self,
        message: str,
        weakness_profile: StudentWeaknessProfile,
        recent_messages: List[ChatMessage],
    ) -> AgentDecision:
        if self._is_question(message):
            return AgentDecision(
                action="answer_with_rag",
                should_use_rag=True,
                reason="사용자가 질문을 했습니다.",
            )

        if weakness_profile.weak_concepts and self._should_intervene(recent_messages):
            top_concept = weakness_profile.weak_concepts[0].concept_key
            return AgentDecision(
                action="proactive_hint",
                target_concept=top_concept,
                should_use_rag=True,
                reason=f"약점 개념 '{top_concept}'에 대한 선제 힌트 제공",
            )

        if self._is_positive(message):
            return AgentDecision(
                action="encourage",
                should_use_rag=False,
                reason="학생의 긍정적 반응에 칭찬 및 격려",
            )

        return AgentDecision(
            action="small_talk",
            should_use_rag=False,
            reason="일반 대화 처리",
        )

    def _is_question(self, message: str) -> bool:
        markers = [
            "?", "？", "뭐야", "뭐예요", "왜", "어떻게", "무슨", "어떤",
            "맞아", "맞나", "인가요", "인가", "인지", "알려줘", "설명해",
            "뭐가", "어디", "언제", "누가",
        ]
        return any(m in message for m in markers)

    def _should_intervene(self, recent_messages: List[ChatMessage]) -> bool:
        assistant_turns = [m for m in recent_messages if m.role == "assistant"]
        for i, turn in enumerate(reversed(assistant_turns)):
            if turn.agent_action in ("proactive_hint", "answer_with_rag"):
                return i >= INTERVENTION_COOLDOWN_TURNS
        return True

    def _is_positive(self, message: str) -> bool:
        markers = ["고마워", "감사", "알겠어", "이해했어", "맞아!", "좋아", "완벽"]
        return any(m in message for m in markers)

    def _build_system_prompt(
        self,
        weakness_profile: StudentWeaknessProfile,
        decision: AgentDecision,
    ) -> str:
        weak_str = ""
        if weakness_profile.weak_concepts:
            items = [
                f"{wc.concept_key}({wc.wrong_count}회)"
                for wc in weakness_profile.weak_concepts[:3]
            ]
            weak_str = f"\n- 최근 틀린 개념: {', '.join(items)}"

        hint_instruction = ""
        if decision.action == "proactive_hint" and decision.target_concept:
            hint_instruction = (
                f"\n- 지금 대화에 '{decision.target_concept}' 관련 설명을 자연스럽게 섞어줘."
            )

        return (
            "너는 초등학생 돌봄 선생님이야. "
            "쉽고 친근한 말로 한국어 맞춤법을 가르쳐줘.\n"
            f"[학생 정보]{weak_str}"
            "\n[대화 방침]"
            "\n- 어려운 말은 쓰지 마."
            "\n- 칭찬을 자주 해줘."
            "\n- 설명은 짧고 간단하게."
            f"{hint_instruction}"
        )


class ChatService:
    """Legacy /chat API 서비스. Agent 도메인 내부에서 RAG 채팅을 담당한다."""

    def __init__(
        self,
        openai_client: OpenAIClient = None,
        vector_db=None,
        embedding_model=None,
    ):
        self.openai_client = openai_client or OpenAIClient()
        self.vector_db = vector_db or get_vector_db()
        self.embedding_model = embedding_model or get_embedding_model()
        self.hybrid_search = get_hybrid_search_service()
        self.rag_service = RagService(
            retriever=RagRetriever(self.hybrid_search),
            openai_client=self.openai_client,
        )
        self.default_system_prompt = (
            "너는 초등학생 돌봄선생님이야. "
            "주어진 참고 자료를 바탕으로 정확하고 친근하게 답변해줘.\n"
            "아이들에게 친절하게 알려주는 튜터처럼 다정한 반말로 이야기해줘. "
            "어려운 말은 쓰지 말고, 설명은 짧고 쉽게 해줘. "
            "참고 자료가 있으면 그것을 우선적으로 활용해줘."
        )

    async def chat_with_rag(
        self,
        prompt: str,
        collection_name: str = None,
        top_k: int = 3,
    ) -> str:
        try:
            logger.info(
                f"[SEARCH] RAG 채팅 시작: '{prompt}' "
                f"(top_k={top_k}, collection={collection_name or 'all'})"
            )
            response = await self.rag_service.answer(
                query=prompt,
                system_prompt=self.default_system_prompt,
                collection_name=collection_name,
                top_k=top_k,
            )
            logger.info(f"[OK] GPT 응답 생성 완료: {len(response)}자")
            return response
        except Exception as e:
            logger.error(f"[ERROR] RAG 채팅 실패: {e}")
            return f"죄송합니다. 채팅 처리 중 오류가 발생했습니다: {str(e)}"

    async def search_relevant_documents(
        self,
        query: str,
        collection_name: str = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        try:
            search_result = await self.rag_service.search(
                query=query,
                collection_name=collection_name,
                top_k=top_k,
            )
            return [
                doc.model_dump() if hasattr(doc, "model_dump") else doc.dict()
                for doc in search_result.documents
            ]
        except Exception as e:
            logger.error(f"[ERROR] 하이브리드 검색 실패: {e}")
            return []

    async def generate_response_with_context(self, prompt: str, context: str) -> str:
        try:
            return await self.openai_client.generate_response_with_context(
                prompt=prompt,
                context=context,
                system_prompt=self.default_system_prompt,
            )
        except Exception as e:
            logger.error(f"[ERROR] GPT 응답 생성 실패: {e}")
            return f"죄송합니다. 응답 생성 중 오류가 발생했습니다: {str(e)}"

    def build_context_from_documents(self, documents: List[Dict[str, Any]]) -> str:
        from app.infrastructure.rag.schemas import RagDocument

        rag_documents = [RagDocument(**doc) for doc in documents]
        return self.rag_service.build_context(rag_documents)

    async def simple_chat(self, prompt: str) -> str:
        try:
            messages = [
                {"role": "system", "content": self.default_system_prompt},
                {"role": "user", "content": prompt},
            ]
            return await self.openai_client.chat_completion(messages)
        except Exception as e:
            logger.error(f"[ERROR] 간단 채팅 실패: {e}")
            return f"죄송합니다. 응답 생성 중 오류가 발생했습니다: {str(e)}"


def get_chat_service() -> ChatService:
    return ChatService()
