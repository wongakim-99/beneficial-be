from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domains.agent.model.agent_models import AgentDecision, ChatMessage, ChatSession
from app.domains.agent.repository.chat_session_repository import ChatSessionRepository
from app.domains.agent.service.agent_service import AgentService, ChatSessionService
from app.domains.progress.model.progress_models import StudentWeaknessProfile, WeakConcept


# ---------------------------------------------------------------------------
# Fake repository
# ---------------------------------------------------------------------------

class FakeChatSessionRepository:
    def __init__(self):
        self.store: Dict[str, Dict[str, Any]] = {}

    def create(self, session: Dict[str, Any]) -> str:
        self.store[session["session_id"]] = session
        return session["session_id"]

    def find_by_session_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get(session_id)

    def find_by_user_id(self, user_id: str) -> List[Dict[str, Any]]:
        return [s for s in self.store.values() if s["user_id"] == user_id]

    def update_session(self, session_id, messages, updated_at, last_agent_action=None, last_intervention_at=None) -> bool:
        if session_id not in self.store:
            return False
        self.store[session_id]["messages"] = messages
        self.store[session_id]["updated_at"] = updated_at
        if last_agent_action is not None:
            self.store[session_id]["last_agent_action"] = last_agent_action
        if last_intervention_at is not None:
            self.store[session_id]["last_intervention_at"] = last_intervention_at
        return True

    def delete(self, session_id: str) -> bool:
        if session_id in self.store:
            del self.store[session_id]
            return True
        return False


def make_session_service() -> ChatSessionService:
    return ChatSessionService(FakeChatSessionRepository())


def _utc_now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ChatSessionService 테스트
# ---------------------------------------------------------------------------

def test_get_or_create_creates_new_session_when_no_id():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    assert session.user_id == "user_1"
    assert session.session_id.startswith("sess_")
    assert session.messages == []


def test_get_or_create_returns_existing_session():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    same = svc.get_or_create("user_1", session_id=session.session_id)
    assert same.session_id == session.session_id


def test_get_or_create_ignores_session_belonging_to_other_user():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    new_session = svc.get_or_create("user_2", session_id=session.session_id)
    assert new_session.session_id != session.session_id
    assert new_session.user_id == "user_2"


def test_append_message_persists():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    msg = ChatMessage(role="user", content="안녕", created_at=_utc_now())
    session = svc.append_message(session, msg)

    assert len(session.messages) == 1
    assert session.messages[0].content == "안녕"


def test_append_assistant_message_updates_last_agent_action():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    msg = ChatMessage(
        role="assistant",
        content="설명이야",
        agent_action="answer_with_rag",
        created_at=_utc_now(),
    )
    session = svc.append_message(session, msg)

    assert session.last_agent_action == "answer_with_rag"
    assert session.last_intervention_at is not None


def test_get_recent_messages_returns_last_10():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    for i in range(15):
        session = svc.append_message(
            session, ChatMessage(role="user", content=str(i), created_at=_utc_now())
        )

    recent = svc.get_recent_messages(session)
    assert len(recent) == 10
    assert recent[-1].content == "14"


def test_delete_removes_session():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    deleted = svc.delete(session.session_id, "user_1")
    assert deleted is True
    assert svc.get(session.session_id, "user_1") is None


def test_delete_rejects_wrong_user():
    svc = make_session_service()
    session = svc.get_or_create("user_1", session_id=None)

    deleted = svc.delete(session.session_id, "user_2")
    assert deleted is False


# ---------------------------------------------------------------------------
# AgentService._decide 테스트 (DB 없이 순수 로직)
# ---------------------------------------------------------------------------

def make_agent_service_stub() -> AgentService:
    return AgentService(
        session_service=make_session_service(),
        rag_service=MagicMock(),
        learning_record_service=MagicMock(),
        openai_client=MagicMock(),
    )


def _weak_profile(concepts=None) -> StudentWeaknessProfile:
    weak_concepts = []
    for key in (concepts or []):
        weak_concepts.append(
            WeakConcept(
                concept_key=key,
                wrong_count=3,
                last_wrong_at=_utc_now(),
                priority=0.95,
            )
        )
    return StudentWeaknessProfile(user_id="user_1", weak_concepts=weak_concepts)


def test_decide_question_triggers_rag():
    svc = make_agent_service_stub()
    decision = svc._decide("되/돼 차이가 뭐야?", _weak_profile(), [])

    assert decision.action == "answer_with_rag"
    assert decision.should_use_rag is True


def test_decide_question_mark_triggers_rag():
    svc = make_agent_service_stub()
    decision = svc._decide("맞아?", _weak_profile(), [])

    assert decision.action == "answer_with_rag"


def test_decide_proactive_hint_when_weakness_and_no_recent_intervention():
    svc = make_agent_service_stub()
    decision = svc._decide("오늘 학교 재밌었어", _weak_profile(["되/돼"]), [])

    assert decision.action == "proactive_hint"
    assert decision.target_concept == "되/돼"
    assert decision.should_use_rag is True


def test_decide_no_proactive_hint_within_cooldown():
    svc = make_agent_service_stub()
    recent = [
        ChatMessage(role="assistant", content="힌트야", agent_action="proactive_hint", created_at=_utc_now()),
        ChatMessage(role="user", content="응", created_at=_utc_now()),
    ]
    decision = svc._decide("그렇구나", _weak_profile(["되/돼"]), recent)

    assert decision.action != "proactive_hint"


def test_decide_encourage_on_positive_message():
    svc = make_agent_service_stub()
    decision = svc._decide("고마워!", _weak_profile(), [])

    assert decision.action == "encourage"
    assert decision.should_use_rag is False


def test_decide_small_talk_as_default():
    svc = make_agent_service_stub()
    decision = svc._decide("오늘 밥 맛있었어", _weak_profile(), [])

    assert decision.action == "small_talk"
    assert decision.should_use_rag is False


# ---------------------------------------------------------------------------
# AgentService.chat 통합 (mock 기반)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_chat_returns_expected_shape():
    session_service = make_session_service()

    mock_rag = MagicMock()
    mock_rag.search = AsyncMock(
        return_value=MagicMock(context="맞춤법 자료")
    )

    mock_learning = MagicMock()
    mock_learning.get_weakness_profile.return_value = _weak_profile(["되/돼"])

    mock_openai = MagicMock()
    mock_openai.generate_response_with_context = AsyncMock(return_value="되는 경우엔 '돼'를 써요!")

    svc = AgentService(
        session_service=session_service,
        rag_service=mock_rag,
        learning_record_service=mock_learning,
        openai_client=mock_openai,
    )

    result = await svc.chat(user_id="user_1", message="되/돼 차이가 뭐야?")

    assert "session_id" in result
    assert result["response"] == "되는 경우엔 '돼'를 써요!"
    assert result["agent_action"] == "answer_with_rag"
    assert "rag_search" in result["used_tools"]
    assert "되/돼" in result["weak_concepts"]
