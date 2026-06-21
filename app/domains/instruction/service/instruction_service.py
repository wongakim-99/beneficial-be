from typing import Protocol

from pydantic import BaseModel, Field

from app.common.security import utc_now
from app.domains.auth.model.auth_models import User
from app.domains.classroom.service.classroom_service import ClassroomService
from app.domains.instruction.model.instruction_models import (
    AssignmentStatus,
    GeneratedProblem,
    TeacherAssignment,
)
from app.domains.instruction.repository.assignment_repository import StageProblemLookup, TeacherAssignmentRepository
from app.domains.instruction.validation import (
    allowed_concept_keys,
    normalize_sentence,
    validate_generated_problem,
)


class InstructionError(ValueError):
    pass


class AssignmentNotFoundError(InstructionError):
    pass


class AssignmentAccessError(InstructionError):
    pass


class InvalidAssignmentTransitionError(InstructionError):
    pass


class ProblemValidationResult(BaseModel):
    problem: GeneratedProblem
    is_valid: bool
    reasons: list[str] = Field(default_factory=list)


class ProblemGenerator(Protocol):
    async def generate(
        self,
        concept_key: str,
        count: int,
        lesson_id: str,
        difficulty: str | None = None,
    ) -> list[GeneratedProblem]:
        ...


class InstructionService:
    def __init__(
        self,
        repository: TeacherAssignmentRepository,
        classroom_service: ClassroomService,
        stage_problem_lookup: StageProblemLookup | None = None,
    ):
        self.repository = repository
        self.classroom_service = classroom_service
        self.stage_problem_lookup = stage_problem_lookup

    def create_draft_assignment(
        self,
        teacher: User,
        target_type: str,
        lesson_id: str,
        concept_key: str,
        problems: list[GeneratedProblem],
        class_id: str | None = None,
        student_id: str | None = None,
        unit_id: str | None = None,
        stage: int = 3,
        generation_context: dict | None = None,
    ) -> TeacherAssignment:
        self._validate_target_access(
            teacher=teacher,
            target_type=target_type,
            class_id=class_id,
            student_id=student_id,
        )
        assignment = TeacherAssignment(
            teacher_id=teacher.user_id,
            target_type=target_type,
            class_id=class_id,
            student_id=student_id,
            unit_id=unit_id,
            lesson_id=lesson_id,
            stage=stage,
            concept_key=concept_key,
            problems=problems,
            generation_context=generation_context or {},
        )
        self.repository.create_assignment(assignment.model_dump())
        return assignment

    def list_assignments(
        self,
        teacher: User,
        status: str | None = None,
        class_id: str | None = None,
        student_id: str | None = None,
    ) -> list[TeacherAssignment]:
        docs = self.repository.find_assignments(
            teacher_id=teacher.user_id,
            status=status,
            class_id=class_id,
            student_id=student_id,
        )
        return [TeacherAssignment(**doc) for doc in docs]

    async def generate_problem_assignment(
        self,
        teacher: User,
        target_type: str,
        lesson_id: str,
        concept_key: str,
        count: int,
        problem_generator: ProblemGenerator,
        class_id: str | None = None,
        student_id: str | None = None,
        unit_id: str | None = None,
        stage: int = 3,
        difficulty: str | None = None,
        generation_context: dict | None = None,
    ) -> tuple[TeacherAssignment, list[ProblemValidationResult]]:
        if stage != 3:
            raise InstructionError("현재 AI 문제 생성은 Stage 3만 지원합니다.")
        if concept_key not in allowed_concept_keys():
            raise InstructionError("지원하지 않는 concept_key입니다.")

        self._validate_target_access(
            teacher=teacher,
            target_type=target_type,
            class_id=class_id,
            student_id=student_id,
        )
        candidates = await problem_generator.generate(
            concept_key=concept_key,
            count=count,
            lesson_id=lesson_id,
            difficulty=difficulty,
        )
        validation_results = self._validate_generated_problems(
            problems=candidates,
            concept_key=concept_key,
            lesson_id=lesson_id,
        )
        valid_problems = [
            result.problem
            for result in validation_results
            if result.is_valid
        ]
        if not valid_problems:
            raise InstructionError("검증을 통과한 생성 문제가 없습니다.")

        assignment = self.create_draft_assignment(
            teacher=teacher,
            target_type=target_type,
            class_id=class_id,
            student_id=student_id,
            unit_id=unit_id,
            lesson_id=lesson_id,
            stage=stage,
            concept_key=concept_key,
            problems=valid_problems,
            generation_context={
                **(generation_context or {}),
                "difficulty": difficulty or "normal",
                "requested_count": count,
                "generated_count": len(candidates),
                "valid_count": len(valid_problems),
            },
        )
        return assignment, validation_results

    def list_student_assignments(
        self,
        student_id: str,
        status: str = "assigned",
        lesson_id: str | None = None,
        stage: int | None = None,
    ) -> list[TeacherAssignment]:
        docs = self.repository.find_student_assignments(
            student_id=student_id,
            class_ids=self._class_ids_for_student(student_id),
            status=status,
            lesson_id=lesson_id,
            stage=stage,
        )
        return [TeacherAssignment(**doc) for doc in docs]

    def get_next_assigned_problem(
        self,
        student_id: str,
        lesson_id: str,
        stage: int = 3,
    ) -> dict | None:
        for assignment in self.list_student_assignments(
            student_id=student_id,
            lesson_id=lesson_id,
            stage=stage,
        ):
            completed = set(assignment.student_progress.get(student_id, []))
            for problem in assignment.problems:
                if str(problem.problem_id) in completed:
                    continue
                data = problem.model_dump()
                data.update(
                    {
                        "assignment_id": assignment.assignment_id,
                        "unit_id": assignment.unit_id,
                        "lesson_id": assignment.lesson_id,
                        "stage": assignment.stage,
                        "concept_key": assignment.concept_key,
                        "source": "assignment",
                        "badge": "선생님복습",
                    }
                )
                return data
        return None

    def submit_student_answer(
        self,
        student_id: str,
        assignment_id: str,
        problem_id: str,
        user_answer: str,
        learning_record_service=None,
    ) -> dict:
        assignment = self._get_for_student(student_id, assignment_id)
        if assignment.status != "assigned":
            raise InvalidAssignmentTransitionError("assigned 상태의 배정만 풀이할 수 있습니다.")

        problem = next(
            (
                candidate
                for candidate in assignment.problems
                if str(candidate.problem_id) == str(problem_id)
            ),
            None,
        )
        if problem is None:
            raise AssignmentNotFoundError("배정 문제를 찾을 수 없습니다.")

        is_correct = user_answer.strip() == problem.correct_answer.strip()
        completed_assignment = False
        if is_correct:
            completed_assignment = self._mark_problem_completed(
                assignment=assignment,
                student_id=student_id,
                problem_id=str(problem.problem_id),
            )

        if learning_record_service:
            learning_record_service.record_answer(
                user_id=student_id,
                stage=assignment.stage,
                question_id=problem.problem_key or f"assignment_{assignment.assignment_id}_{problem.problem_id}",
                class_id=assignment.class_id,
                unit_id=assignment.unit_id,
                lesson_id=assignment.lesson_id,
                problem_id=problem.problem_id,
                problem_key=problem.problem_key,
                concept_key=assignment.concept_key,
                user_answer=user_answer,
                correct_answer=problem.correct_answer,
                is_correct=is_correct,
                source="assignment",
                assignment_id=assignment.assignment_id,
            )

        return {
            "problem_id": problem.problem_id,
            "is_correct": is_correct,
            "user_answer": user_answer,
            "correct_answer": problem.correct_answer,
            "explanation": problem.explanation,
            "full_sentence": problem.full_sentence,
            "status": "completed" if completed_assignment else ("correct" if is_correct else "review"),
            "badge": "훌륭해요!" if is_correct else "재도전",
            "assignment_id": assignment.assignment_id,
            "source": "assignment",
        }

    def assign(self, teacher: User, assignment_id: str) -> TeacherAssignment:
        assignment = self._get_for_teacher(teacher, assignment_id)
        if assignment.status != "draft":
            raise InvalidAssignmentTransitionError("draft 상태의 배정만 assigned로 전환할 수 있습니다.")
        return self._transition(assignment, "assigned", {"assigned_at": utc_now()})

    def cancel(self, teacher: User, assignment_id: str) -> TeacherAssignment:
        assignment = self._get_for_teacher(teacher, assignment_id)
        if assignment.status not in {"draft", "assigned"}:
            raise InvalidAssignmentTransitionError("draft 또는 assigned 상태만 취소할 수 있습니다.")
        return self._transition(assignment, "cancelled", {"cancelled_at": utc_now()})

    def complete(self, teacher: User, assignment_id: str) -> TeacherAssignment:
        assignment = self._get_for_teacher(teacher, assignment_id)
        if assignment.status != "assigned":
            raise InvalidAssignmentTransitionError("assigned 상태만 완료할 수 있습니다.")
        return self._transition(assignment, "completed", {"completed_at": utc_now()})

    def _get_for_teacher(self, teacher: User, assignment_id: str) -> TeacherAssignment:
        doc = self.repository.find_assignment_by_id(assignment_id)
        if not doc:
            raise AssignmentNotFoundError("배정을 찾을 수 없습니다.")
        assignment = TeacherAssignment(**doc)
        if teacher.role != "developer" and assignment.teacher_id != teacher.user_id:
            raise AssignmentAccessError("본인이 만든 배정만 관리할 수 있습니다.")
        return assignment

    def _get_for_student(self, student_id: str, assignment_id: str) -> TeacherAssignment:
        doc = self.repository.find_assignment_by_id(assignment_id)
        if not doc:
            raise AssignmentNotFoundError("배정을 찾을 수 없습니다.")
        assignment = TeacherAssignment(**doc)
        if assignment.target_type == "student" and assignment.student_id == student_id:
            return assignment
        if (
            assignment.target_type == "class"
            and assignment.class_id in self._class_ids_for_student(student_id)
        ):
            return assignment
        raise AssignmentAccessError("본인에게 배정된 문제가 아닙니다.")

    def _transition(
        self,
        assignment: TeacherAssignment,
        status: AssignmentStatus,
        fields: dict,
    ) -> TeacherAssignment:
        update_fields = {"status": status, **fields}
        self.repository.update_assignment(assignment.assignment_id, update_fields)
        data = assignment.model_dump()
        data.update(update_fields)
        return TeacherAssignment(**data)

    def _validate_target_access(
        self,
        teacher: User,
        target_type: str,
        class_id: str | None,
        student_id: str | None,
    ) -> None:
        if target_type == "class":
            if not class_id:
                raise InstructionError("반 배정에는 class_id가 필요합니다.")
            if not self.classroom_service.get_class_for_user(class_id, teacher):
                raise AssignmentAccessError("담당 반에만 배정할 수 있습니다.")
            return

        if target_type == "student":
            if not student_id:
                raise InstructionError("학생 배정에는 student_id가 필요합니다.")
            if not self.classroom_service.can_access_student(teacher, student_id):
                raise AssignmentAccessError("담당 학생에게만 배정할 수 있습니다.")
            return

        raise InstructionError("target_type은 student 또는 class여야 합니다.")

    def _class_ids_for_student(self, student_id: str) -> list[str]:
        return [
            classroom.class_id
            for classroom in self.classroom_service.list_classes_for_student(student_id)
        ]

    def _mark_problem_completed(
        self,
        assignment: TeacherAssignment,
        student_id: str,
        problem_id: str,
    ) -> bool:
        progress = {
            user_id: list(problem_ids)
            for user_id, problem_ids in assignment.student_progress.items()
        }
        completed_problem_ids = progress.setdefault(student_id, [])
        if problem_id not in completed_problem_ids:
            completed_problem_ids.append(problem_id)

        all_problem_ids = {str(problem.problem_id) for problem in assignment.problems}
        student_completed_all = all_problem_ids.issubset(set(completed_problem_ids))
        update_fields = {"student_progress": progress}
        if student_completed_all and assignment.target_type == "student":
            update_fields.update({"status": "completed", "completed_at": utc_now()})

        self.repository.update_assignment(assignment.assignment_id, update_fields)
        return student_completed_all

    def _validate_generated_problems(
        self,
        problems: list[GeneratedProblem],
        concept_key: str,
        lesson_id: str,
    ) -> list[ProblemValidationResult]:
        existing_full_sentences = (
            self.stage_problem_lookup.find_stage3_full_sentences(lesson_id)
            if self.stage_problem_lookup
            else set()
        )
        seen_full_sentences: set[str] = set()
        results = []
        for problem in problems:
            reasons = validate_generated_problem(
                problem=problem,
                concept_key=concept_key,
                existing_full_sentences=existing_full_sentences,
                seen_full_sentences=seen_full_sentences,
            )
            problem.validation_status = "invalid" if reasons else "valid"
            if not reasons:
                seen_full_sentences.add(normalize_sentence(problem.full_sentence))
            results.append(
                ProblemValidationResult(
                    problem=problem,
                    is_valid=not reasons,
                    reasons=reasons,
                )
            )
        return results
