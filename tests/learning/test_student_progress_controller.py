from datetime import datetime, timezone
import pytest
from fastapi import HTTPException

from app.domains.agent.controller.agent_router import get_my_agent_profile
from app.domains.auth.model.auth_models import User
from app.domains.progress.controller.student_progress_router import get_my_progress


def _user(role: str = "student") -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id=f"user_{role}",
        email=f"{role}@example.com",
        password_hash="hash",
        display_name=role,
        role=role,
        created_at=now,
        updated_at=now,
    )


class FakeLearningRecordService:
    def get_student_progress_metrics(self, user_id):
        return {
            "today_solved_count": 4,
            "total_solved_count": 7,
            "streak_correct_count": 3,
            "completed_question_count": 5,
        }

    def get_weakness_profile(self, user_id):
        raise AssertionError("student profile endpoint should be blocked first")

    def get_records(self, user_id):
        return [
            SimpleRecord("lesson_1", 2, True),
            SimpleRecord("lesson_2", 2, True),
        ]

    def calculate_progress_rate(self, user_id, units_with_lessons):
        return 40

    def build_progress_badges(self, metrics, progress_rate):
        return ["첫 학습 시작", "연속 정답"]


class FakeContentService:
    def list_units_with_lessons(self):
        return [
            (object(), [SimpleRecord("lesson_1"), SimpleRecord("lesson_2")]),
            (object(), [SimpleRecord("lesson_3"), SimpleRecord("lesson_4"), SimpleRecord("lesson_5")]),
        ]


class SimpleRecord:
    def __init__(self, lesson_id, stage=2, is_correct=True):
        self.lesson_id = lesson_id
        self.stage = stage
        self.is_correct = is_correct


def test_student_progress_response_uses_positive_metrics_only():
    response = get_my_progress(
        current_user=_user("student"),
        learning_record_service=FakeLearningRecordService(),
        content_service=FakeContentService(),
    )

    assert response.today_solved_count == 4
    assert response.streak_correct_count == 3
    assert response.progress_rate == 40
    assert "연속 정답" in response.badges
    assert not hasattr(response, "wrong_count")


def test_agent_profile_me_rejects_students():
    with pytest.raises(HTTPException) as exc_info:
        get_my_agent_profile(
            current_user=_user("student"),
            learning_record_service=FakeLearningRecordService(),
        )

    assert exc_info.value.status_code == 403
