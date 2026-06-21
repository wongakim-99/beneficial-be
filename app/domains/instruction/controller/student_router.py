"""학생 관점의 Instruction 라우터.

router        : /student/learning/assignments  — 배정 과제 목록 조회
stage3_router : /student/learning/stage3       — 다음 문제 조회 / 답안 제출
                (content + instruction 오케스트레이션. instruction 계층에서 담당)
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.domains.auth.dependency.auth_dependencies import get_current_student
from app.domains.auth.model.auth_models import User
from app.domains.content.stage3.schemas import Stage3AnswerRequest, Stage3AnswerResponse
from app.domains.content.stage3.service import DEFAULT_STAGE3_LESSON_ID, get_stage3_service
from app.domains.instruction.dependency.instruction_dependencies import get_instruction_service
from app.domains.instruction.schema.instruction_schemas import (
    StudentAssignmentListResponse,
    StudentAssignmentProblemResponse,
    StudentAssignmentResponse,
)
from app.domains.instruction.service.instruction_service import InstructionService
from app.domains.progress.dependency.learning_record_dependencies import get_learning_record_service
from app.common.logging.logging_config import get_logger

logger = get_logger(__name__)

# 배정 과제 목록 조회
router = APIRouter(prefix="/student/learning/assignments", tags=["student-learning"])

# stage3 다음 문제 / 답안 제출 (content + instruction 오케스트레이션)
stage3_router = APIRouter(prefix="/student/learning/stage3", tags=["student-learning"])


@router.get("", response_model=StudentAssignmentListResponse)
def list_my_assignments(
    lesson_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_student),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> StudentAssignmentListResponse:
    """현재 학생에게 배정된 Stage 3 과제를 조회한다."""
    assignments = instruction_service.list_student_assignments(
        student_id=current_user.user_id,
        lesson_id=lesson_id,
        stage=3,
    )
    items = []
    for assignment in assignments:
        items.append(
            StudentAssignmentResponse(
                assignment_id=assignment.assignment_id,
                lesson_id=assignment.lesson_id,
                unit_id=assignment.unit_id,
                stage=assignment.stage,
                concept_key=assignment.concept_key,
                status=assignment.status,
                completed_problem_ids=assignment.student_progress.get(
                    current_user.user_id,
                    [],
                ),
                assigned_at=assignment.assigned_at,
                problems=[
                    StudentAssignmentProblemResponse(
                        problem_id=str(problem.problem_id),
                        problem_key=problem.problem_key,
                        type=problem.type,
                        sentence_part1=problem.sentence_part1,
                        sentence_part2=problem.sentence_part2,
                        visual_hint=problem.visual_hint,
                        accent_color=problem.accent_color,
                    )
                    for problem in assignment.problems
                ],
            )
        )
    return StudentAssignmentListResponse(assignments=items, total_count=len(items))


@stage3_router.get(
    "/next-problem",
    summary="다음 문제 조회",
    response_model=dict,
)
async def get_next_problem(
    lesson_id: str = DEFAULT_STAGE3_LESSON_ID,
    current_user: User = Depends(get_current_student),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> dict:
    """선생님 배정 문제를 우선 출제하고, 없으면 기본 Stage 3 문제를 출제한다."""
    try:
        problem = get_stage3_service(instruction_service=instruction_service).get_next_problem(
            user_id=current_user.user_id,
            lesson_id=lesson_id,
        )
        if not problem:
            return {"success": True, "message": "모든 문제를 완료했습니다!", "is_completed": True}
        return {
            "success": True,
            "problem": {
                "problem_id": problem["problem_id"],
                "sentence_part1": problem["sentence_part1"],
                "sentence_part2": problem["sentence_part2"],
                "visual_hint": problem.get("visual_hint"),
                "accent_color": problem.get("accent_color"),
                "badge": problem.get("badge"),
                "source": problem.get("source", "base"),
                "assignment_id": problem.get("assignment_id"),
            },
            "is_completed": False,
        }
    except Exception as e:
        logger.error(f"[ERROR] 3단계 다음 문제 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="다음 문제 조회에 실패했습니다")


@stage3_router.post(
    "/submit-answer",
    summary="답변 제출",
    response_model=Stage3AnswerResponse,
)
async def submit_stage3_answer(
    request: Stage3AnswerRequest,
    lesson_id: str | None = None,
    current_user: User = Depends(get_current_student),
    instruction_service: InstructionService = Depends(get_instruction_service),
) -> Stage3AnswerResponse:
    """기본 문제 또는 배정 문제 답안을 제출한다."""
    try:
        learning_svc = get_learning_record_service()
        return get_stage3_service(
            learning_record_service=learning_svc,
            instruction_service=instruction_service,
        ).submit_answer(
            request.problem_id,
            request.user_answer,
            user_id=current_user.user_id,
            lesson_id=lesson_id,
            assignment_id=request.assignment_id,
        )
    except Exception as e:
        logger.error(f"[ERROR] 3단계 답변 제출 실패: {e}")
        raise HTTPException(status_code=500, detail="답변 제출에 실패했습니다")
