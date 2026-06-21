import secrets
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.common.security import utc_now


class TeacherMessage(BaseModel):
    """교사가 학생에게 보내는 격려/안내 메시지. append-only."""

    message_id: str = Field(default_factory=lambda: f"msg_{secrets.token_urlsafe(12)}")
    teacher_id: str
    student_id: str
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    read_at: Optional[datetime] = None
