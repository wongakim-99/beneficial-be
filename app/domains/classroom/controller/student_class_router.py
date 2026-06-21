"""학생이 본인 소속 반 정보를 조회하는 Classroom 라우터.

경로 prefix: /student/my-class
주 사용자: 학생

교사용 반 관리 API와 분리한 이유:
- 학생은 본인이 속한 반의 요약 정보만 조회한다.
- 반 생성, 학생 추가/삭제, 다른 학생 기록 조회 권한은 없다.
"""
from fastapi import APIRouter, Depends

from app.domains.auth.dependency.auth_dependencies import get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.classroom.dependency.classroom_dependencies import get_classroom_service
from app.domains.classroom.schema.classroom_schemas import StudentMyClassResponse
from app.domains.classroom.service.classroom_service import ClassroomService

# 학생 관점의 "내 반" 단일 리소스.
router = APIRouter(prefix="/student/my-class", tags=["student"])


@router.get("", response_model=StudentMyClassResponse | None)
def get_my_class(
    current_user: User = Depends(get_current_user),
    classroom_service: ClassroomService = Depends(get_classroom_service),
) -> StudentMyClassResponse | None:
    """현재 로그인한 학생이 속한 반과 담당 교사 정보를 반환한다."""
    info = classroom_service.get_my_class_info(current_user.user_id)
    if not info:
        return None
    return StudentMyClassResponse(**info)
