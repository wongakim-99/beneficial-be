from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)


class TeacherMessageResponse(BaseModel):
    message_id: str
    teacher_id: str
    student_id: str
    content: str
    created_at: datetime
    read_at: Optional[datetime] = None
    is_read: bool


class MessagesResponse(BaseModel):
    messages: list[TeacherMessageResponse] = Field(default_factory=list)
    total_count: int
    unread_count: int
