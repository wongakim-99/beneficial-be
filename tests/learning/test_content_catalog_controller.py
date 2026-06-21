import pytest
from datetime import datetime, timezone

from app.domains.auth.model.auth_models import User
from app.domains.content.model.content_models import Lesson, Unit
from app.domains.content.controller.catalog_router import get_content_lesson, get_content_units


def _user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id="student_1",
        email="student@example.com",
        password_hash="hash",
        display_name="학생",
        role="student",
        created_at=now,
        updated_at=now,
    )


class FakeContentCatalogService:
    def list_units_with_lessons(self):
        return [
            (
                Unit(
                    unit_id="unit_1",
                    name="1단원",
                    order=1,
                    lesson_ids=["lesson_1"],
                ),
                [
                    Lesson(
                        lesson_id="lesson_1",
                        unit_id="unit_1",
                        name="차시 1",
                        order=1,
                        concept_keys=["A/B"],
                        stage_ids=[1, 2, 3],
                    )
                ],
            )
        ]

    def get_lesson(self, lesson_id):
        if lesson_id != "lesson_1":
            return None
        return Lesson(
            lesson_id="lesson_1",
            unit_id="unit_1",
            name="차시 1",
            order=1,
            concept_keys=["A/B"],
            stage_ids=[1, 2, 3],
        )


def test_content_units_endpoint_maps_tree():
    response = get_content_units(
        current_user=_user(),
        content_service=FakeContentCatalogService(),
    )

    assert response.total_count == 1
    assert response.units[0].lessons[0].lesson_id == "lesson_1"


def test_content_lesson_endpoint_returns_detail():
    response = get_content_lesson(
        lesson_id="lesson_1",
        current_user=_user(),
        content_service=FakeContentCatalogService(),
    )

    assert response.lesson_id == "lesson_1"
    assert response.concept_keys == ["A/B"]


def test_content_lesson_endpoint_raises_404_when_missing():
    with pytest.raises(Exception) as exc:
        get_content_lesson(
            lesson_id="missing",
            current_user=_user(),
            content_service=FakeContentCatalogService(),
        )

    assert exc.value.status_code == 404
