from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.domains.auth.dependency.auth_dependencies import (
    get_current_developer,
    get_current_student,
    get_current_teacher,
)
from app.domains.auth.model.auth_models import User


def _user(role: str) -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id=f"user_{role}",
        email=f"{role}@example.com",
        password_hash="hashed",
        display_name=role,
        role=role,
        created_at=now,
        updated_at=now,
    )


def test_student_dependency_accepts_only_students():
    student = _user("student")

    assert get_current_student(student).user_id == student.user_id

    with pytest.raises(HTTPException) as exc_info:
        get_current_student(_user("teacher"))
    assert exc_info.value.status_code == 403


def test_teacher_dependency_accepts_teacher_and_developer():
    teacher = _user("teacher")
    developer = _user("developer")

    assert get_current_teacher(teacher).user_id == teacher.user_id
    assert get_current_teacher(developer).user_id == developer.user_id

    with pytest.raises(HTTPException) as exc_info:
        get_current_teacher(_user("student"))
    assert exc_info.value.status_code == 403


def test_developer_dependency_accepts_only_developers():
    developer = _user("developer")

    assert get_current_developer(developer).user_id == developer.user_id

    with pytest.raises(HTTPException) as exc_info:
        get_current_developer(_user("teacher"))
    assert exc_info.value.status_code == 403
