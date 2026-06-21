from fastapi import APIRouter, Depends, HTTPException

from app.common.logging.logging_config import get_logger
from app.domains.content.stage3.schemas import (
    Stage3ProblemsResponse,
    Stage3ProgressResponse,
)
from app.domains.auth.dependency.auth_dependencies import get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.content.stage3.service import (
    DEFAULT_STAGE3_LESSON_ID,
    get_stage3_service,
)

router = APIRouter(prefix="/student/learning/stage3", tags=["student-learning"])
logger = get_logger(__name__)


@router.get(
    "/problems",
    summary="3단계 문제 목록 조회",
    response_model=Stage3ProblemsResponse,
)
async def get_stage3_problems(
    lesson_id: str = DEFAULT_STAGE3_LESSON_ID,
    current_user: User = Depends(get_current_user),
) -> Stage3ProblemsResponse:
    try:
        return get_stage3_service().get_problems(lesson_id=lesson_id)
    except Exception as e:
        logger.error(f"[ERROR] 3단계 문제 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="3단계 문제 목록 조회에 실패했습니다")


@router.get(
    "/progress",
    summary="학습 진행도 조회",
    response_model=Stage3ProgressResponse,
)
async def get_stage3_progress(
    lesson_id: str = DEFAULT_STAGE3_LESSON_ID,
    current_user: User = Depends(get_current_user),
) -> Stage3ProgressResponse:
    try:
        return get_stage3_service().get_progress(
            user_id=current_user.user_id,
            lesson_id=lesson_id,
        )
    except Exception as e:
        logger.error(f"[ERROR] 3단계 진행도 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="진행도 조회에 실패했습니다")


@router.post(
    "/reset-progress",
    summary="진행도 초기화",
    response_model=dict,
)
async def reset_stage3_progress(
    lesson_id: str = DEFAULT_STAGE3_LESSON_ID,
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        get_stage3_service().reset_progress(
            user_id=current_user.user_id,
            lesson_id=lesson_id,
        )
        return {"success": True, "message": "진행도가 초기화되었습니다."}
    except Exception as e:
        logger.error(f"[ERROR] 3단계 진행도 초기화 실패: {e}")
        raise HTTPException(status_code=500, detail="진행도 초기화에 실패했습니다")
