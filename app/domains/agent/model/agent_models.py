from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    agent_action: Optional[str] = None
    target_concept: Optional[str] = None
    used_tools: List[str] = Field(default_factory=list)
    created_at: datetime


class ChatSession(BaseModel):
    session_id: str
    user_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_agent_action: Optional[str] = None
    last_intervention_at: Optional[datetime] = None


class AgentDecision(BaseModel):
    action: Literal[
        "answer_with_rag",
        "proactive_hint",
        "encourage",
        "small_talk",
        "ask_followup",
    ]
    target_concept: Optional[str] = None
    should_use_rag: bool
    reason: str
