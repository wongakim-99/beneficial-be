"""
LangGraph 기반 학습 Agent 상태 머신.

노드 흐름:
  load_context
    → decide_action
    → (rag_search) → generate_response   (should_use_rag == True)
    → generate_response                   (should_use_rag == False)
    → save_turn
    → END
"""
import logging
from typing import Any, List, Optional

from typing_extensions import TypedDict

from langgraph.graph import END, StateGraph

from app.common.security import utc_now
from app.domains.agent.model.agent_models import ChatMessage

logger = logging.getLogger(__name__)


def _short(text: Optional[str], limit: int = 40) -> str:
    """로그 한 줄에 들어갈 만큼만 잘라서 보여준다."""
    if not text:
        return ""
    flat = text.replace("\n", " ").strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# 그래프 상태
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    # 입력 (chat() 에서 채움)
    user_id: str
    session_id: Optional[str]
    user_message: str

    # load_context 이후 채워지는 필드
    session: Optional[Any]           # ChatSession
    weakness_profile: Optional[Any]  # StudentWeaknessProfile
    recent_messages: List[Any]       # List[ChatMessage]

    # decide_action 이후 채워지는 필드
    decision: Optional[Any]          # AgentDecision

    # maybe_rag_search 이후 채워지는 필드
    rag_context: str
    used_tools: List[str]

    # generate_response 이후 채워지는 필드
    response: str


# ---------------------------------------------------------------------------
# 그래프 빌더
# ---------------------------------------------------------------------------

def build_agent_graph(agent_service: Any):
    """
    agent_service: AgentService 인스턴스.
    노드 함수들이 클로저로 서비스를 참조한다.
    """

    # ── 노드 함수 ────────────────────────────────────────────────────────

    async def load_context(state: AgentState) -> dict:
        """세션 로드/생성, 사용자 메시지 저장, 약점 프로파일 조회."""
        session = agent_service.session_service.get_or_create(
            state["user_id"], state["session_id"]
        )
        user_msg = ChatMessage(
            role="user", content=state["user_message"], created_at=utc_now()
        )
        session = agent_service.session_service.append_message(session, user_msg)
        weakness_profile = agent_service.learning_record_service.get_weakness_profile(
            state["user_id"]
        )
        recent = agent_service.session_service.get_recent_messages(session)
        logger.info(
            "[AGENT] load_context: user_id=%s session=%s weak_concepts=%d recent=%d msg=%r",
            state["user_id"],
            session.session_id,
            len(getattr(weakness_profile, "weak_concepts", []) or []),
            len(recent),
            _short(state["user_message"]),
        )
        return {
            "session": session,
            "session_id": session.session_id,
            "weakness_profile": weakness_profile,
            "recent_messages": recent,
        }

    def decide_action(state: AgentState) -> dict:
        """메시지 의도 판단 → AgentDecision 생성."""
        decision = agent_service._decide(
            state["user_message"],
            state["weakness_profile"],
            state["recent_messages"],
        )
        logger.info(
            "[AGENT] decide_action: action=%s target=%s use_rag=%s reason=%r",
            decision.action,
            decision.target_concept,
            decision.should_use_rag,
            _short(decision.reason, 60),
        )
        return {"decision": decision}

    async def rag_search(state: AgentState) -> dict:
        """RagService를 호출해 관련 문서를 검색한다."""
        result = await agent_service.rag_service.search(state["user_message"])
        context = result.context or ""
        logger.info(
            "[AGENT] rag_search: query=%r context_chars=%d",
            _short(state["user_message"]),
            len(context),
        )
        return {"rag_context": context, "used_tools": ["rag_search"]}

    async def generate_response(state: AgentState) -> dict:
        """시스템 프롬프트 + (선택적) RAG context로 LLM 응답을 생성한다."""
        system_prompt = agent_service._build_system_prompt(
            state["weakness_profile"], state["decision"]
        )
        context = state.get("rag_context") or None
        response = await agent_service.openai_client.generate_response_with_context(
            prompt=state["user_message"],
            context=context,
            system_prompt=system_prompt,
        )
        logger.info(
            "[AGENT] generate_response: has_rag=%s response_chars=%d preview=%r",
            context is not None,
            len(response or ""),
            _short(response, 60),
        )
        return {"response": response}

    async def save_turn(state: AgentState) -> dict:
        """Assistant 메시지를 세션에 저장한다."""
        decision = state["decision"]
        assistant_msg = ChatMessage(
            role="assistant",
            content=state["response"],
            agent_action=decision.action,
            target_concept=decision.target_concept,
            used_tools=state.get("used_tools", []),
            created_at=utc_now(),
        )
        session = agent_service.session_service.append_message(
            state["session"], assistant_msg
        )
        logger.info(
            "[AGENT] save_turn: session=%s total_messages=%d tools=%s",
            session.session_id,
            len(session.messages),
            state.get("used_tools", []),
        )
        return {"session": session}

    # ── 라우팅 ───────────────────────────────────────────────────────────

    def route_after_decision(state: AgentState) -> str:
        next_node = "rag_search" if state["decision"].should_use_rag else "generate_response"
        logger.debug("[AGENT] route_after_decision → %s", next_node)
        return next_node

    # ── 그래프 조립 ──────────────────────────────────────────────────────

    builder = StateGraph(AgentState)

    builder.add_node("load_context", load_context)
    builder.add_node("decide_action", decide_action)
    builder.add_node("rag_search", rag_search)
    builder.add_node("generate_response", generate_response)
    builder.add_node("save_turn", save_turn)

    builder.set_entry_point("load_context")
    builder.add_edge("load_context", "decide_action")
    builder.add_conditional_edges(
        "decide_action",
        route_after_decision,
        {"rag_search": "rag_search", "generate_response": "generate_response"},
    )
    builder.add_edge("rag_search", "generate_response")
    builder.add_edge("generate_response", "save_turn")
    builder.add_edge("save_turn", END)

    return builder.compile()
