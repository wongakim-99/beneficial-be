"""에이전트/채팅 호출 로그 저장소.

모니터링은 비즈니스 도메인이 아니라 운영 관심사이므로 infrastructure에 둔다.
agent 도메인이 호출 로그를 기록(write)하고 developer 도메인이 조회(read)하며,
두 도메인이 서로 직접 의존하지 않고 이 모듈에만 의존한다.
"""
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from app.common.logging.logging_config import get_logger
from app.common.security import utc_now
from app.infrastructure.db.mongo.mongo_client import MongoClient, get_mongo_client

logger = get_logger(__name__)


class AgentCallLog(BaseModel):
    """에이전트/채팅 1회 호출에 대한 append-only 이벤트 로그."""

    log_id: str = Field(default_factory=lambda: f"call_{secrets.token_urlsafe(12)}")
    user_id: str
    endpoint: str  # 예: "agent_chat", "chat_rag"
    action: Optional[str] = None  # AgentDecision.action (agent_chat에 한함)
    used_tools: List[str] = Field(default_factory=list)
    success: bool = True
    latency_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=utc_now)


class AgentCallLogRepository(Protocol):
    def record(self, log: Dict[str, Any]) -> str:
        ...

    def find_recent(
        self,
        endpoint: Optional[str],
        user_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        ...

    def find_since(self, since: datetime) -> List[Dict[str, Any]]:
        ...


class MongoAgentCallLogRepository:
    collection_name = "agent_call_logs"

    def __init__(self, mongo_client: MongoClient):
        self.mongo_client = mongo_client

    def record(self, log: Dict[str, Any]) -> str:
        return self.mongo_client.insert_one(self.collection_name, log)

    def find_recent(
        self,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        filter_dict: Dict[str, Any] = {}
        if endpoint:
            filter_dict["endpoint"] = endpoint
        if user_id:
            filter_dict["user_id"] = user_id
        return self.mongo_client.find_many(
            self.collection_name,
            filter_dict,
            limit=limit,
            sort=[("created_at", -1)],
        )

    def find_since(self, since: datetime) -> List[Dict[str, Any]]:
        return self.mongo_client.find_many(
            self.collection_name,
            {"created_at": {"$gte": since}},
            sort=[("created_at", -1)],
        )


def record_agent_call(
    repository: Optional[AgentCallLogRepository],
    *,
    user_id: str,
    endpoint: str,
    action: Optional[str] = None,
    used_tools: Optional[List[str]] = None,
    success: bool = True,
    latency_ms: Optional[int] = None,
) -> None:
    """호출 로그를 best-effort로 기록한다.

    모니터링 실패가 실제 요청 흐름을 깨면 안 되므로, 저장소가 없거나
    어떤 예외가 나도 조용히 무시한다.
    """
    if repository is None:
        return
    try:
        log = AgentCallLog(
            user_id=user_id,
            endpoint=endpoint,
            action=action,
            used_tools=used_tools or [],
            success=success,
            latency_ms=latency_ms,
        )
        repository.record(log.model_dump())
    except Exception as e:  # noqa: BLE001 - 모니터링 실패는 요청에 영향 주지 않는다
        logger.warning("[MONITOR] 호출 로그 기록 실패: %s", e)


_call_log_repository: Optional[MongoAgentCallLogRepository] = None


def get_call_log_repository() -> Optional[AgentCallLogRepository]:
    """호출 로그 저장소 싱글턴.

    MongoDB 연결이 불가하면 None을 반환한다. 계측은 best-effort이므로
    None이어도 호출자(record_agent_call)가 안전하게 무시한다.
    """
    global _call_log_repository
    if _call_log_repository is None:
        try:
            _call_log_repository = MongoAgentCallLogRepository(get_mongo_client())
        except Exception as e:  # noqa: BLE001
            logger.warning("[MONITOR] 호출 로그 저장소 초기화 실패: %s", e)
            return None
    return _call_log_repository
