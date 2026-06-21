from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TeacherClassResponse(BaseModel):
    class_id: str
    name: str
    teacher_id: str
    student_count: int


class TeacherClassesResponse(BaseModel):
    classes: list[TeacherClassResponse] = Field(default_factory=list)
    total_count: int


class TeacherStudentSummaryResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    weak_concepts: list[str] = Field(default_factory=list)
    recent_activity_at: datetime | None = None


class TeacherClassStudentsResponse(BaseModel):
    class_id: str
    students: list[TeacherStudentSummaryResponse] = Field(default_factory=list)
    total_count: int


class ClassWeakConceptSummary(BaseModel):
    concept_key: str
    wrong_count: int  # 반 전체 오답 합계
    student_count: int  # 이 개념을 한 번 이상 틀린 학생 수
    last_wrong_at: datetime | None = None


class TeacherClassSummaryResponse(BaseModel):
    class_id: str
    name: str
    student_count: int  # 반 전체 학생 수
    active_student_count: int  # 학습 기록이 있는 학생 수
    participation_rate: int  # active / total (%)
    total_solved_count: int  # 반 전체 풀이 시도 수
    total_wrong_count: int  # 반 전체 오답 수
    weak_concepts: list[ClassWeakConceptSummary] = Field(default_factory=list)


class CreateClassRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class StudentMyClassResponse(BaseModel):
    class_id: str
    class_name: str
    teacher_display_name: str
    teacher_school_name: Optional[str] = None


class UserSearchResult(BaseModel):
    user_id: str
    display_name: str
    email: str


class UserSearchResponse(BaseModel):
    users: list[UserSearchResult] = Field(default_factory=list)


class AddStudentRequest(BaseModel):
    student_id: str
