"""에이전트/채팅 호출 로그를 집계해 운영 지표와 트레이스를 제공한다.

저장된 호출 로그(`agent_call_logs`)를 기간 단위로 끌어와 Python에서 집계한다.
데이터 규모가 큰 운영 환경에서는 MongoDB aggregation 파이프라인으로
옮기는 것이 좋지만, 현재 규모에서는 단순 집계로 충분하다.
"""
from collections import Counter
from datetime import timedelta
from typing import Optional

from app.common.security import utc_now
from app.infrastructure.monitoring.call_log_repository import AgentCallLogRepository


class MonitoringService:
    def __init__(self, repository: Optional[AgentCallLogRepository]):
        self.repository = repository

    def get_usage_stats(self, days: int = 7) -> dict:
        """최근 N일 호출 사용량 통계를 집계한다."""
        if self.repository is None:
            return self._empty_stats(days)

        since = utc_now() - timedelta(days=days)
        logs = self.repository.find_since(since)

        total_calls = len(logs)
        success_count = sum(1 for log in logs if log.get("success", True))
        error_count = total_calls - success_count
        unique_users = len(
            {log.get("user_id") for log in logs if log.get("user_id")}
        )
        endpoint_counter = Counter(log.get("endpoint", "unknown") for log in logs)
        action_counter = Counter(
            log.get("action") for log in logs if log.get("action")
        )
        success_rate = (
            round(success_count / total_calls * 100, 1) if total_calls else 0.0
        )

        return {
            "window_days": days,
            "total_calls": total_calls,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_rate,
            "unique_users": unique_users,
            "calls_by_endpoint": [
                {"endpoint": endpoint, "count": count}
                for endpoint, count in endpoint_counter.most_common()
            ],
            "calls_by_action": [
                {"action": action, "count": count}
                for action, count in action_counter.most_common()
            ],
        }

    def get_recent_traces(
        self,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """최근 호출 트레이스를 시간 역순으로 조회한다."""
        if self.repository is None:
            return []
        return self.repository.find_recent(
            endpoint=endpoint,
            user_id=user_id,
            limit=limit,
        )

    def _empty_stats(self, days: int) -> dict:
        return {
            "window_days": days,
            "total_calls": 0,
            "success_count": 0,
            "error_count": 0,
            "success_rate": 0.0,
            "unique_users": 0,
            "calls_by_endpoint": [],
            "calls_by_action": [],
        }
