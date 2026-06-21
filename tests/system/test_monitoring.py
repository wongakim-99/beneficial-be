from datetime import datetime, timedelta, timezone

import pytest

from app.domains.developer.controller.admin_router import get_usage_stats, get_usage_traces
from app.domains.developer.service.monitoring_service import MonitoringService


def _log(**overrides):
    base = {
        "log_id": "call_x",
        "user_id": "u1",
        "endpoint": "agent_chat",
        "action": "answer_with_rag",
        "used_tools": ["rag_search"],
        "success": True,
        "latency_ms": 100,
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


class FakeCallLogRepository:
    def __init__(self, logs):
        self._logs = logs

    def record(self, log):
        self._logs.append(log)
        return log["log_id"]

    def find_since(self, since):
        return [log for log in self._logs if log["created_at"] >= since]

    def find_recent(self, endpoint=None, user_id=None, limit=50):
        items = self._logs
        if endpoint:
            items = [log for log in items if log["endpoint"] == endpoint]
        if user_id:
            items = [log for log in items if log["user_id"] == user_id]
        items = sorted(items, key=lambda log: log["created_at"], reverse=True)
        return items[:limit]


def test_usage_stats_aggregates_counts_and_success_rate():
    logs = [
        _log(log_id="1", user_id="u1", endpoint="agent_chat", action="answer_with_rag", success=True),
        _log(log_id="2", user_id="u1", endpoint="agent_chat", action="small_talk", success=True),
        _log(log_id="3", user_id="u2", endpoint="chat_rag", action=None, success=False),
    ]
    service = MonitoringService(FakeCallLogRepository(logs))

    stats = service.get_usage_stats(days=7)

    assert stats["total_calls"] == 3
    assert stats["success_count"] == 2
    assert stats["error_count"] == 1
    assert stats["unique_users"] == 2
    assert stats["success_rate"] == 66.7  # round(2/3*100, 1)
    endpoints = {item["endpoint"]: item["count"] for item in stats["calls_by_endpoint"]}
    assert endpoints == {"agent_chat": 2, "chat_rag": 1}
    actions = {item["action"]: item["count"] for item in stats["calls_by_action"]}
    assert actions == {"answer_with_rag": 1, "small_talk": 1}  # action 없는 로그는 제외


def test_usage_stats_excludes_logs_outside_window():
    now = datetime.now(timezone.utc)
    logs = [
        _log(log_id="recent", created_at=now),
        _log(log_id="old", created_at=now - timedelta(days=30)),
    ]
    service = MonitoringService(FakeCallLogRepository(logs))

    assert service.get_usage_stats(days=7)["total_calls"] == 1


def test_usage_stats_handles_missing_repository():
    service = MonitoringService(None)

    stats = service.get_usage_stats(days=7)

    assert stats["total_calls"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["calls_by_endpoint"] == []


def test_recent_traces_filters_by_endpoint():
    logs = [
        _log(log_id="1", endpoint="agent_chat"),
        _log(log_id="2", endpoint="chat_rag"),
    ]
    service = MonitoringService(FakeCallLogRepository(logs))

    traces = service.get_recent_traces(endpoint="chat_rag")

    assert len(traces) == 1
    assert traces[0]["endpoint"] == "chat_rag"


class FakeMonitoringService:
    def get_usage_stats(self, days):
        return {
            "window_days": days,
            "total_calls": 5,
            "success_count": 4,
            "error_count": 1,
            "success_rate": 80.0,
            "unique_users": 2,
            "calls_by_endpoint": [{"endpoint": "agent_chat", "count": 5}],
            "calls_by_action": [{"action": "answer_with_rag", "count": 3}],
        }

    def get_recent_traces(self, endpoint=None, user_id=None, limit=50):
        return [_log(log_id="1")]


@pytest.mark.asyncio
async def test_usage_stats_endpoint_maps_response():
    response = await get_usage_stats(days=7, monitoring_service=FakeMonitoringService())

    assert response.total_calls == 5
    assert response.success_rate == 80.0
    assert response.calls_by_endpoint[0].endpoint == "agent_chat"


@pytest.mark.asyncio
async def test_usage_traces_endpoint_maps_response():
    response = await get_usage_traces(
        endpoint=None,
        user_id=None,
        limit=50,
        monitoring_service=FakeMonitoringService(),
    )

    assert response.total_count == 1
    assert response.traces[0].endpoint == "agent_chat"
