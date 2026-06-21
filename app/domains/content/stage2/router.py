from fastapi import APIRouter, Depends, HTTPException

from app.common.logging.logging_config import get_logger
from app.domains.auth.dependency.auth_dependencies import get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.auth.whitelist import is_answer_bypass_email
from app.domains.content.stage2.schemas import (
    Stage2ProblemResponse,
    Stage2ProblemsResponse,
    Stage2SubmitRequest,
    Stage2SubmitResponse,
)
from app.domains.content.stage2.service import (
    DEFAULT_STAGE2_LESSON_ID,
    find_stage2_lesson_data,
    find_stage2_problem_data,
)
from app.domains.progress.dependency.learning_record_dependencies import get_learning_record_service
from app.domains.progress.service.learning_record_service import LearningRecordService
from app.infrastructure.db.mongo.mongo_client import get_mongo_client

router = APIRouter(prefix="/student/learning", tags=["student-learning"])
logger = get_logger(__name__)


@router.get(
    "/stage2/problems",
    summary="2단계 예제풀이 문제 조회",
    response_model=Stage2ProblemsResponse,
)
async def get_stage2_problems(
    lesson_id: str = DEFAULT_STAGE2_LESSON_ID,
    current_user: User = Depends(get_current_user),
) -> Stage2ProblemsResponse:
    try:
        stage2_data = find_stage2_lesson_data(get_mongo_client(), lesson_id)

        if not stage2_data:
            raise HTTPException(status_code=404, detail="2단계 문제 데이터를 찾을 수 없습니다")

        problems = [
            Stage2ProblemResponse(
                problem_id=p["problem_id"],
                sentence_part1=p["sentence_part1"],
                sentence_part2=p["sentence_part2"],
            )
            for p in stage2_data["problems"]
        ]

        logger.info(f"[OK] 2단계 문제 {stage2_data['total_problems']}개 조회 완료")

        return Stage2ProblemsResponse(
            lesson_id=stage2_data["lesson_id"],
            title=stage2_data["title"],
            instruction=stage2_data["instruction"],
            total_problems=stage2_data["total_problems"],
            answer_options=stage2_data["answer_options"],
            problems=problems,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] 2단계 문제 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="2단계 문제 조회에 실패했습니다")


@router.post(
    "/stage2/submit-answer",
    summary="2단계 문제 답안 제출",
    response_model=Stage2SubmitResponse,
)
async def submit_stage2_answer(
    request: Stage2SubmitRequest,
    lesson_id: str = DEFAULT_STAGE2_LESSON_ID,
    current_user: User = Depends(get_current_user),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
) -> Stage2SubmitResponse:
    try:
        stage2_data = find_stage2_problem_data(
            get_mongo_client(),
            problem_id=request.problem_id,
            lesson_id=lesson_id,
        )
        if not stage2_data:
            raise HTTPException(status_code=404, detail="2단계 문제 데이터를 찾을 수 없습니다")

        problem = next(
            (p for p in stage2_data["problems"] if p["problem_id"] == request.problem_id),
            None,
        )
        if not problem:
            raise HTTPException(
                status_code=404, detail=f"문제 ID {request.problem_id}를 찾을 수 없습니다"
            )

        correct_answer = problem["correct_answer"]
        is_correct, concept_key = learning_record_service.record_stage2_answer(
            problem_id=request.problem_id,
            correct_answer=correct_answer,
            user_answer=request.user_answer,
            user_id=current_user.user_id,
        )
        answer_bypass_enabled = is_answer_bypass_email(current_user.email)

        logger.info(
            f"[OK] 2단계 답안 제출: problem={request.problem_id} "
            f"answer={request.user_answer} correct={is_correct}"
        )
        return Stage2SubmitResponse(
            problem_id=request.problem_id,
            is_correct=is_correct,
            user_answer=request.user_answer,
            correct_answer=correct_answer,
            full_sentence=problem["full_sentence"],
            concept_key=concept_key,
            is_answer_bypass_enabled=answer_bypass_enabled,
            is_admin=answer_bypass_enabled,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] 2단계 답안 제출 실패: {e}")
        raise HTTPException(status_code=500, detail="2단계 답안 제출에 실패했습니다")
