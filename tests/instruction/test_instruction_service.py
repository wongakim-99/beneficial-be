from datetime import datetime, timezone

import pytest

from app.domains.auth.model.auth_models import User
from app.domains.classroom.model.classroom_models import Classroom
from app.domains.instruction.model.instruction_models import GeneratedProblem
from app.domains.instruction.service.instruction_service import (
    AssignmentAccessError,
    InstructionService,
    InvalidAssignmentTransitionError,
)


def _user(user_id="teacher_1", role="teacher") -> User:
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


def _problem() -> GeneratedProblem:
    return GeneratedProblem(
        problem_id="gen_1",
        sentence_part1="숙제가 다",
        correct_answer="됐어",
        sentence_part2="?",
        full_sentence="숙제가 다 됐어?",
        explanation="'됐어'는 '되었어'의 줄임말입니다.",
    )


class FakeAssignmentRepository:
    def __init__(self):
        self.assignments = []

    def create_assignment(self, assignment):
        self.assignments.append(dict(assignment))
        return "inserted"

    def find_assignment_by_id(self, assignment_id):
        return next(
            (
                assignment
                for assignment in self.assignments
                if assignment["assignment_id"] == assignment_id
            ),
            None,
        )

    def find_assignments(self, teacher_id, status=None, class_id=None, student_id=None):
        results = [
            assignment
            for assignment in self.assignments
            if assignment["teacher_id"] == teacher_id
        ]
        if status:
            results = [assignment for assignment in results if assignment["status"] == status]
        if class_id:
            results = [assignment for assignment in results if assignment.get("class_id") == class_id]
        if student_id:
            results = [assignment for assignment in results if assignment.get("student_id") == student_id]
        return results

    def find_student_assignments(
        self,
        student_id,
        class_ids,
        status="assigned",
        lesson_id=None,
        stage=None,
    ):
        results = [
            assignment
            for assignment in self.assignments
            if assignment["status"] == status
            and (
                (
                    assignment["target_type"] == "student"
                    and assignment.get("student_id") == student_id
                )
                or (
                    assignment["target_type"] == "class"
                    and assignment.get("class_id") in class_ids
                )
            )
        ]
        if lesson_id:
            results = [assignment for assignment in results if assignment["lesson_id"] == lesson_id]
        if stage is not None:
            results = [assignment for assignment in results if assignment["stage"] == stage]
        return results

    def update_assignment(self, assignment_id, fields):
        assignment = self.find_assignment_by_id(assignment_id)
        if not assignment:
            return False
        assignment.update(fields)
        return True


class FakeClassroomService:
    def __init__(self, allowed_classes=None, allowed_students=None):
        self.allowed_classes = set(allowed_classes or [])
        self.allowed_students = set(allowed_students or [])

    def get_class_for_user(self, class_id, user):
        if user.role == "developer" or class_id in self.allowed_classes:
            return {"class_id": class_id}
        return None

    def can_access_student(self, user, student_id):
        return user.role == "developer" or student_id in self.allowed_students

    def list_classes_for_student(self, student_id):
        if student_id not in self.allowed_students:
            return []
        return [
            Classroom(
                class_id=class_id,
                name=class_id,
                teacher_id="teacher_1",
                student_ids=[student_id],
            )
            for class_id in self.allowed_classes
        ]


def _service(repository=None, classroom_service=None):
    return InstructionService(
        repository or FakeAssignmentRepository(),
        classroom_service or FakeClassroomService(
            allowed_classes=["class_1"],
            allowed_students=["student_1"],
        ),
    )


class FakeProblemGenerator:
    def __init__(self, problems):
        self.problems = problems

    async def generate(self, concept_key, count, lesson_id, difficulty=None):
        return self.problems[:count]


class FakeStageProblemLookup:
    def __init__(self, existing_full_sentences=None):
        self.existing_full_sentences = set(existing_full_sentences or [])

    def find_stage3_full_sentences(self, lesson_id):
        return self.existing_full_sentences


def test_create_student_draft_assignment_sets_problem_keys():
    repository = FakeAssignmentRepository()
    service = _service(repository=repository)

    assignment = service.create_draft_assignment(
        teacher=_user(),
        target_type="student",
        student_id="student_1",
        lesson_id="lesson_4",
        concept_key="되/돼",
        problems=[_problem()],
    )

    assert assignment.status == "draft"
    assert assignment.student_id == "student_1"
    assert assignment.problems[0].problem_key == f"assignment:{assignment.assignment_id}:gen_1"
    assert repository.assignments[0]["assignment_id"] == assignment.assignment_id


def test_create_assignment_rejects_unowned_student():
    service = _service(classroom_service=FakeClassroomService(allowed_students=[]))

    with pytest.raises(AssignmentAccessError):
        service.create_draft_assignment(
            teacher=_user(),
            target_type="student",
            student_id="student_1",
            lesson_id="lesson_4",
            concept_key="되/돼",
            problems=[_problem()],
        )


def test_assignment_status_transitions():
    repository = FakeAssignmentRepository()
    service = _service(repository=repository)
    assignment = service.create_draft_assignment(
        teacher=_user(),
        target_type="class",
        class_id="class_1",
        lesson_id="lesson_4",
        concept_key="되/돼",
        problems=[_problem()],
    )

    assigned = service.assign(_user(), assignment.assignment_id)
    completed = service.complete(_user(), assignment.assignment_id)

    assert assigned.status == "assigned"
    assert assigned.assigned_at is not None
    assert completed.status == "completed"
    assert completed.completed_at is not None


def test_assignment_rejects_invalid_transition():
    service = _service()
    assignment = service.create_draft_assignment(
        teacher=_user(),
        target_type="class",
        class_id="class_1",
        lesson_id="lesson_4",
        concept_key="되/돼",
        problems=[_problem()],
    )

    with pytest.raises(InvalidAssignmentTransitionError):
        service.complete(_user(), assignment.assignment_id)


def test_list_assignments_filters_by_status():
    service = _service()
    assignment = service.create_draft_assignment(
        teacher=_user(),
        target_type="student",
        student_id="student_1",
        lesson_id="lesson_4",
        concept_key="되/돼",
        problems=[_problem()],
    )
    service.assign(_user(), assignment.assignment_id)

    assignments = service.list_assignments(_user(), status="assigned")

    assert len(assignments) == 1
    assert assignments[0].assignment_id == assignment.assignment_id


def test_get_next_assigned_problem_for_student_skips_completed_problems():
    service = _service()
    assignment = service.create_draft_assignment(
        teacher=_user(),
        target_type="student",
        student_id="student_1",
        lesson_id="lesson_4",
        concept_key="되/돼",
        problems=[
            _problem(),
            GeneratedProblem(
                problem_id="gen_2",
                sentence_part1="내일은 날씨가",
                correct_answer="좋대",
                sentence_part2=".",
                full_sentence="내일은 날씨가 좋대.",
                explanation="'좋대'는 들은 말을 전할 때 써요.",
            ),
        ],
    )
    service.assign(_user(), assignment.assignment_id)
    service.submit_student_answer(
        student_id="student_1",
        assignment_id=assignment.assignment_id,
        problem_id="gen_1",
        user_answer="됐어",
    )

    problem = service.get_next_assigned_problem("student_1", lesson_id="lesson_4")

    assert problem["problem_id"] == "gen_2"
    assert problem["assignment_id"] == assignment.assignment_id
    assert problem["source"] == "assignment"


def test_submit_student_assignment_answer_records_source_and_completes_assignment():
    class FakeLearningRecordService:
        def __init__(self):
            self.records = []

        def record_answer(self, **kwargs):
            self.records.append(kwargs)

    repository = FakeAssignmentRepository()
    service = _service(repository=repository)
    assignment = service.create_draft_assignment(
        teacher=_user(),
        target_type="student",
        student_id="student_1",
        lesson_id="lesson_4",
        concept_key="되/돼",
        problems=[_problem()],
    )
    service.assign(_user(), assignment.assignment_id)
    record_service = FakeLearningRecordService()

    result = service.submit_student_answer(
        student_id="student_1",
        assignment_id=assignment.assignment_id,
        problem_id="gen_1",
        user_answer="됐어",
        learning_record_service=record_service,
    )

    stored = repository.find_assignment_by_id(assignment.assignment_id)
    assert result["is_correct"] is True
    assert result["status"] == "completed"
    assert stored["status"] == "completed"
    assert stored["student_progress"]["student_1"] == ["gen_1"]
    assert record_service.records[0]["source"] == "assignment"
    assert record_service.records[0]["assignment_id"] == assignment.assignment_id
    assert record_service.records[0]["problem_key"] == assignment.problems[0].problem_key


@pytest.mark.asyncio
async def test_generate_problem_assignment_stores_valid_generated_problems_only():
    repository = FakeAssignmentRepository()
    service = InstructionService(
        repository,
        FakeClassroomService(allowed_students=["student_1"]),
        stage_problem_lookup=FakeStageProblemLookup(
            existing_full_sentences={"그렇게 하면 안 돼."}
        ),
    )

    assignment, validation_results = await service.generate_problem_assignment(
        teacher=_user(),
        target_type="student",
        student_id="student_1",
        lesson_id="lesson_4",
        concept_key="되/돼",
        count=2,
        difficulty="normal",
        problem_generator=FakeProblemGenerator(
            [
                GeneratedProblem(
                    problem_id="gen_valid",
                    sentence_part1="숙제가 다",
                    correct_answer="돼",
                    sentence_part2=".",
                    full_sentence="숙제가 다 돼.",
                    explanation="'돼'는 '되어'로 바꿀 수 있을 때 써요.",
                ),
                GeneratedProblem(
                    problem_id="gen_duplicate",
                    sentence_part1="그렇게 하면 안",
                    correct_answer="돼",
                    sentence_part2=".",
                    full_sentence="그렇게 하면 안 돼.",
                    explanation="중복 문제",
                ),
            ]
        ),
    )

    assert assignment.status == "draft"
    assert assignment.problems[0].problem_id == "gen_valid"
    assert repository.assignments[0]["problems"][0]["validation_status"] == "valid"
    assert len(validation_results) == 2
    assert validation_results[0].is_valid is True
    assert validation_results[1].is_valid is False
    assert "기존 기본 문제와 중복됩니다." in validation_results[1].reasons
