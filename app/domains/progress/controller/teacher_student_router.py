"""교사가 담당 학생의 학습 상태를 조회하는 라우터.

경로 prefix: /teacher/students
주 사용자: 교사, 개발자

progress 도메인에 위치한 이유:
- 학생의 약점 프로필과 학습 기록 조회는 progress 도메인의 책임이다.
- 교사 권한 확인은 classroom 서비스에 위임하고, 데이터는 progress 서비스에서 가져온다.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domains.auth.dependency.auth_dependencies import get_current_teacher
from app.domains.auth.model.auth_models import User
from app.domains.classroom.dependency.classroom_dependencies import get_classroom_service
from app.domains.classroom.service.classroom_service import ClassroomService
from app.domains.progress.dependency.learning_record_dependencies import get_learning_record_service
from app.domains.progress.schema.learning_record_schemas import (
    LearningRecordResponse,
    LearningRecordsResponse,
    StudentWeaknessProfileResponse,
    WeakConceptResponse,
)
from app.domains.progress.service.learning_record_service import LearningRecordService

router = APIRouter(prefix="/teacher/students", tags=["teacher"])


@router.get("/{user_id}/profile", response_model=StudentWeaknessProfileResponse)
def get_student_profile(
    user_id: str,
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
) -> StudentWeaknessProfileResponse:
    """담당 학생의 약점 개념 프로필을 조회한다."""
    _ensure_student_access(classroom_service, current_user, user_id)
    profile = learning_record_service.get_weakness_profile(user_id)
    return StudentWeaknessProfileResponse(
        user_id=profile.user_id,
        weak_concepts=[
            WeakConceptResponse(**weak_concept.model_dump())
            for weak_concept in profile.weak_concepts
        ],
    )


@router.get("/{user_id}/records", response_model=LearningRecordsResponse)
def get_student_records(
    user_id: str,
    stage: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
) -> LearningRecordsResponse:
    """담당 학생의 학습 기록을 조회한다. stage 파라미터로 단계별 필터링할 수 있다."""
    _ensure_student_access(classroom_service, current_user, user_id)
    records = learning_record_service.get_records(user_id)
    if stage is not None:
        records = [record for record in records if record.stage == stage]
    records = records[:limit]

    response_records = [
        LearningRecordResponse(**record.model_dump())
        for record in records
    ]
    return LearningRecordsResponse(
        records=response_records,
        total_count=len(response_records),
    )


def _ensure_student_access(
    classroom_service: ClassroomService,
    current_user: User,
    student_id: str,
) -> None:
    """교사가 담당하지 않는 학생의 데이터에 접근하지 못하게 막는다."""
    if not classroom_service.can_access_student(current_user, student_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="담당 학생 데이터만 조회할 수 있습니다.",
        )
