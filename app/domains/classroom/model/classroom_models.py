from datetime import datetime

from pydantic import BaseModel, Field


class Classroom(BaseModel):
    class_id: str = Field(..., description="Stable class identifier")
    name: str = Field(..., description="Class display name")
    teacher_id: str = Field(..., description="Owner teacher user_id")
    student_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
