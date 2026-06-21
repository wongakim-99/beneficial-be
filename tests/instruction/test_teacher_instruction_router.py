from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.domains.auth.model.auth_models import User
from app.domains.instruction.controller.teacher_router import (
    assign_assignment,
    create_assignment_draft,
    generate_problems,
)
from app.domains.instruction.model.instruction_models import GeneratedProblem
from app.domains.instruction.schema.instruction_schemas import (
    CreateAssignmentDraftRequest,
    GeneratedProblemRequest,
    GenerateProblemsRequest,
)
from app.domains.instruction.service.instruction_service import InstructionService
from tests.instruction.test_instruction_service import (
    FakeAssignmentRepository,
    FakeClassroomService,
    FakeProblemGenerator,
)


def _teacher() -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id="teacher_1",
        email="teacher@example.com",
        password_hash="hash",
        display_name="teacher",
        role="teacher",
        created_at=now,
        updated_at=now,
    )


def _body(student_id="student_1") -> CreateAssignmentDraftRequest:
    return CreateAssignmentDraftRequest(
        target_type="student",
        student_id=student_id,
        lesson_id="lesson_4",
        concept_key="되/돼",
        problems=[
            GeneratedProblemRequest(
                problem_id="gen_1",
                sentence_part1="숙제가 다",
                correct_answer="됐어",
                sentence_part2="?",
                full_sentence="숙제가 다 됐어?",
                explanation="설명",
            )
        ],
    )


def _service(repository=None, allowed_students=None) -> InstructionService:
    return InstructionService(
        repository or FakeAssignmentRepository(),
        FakeClassroomService(allowed_students=allowed_students or ["student_1"]),
    )


def test_create_assignment_draft_endpoint_maps_response():
    response = create_assignment_draft(
        body=_body(),
        current_user=_teacher(),
        instruction_service=_service(),
    )

    assert response.status == "draft"
    assert response.student_id == "student_1"
    assert response.problems[0].problem_key.endswith(":gen_1")


def test_create_assignment_draft_endpoint_rejects_forbidden_student():
    with pytest.raises(HTTPException) as exc_info:
        create_assignment_draft(
            body=_body(student_id="student_2"),
            current_user=_teacher(),
            instruction_service=_service(allowed_students=[]),
        )

    assert exc_info.value.status_code == 403


def test_assign_assignment_endpoint_transitions_status():
    repository = FakeAssignmentRepository()
    service = _service(repository=repository)
    created = create_assignment_draft(
        body=_body(),
        current_user=_teacher(),
        instruction_service=service,
    )

    response = assign_assignment(
        assignment_id=created.assignment_id,
        current_user=_teacher(),
        instruction_service=service,
    )

    assert response.status == "assigned"
    assert response.assigned_at is not None


@pytest.mark.asyncio
async def test_generate_problems_endpoint_creates_draft_assignment():
    response = await generate_problems(
        body=GenerateProblemsRequest(
            target_type="student",
            student_id="student_1",
            lesson_id="lesson_4",
            concept_key="되/돼",
            count=1,
        ),
        current_user=_teacher(),
        instruction_service=_service(),
        problem_generator=FakeProblemGenerator(
            [
                GeneratedProblem(
                    problem_id="gen_1",
                    sentence_part1="숙제가 다",
                    correct_answer="돼",
                    sentence_part2=".",
                    full_sentence="숙제가 다 돼.",
                    explanation="'돼'는 '되어'로 바꿀 수 있을 때 써요.",
                )
            ]
        ),
    )

    assert response.assignment is not None
    assert response.assignment.status == "draft"
    assert response.total_generated == 1
    assert response.total_valid == 1
