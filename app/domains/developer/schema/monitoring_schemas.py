from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EndpointCount(BaseModel):
    endpoint: str
    count: int


class ActionCount(BaseModel):
    action: str
    count: int


class UsageStatsResponse(BaseModel):
    window_days: int
    total_calls: int
    success_count: int
    error_count: int
    success_rate: float  # 0~100 (%)
    unique_users: int
    calls_by_endpoint: list[EndpointCount] = Field(default_factory=list)
    calls_by_action: list[ActionCount] = Field(default_factory=list)


class TraceLog(BaseModel):
    log_id: str
    user_id: str
    endpoint: str
    action: Optional[str] = None
    used_tools: list[str] = Field(default_factory=list)
    success: bool
    latency_ms: Optional[int] = None
    created_at: datetime


class TracesResponse(BaseModel):
    traces: list[TraceLog] = Field(default_factory=list)
    total_count: int
