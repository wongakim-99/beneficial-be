import secrets
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.common.security import utc_now


AssignmentStatus = Literal["draft", "assigned", "completed", "cancelled"]
AssignmentTargetType = Literal["student", "class"]
GeneratedProblemType = Literal["fill_blank"]


class GeneratedProblem(BaseModel):
    problem_id: str = Field(default_factory=lambda: f"gen_{secrets.token_urlsafe(8)}")
    problem_key: str | None = None
    type: GeneratedProblemType = "fill_blank"
    sentence_part1: str
    correct_answer: str
    sentence_part2: str
    full_sentence: str
    explanation: str
    visual_hint: str | None = None
    accent_color: str | None = None
    validation_status: str = "pending"


class TeacherAssignment(BaseModel):
    assignment_id: str = Field(default_factory=lambda: f"assign_{secrets.token_urlsafe(16)}")
    teacher_id: str
    class_id: str | None = None
    student_id: str | None = None
    target_type: AssignmentTargetType
    unit_id: str | None = None
    lesson_id: str
    stage: int = 3
    concept_key: str
    status: AssignmentStatus = "draft"
    source: str = "ai_generated"
    problems: list[GeneratedProblem] = Field(default_factory=list)
    student_progress: dict[str, list[str]] = Field(default_factory=dict)
    generation_context: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    assigned_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None

    def model_post_init(self, __context) -> None:
        for problem in self.problems:
            if problem.problem_key is None:
                problem.problem_key = f"assignment:{self.assignment_id}:{problem.problem_id}"
