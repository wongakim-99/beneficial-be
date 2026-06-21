from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domains.auth.dependency.auth_dependencies import get_current_teacher
from app.domains.auth.model.auth_models import User
from app.domains.instruction.dependency.instruction_dependencies import get_instruction_service, get_problem_generator
from app.domains.instruction.service.generation import OpenAIProblemGenerator
from app.domains.instruction.model.instruction_models import GeneratedProblem
from app.domains.instruction.schema.instruction_schemas import (
    AssignmentListResponse,
    AssignmentResponse,
    CreateAssignmentDraftRequest,
    GenerateProblemsRequest,
    GenerateProblemsResponse,
    ProblemValidationResponse,
)
from app.domains.instruction.service.instruction_service import (
    AssignmentAccessError,
    AssignmentNotFoundError,
    InstructionError,
    InstructionService,
    InvalidAssignmentTransitionError,
)

router = APIRouter(prefix="/teacher/instruction", tags=["teacher"])


@router.post("/assignments/draft", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment_draft(
    body: CreateAssignmentDraftRequest,
    current_user: User = Depends(get_current_teacher),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> AssignmentResponse:
    try:
        assignment = instruction_service.create_draft_assignment(
            teacher=current_user,
            target_type=body.target_type,
            class_id=body.class_id,
            student_id=body.student_id,
            unit_id=body.unit_id,
            lesson_id=body.lesson_id,
            stage=body.stage,
            concept_key=body.concept_key,
            problems=[
                GeneratedProblem(**problem.model_dump(exclude_none=True))
                for problem in body.problems
            ],
            generation_context=body.generation_context,
        )
        return AssignmentResponse(**assignment.model_dump())
    except AssignmentAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except InstructionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/assignments", response_model=AssignmentListResponse)
def list_assignments(
    status_filter: str | None = Query(default=None, alias="status"),
    class_id: str | None = Query(default=None),
    student_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_teacher),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> AssignmentListResponse:
    assignments = instruction_service.list_assignments(
        teacher=current_user,
        status=status_filter,
        class_id=class_id,
        student_id=student_id,
    )
    items = [
        AssignmentResponse(**assignment.model_dump())
        for assignment in assignments
    ]
    return AssignmentListResponse(assignments=items, total_count=len(items))


@router.post("/generate-problems", response_model=GenerateProblemsResponse, status_code=status.HTTP_201_CREATED)
async def generate_problems(
    body: GenerateProblemsRequest,
    current_user: User = Depends(get_current_teacher),
    instruction_service: InstructionService = Depends(get_instruction_service),
    problem_generator: OpenAIProblemGenerator = Depends(get_problem_generator),
) -> GenerateProblemsResponse:
    try:
        assignment, validation_results = await instruction_service.generate_problem_assignment(
            teacher=current_user,
            target_type=body.target_type,
            class_id=body.class_id,
            student_id=body.student_id,
            unit_id=body.unit_id,
            lesson_id=body.lesson_id,
            stage=body.stage,
            concept_key=body.concept_key,
            count=body.count,
            difficulty=body.difficulty,
            generation_context=body.generation_context,
            problem_generator=problem_generator,
        )
        return GenerateProblemsResponse(
            assignment=AssignmentResponse(**assignment.model_dump()),
            validation_results=[
                ProblemValidationResponse(
                    problem=result.problem.model_dump(),
                    is_valid=result.is_valid,
                    reasons=result.reasons,
                )
                for result in validation_results
            ],
            total_generated=len(validation_results),
            total_valid=sum(1 for result in validation_results if result.is_valid),
        )
    except AssignmentAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except InstructionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/assignments/{assignment_id}/assign", response_model=AssignmentResponse)
def assign_assignment(
    assignment_id: str,
    current_user: User = Depends(get_current_teacher),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> AssignmentResponse:
    return _transition_assignment(
        lambda: instruction_service.assign(current_user, assignment_id)
    )


@router.patch("/assignments/{assignment_id}/cancel", response_model=AssignmentResponse)
def cancel_assignment(
    assignment_id: str,
    current_user: User = Depends(get_current_teacher),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> AssignmentResponse:
    return _transition_assignment(
        lambda: instruction_service.cancel(current_user, assignment_id)
    )


@router.patch("/assignments/{assignment_id}/complete", response_model=AssignmentResponse)
def complete_assignment(
    assignment_id: str,
    current_user: User = Depends(get_current_teacher),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> AssignmentResponse:
    return _transition_assignment(
        lambda: instruction_service.complete(current_user, assignment_id)
    )


def _transition_assignment(operation) -> AssignmentResponse:
    try:
        assignment = operation()
        return AssignmentResponse(**assignment.model_dump())
    except AssignmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AssignmentAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except InvalidAssignmentTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
