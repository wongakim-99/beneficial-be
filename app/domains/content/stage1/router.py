from fastapi import APIRouter, Depends, HTTPException

from app.common.logging.logging_config import get_logger
from app.domains.auth.dependency.auth_dependencies import get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.content.stage1.schemas import (
    Stage1CardsResponse,
    Stage1SubmitRequest,
    Stage1SubmitResponse,
)
from app.domains.content.stage1.service import stage1_pair_response
from app.domains.progress.dependency.learning_record_dependencies import get_learning_record_service
from app.domains.progress.service.learning_record_service import LearningRecordService
from app.infrastructure.db.mongo.mongo_client import get_mongo_client

router = APIRouter(prefix="/student/learning", tags=["student-learning"])
logger = get_logger(__name__)


@router.get(
    "/stage1/cards",
    summary="1단계 어휘학습 카드 조회",
    response_model=Stage1CardsResponse,
)
async def get_stage1_cards(
    current_user: User = Depends(get_current_user),
) -> Stage1CardsResponse:
    try:
        card_pairs = list(
            get_mongo_client().find_many("stage1_cards", {}, sort=[("order", 1)])
        )

        if not card_pairs:
            raise HTTPException(status_code=404, detail="카드 데이터를 찾을 수 없습니다")

        pairs_response = [stage1_pair_response(pair) for pair in card_pairs]
        logger.info(f"[OK] 1단계 카드 쌍 {len(pairs_response)}개 조회 완료")

        return Stage1CardsResponse(
            success=True,
            total_pairs=len(pairs_response),
            card_pairs=pairs_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] 1단계 카드 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="카드 조회에 실패했습니다")


@router.post(
    "/stage1/submit-card-check",
    summary="1단계 카드 확인 답안 제출",
    response_model=Stage1SubmitResponse,
)
async def submit_stage1_card_check(
    request: Stage1SubmitRequest,
    current_user: User = Depends(get_current_user),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
) -> Stage1SubmitResponse:
    try:
        pair = get_mongo_client().find_one("stage1_cards", {"pair_id": request.pair_id})
        if not pair:
            raise HTTPException(status_code=404, detail="카드 쌍을 찾을 수 없습니다")

        correct_word = pair["word1"]
        is_correct, concept_key = learning_record_service.record_stage1_card_check(
            pair_id=request.pair_id,
            correct_word=correct_word,
            chosen_word=request.chosen_word,
            user_id=current_user.user_id,
        )

        logger.info(
            f"[OK] 1단계 카드 답안 제출: pair={request.pair_id} "
            f"chosen={request.chosen_word} correct={is_correct}"
        )
        return Stage1SubmitResponse(
            pair_id=request.pair_id,
            is_correct=is_correct,
            chosen_word=request.chosen_word,
            correct_word=correct_word,
            concept_key=concept_key,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] 1단계 카드 답안 제출 실패: {e}")
        raise HTTPException(status_code=500, detail="카드 답안 제출에 실패했습니다")
