from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domains.auth.model.auth_models import User
from app.domains.classroom.controller.teacher_class_router import list_class_students, list_my_classes
from app.domains.progress.controller.teacher_student_router import get_student_records


def _user(user_id: str = "teacher_1", role: str = "teacher") -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id=user_id,
        email=f"{user_id}@example.com",
        password_hash="hash",
        display_name=user_id,
        role=role,
        created_at=now,
        updated_at=now,
    )


class FakeClassroomService:
    def list_classes_for_user(self, user):
        return [
            SimpleNamespace(
                class_id="class_1",
                name="돌봄 1반",
                teacher_id="teacher_1",
                student_ids=["student_1"],
            )
        ]

    def get_class_for_user(self, class_id, user):
        if class_id != "class_1":
            return None
        return SimpleNamespace(
            class_id="class_1",
            name="돌봄 1반",
            teacher_id="teacher_1",
            student_ids=["student_1"],
        )

    def list_students_for_class(self, class_id, user):
        return [
            {
                "user_id": "student_1",
                "email": "student@example.com",
                "display_name": "학생",
            }
        ]

    def can_access_student(self, user, student_id):
        return student_id == "student_1"


class FakeLearningRecordService:
    def get_weakness_profile(self, user_id, min_wrong_count=2):
        weak_concept = SimpleNamespace(
            concept_key="되/돼",
            wrong_count=2,
            last_wrong_at=datetime.now(timezone.utc),
            priority=0.8,
        )
        return SimpleNamespace(user_id=user_id, weak_concepts=[weak_concept])

    def get_records(self, user_id):
        now = datetime.now(timezone.utc)
        return [
            SimpleNamespace(
                user_id=user_id,
                temp_user_id=None,
                stage=2,
                question_id="stage2_problem_1",
                concept_key="되/돼",
                user_answer="되",
                correct_answer="돼",
                is_correct=False,
                created_at=now,
                model_dump=lambda: {
                    "user_id": user_id,
                    "temp_user_id": None,
                    "stage": 2,
                    "question_id": "stage2_problem_1",
                    "concept_key": "되/돼",
                    "user_answer": "되",
                    "correct_answer": "돼",
                    "is_correct": False,
                    "created_at": now,
                },
            ),
            SimpleNamespace(
                user_id=user_id,
                temp_user_id=None,
                stage=1,
                question_id="stage1_pair_1",
                concept_key="되/돼",
                user_answer="되다",
                correct_answer="되다",
                is_correct=True,
                created_at=now - timedelta(minutes=1),
                model_dump=lambda: {
                    "user_id": user_id,
                    "temp_user_id": None,
                    "stage": 1,
                    "question_id": "stage1_pair_1",
                    "concept_key": "되/돼",
                    "user_answer": "되다",
                    "correct_answer": "되다",
                    "is_correct": True,
                    "created_at": now - timedelta(minutes=1),
                },
            ),
        ]


def test_teacher_classes_endpoint_maps_counts():
    response = list_my_classes(
        current_user=_user(),
        classroom_service=FakeClassroomService(),
    )

    assert response.total_count == 1
    assert response.classes[0].student_count == 1


def test_teacher_class_students_endpoint_includes_weak_summary():
    response = list_class_students(
        class_id="class_1",
        current_user=_user(),
        classroom_service=FakeClassroomService(),
        learning_record_service=FakeLearningRecordService(),
    )

    assert response.total_count == 1
    assert response.students[0].weak_concepts == ["되/돼"]
    assert response.students[0].recent_activity_at is not None


def test_teacher_records_endpoint_filters_by_stage():
    response = get_student_records(
        user_id="student_1",
        stage=2,
        limit=10,
        current_user=_user(),
        classroom_service=FakeClassroomService(),
        learning_record_service=FakeLearningRecordService(),
    )

    assert response.total_count == 1
    assert response.records[0].stage == 2


def test_teacher_records_endpoint_blocks_unassigned_student():
    with pytest.raises(HTTPException) as exc_info:
        get_student_records(
            user_id="student_2",
            current_user=_user(),
            classroom_service=FakeClassroomService(),
            learning_record_service=FakeLearningRecordService(),
        )

    assert exc_info.value.status_code == 403
