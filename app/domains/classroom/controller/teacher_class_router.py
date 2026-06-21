"""교사가 반과 반 소속 학생을 관리하는 Classroom 라우터.

경로 prefix: /teacher/classes
주 사용자: 교사, 개발자

student_view_router.py와 분리한 이유:
- 이 파일은 반(classroom) 리소스의 생성/목록/학생 배정 변경을 담당한다.
- student_view_router.py는 특정 학생의 학습 상태 조회만 담당한다.
- 같은 교사 권한 API라도 URL 기준 리소스가 classes와 students로 달라서 파일을 나눴다.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domains.auth.dependency.auth_dependencies import get_current_teacher
from app.domains.auth.model.auth_models import User
from app.domains.classroom.dependency.classroom_dependencies import get_classroom_service
from app.domains.classroom.service.classroom_service import ClassroomService
from app.domains.progress.dependency.learning_record_dependencies import get_learning_record_service
from app.domains.progress.service.learning_record_service import LearningRecordService
from app.domains.classroom.schema.classroom_schemas import (
    AddStudentRequest,
    ClassWeakConceptSummary,
    CreateClassRequest,
    TeacherClassesResponse,
    TeacherClassResponse,
    TeacherClassStudentsResponse,
    TeacherClassSummaryResponse,
    TeacherStudentSummaryResponse,
    UserSearchResponse,
    UserSearchResult,
)

# 교사 관점의 반 관리 API.
router = APIRouter(prefix="/teacher/classes", tags=["teacher"])


@router.post("", response_model=TeacherClassResponse, status_code=status.HTTP_201_CREATED)
def create_class(
    body: CreateClassRequest,
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
) -> TeacherClassResponse:
    """현재 교사 소유의 새 반을 생성한다."""
    classroom = classroom_service.create_class(name=body.name, teacher_id=current_user.user_id)
    return TeacherClassResponse(
        class_id=classroom.class_id,
        name=classroom.name,
        teacher_id=classroom.teacher_id,
        student_count=0,
    )


@router.get("", response_model=TeacherClassesResponse)
def list_my_classes(
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
) -> TeacherClassesResponse:
    """현재 교사가 담당하는 반 목록을 조회한다. 개발자는 전체 반을 조회한다."""
    classrooms = classroom_service.list_classes_for_user(current_user)
    items = [
        TeacherClassResponse(
            class_id=classroom.class_id,
            name=classroom.name,
            teacher_id=classroom.teacher_id,
            student_count=len(classroom.student_ids),
        )
        for classroom in classrooms
    ]
    return TeacherClassesResponse(classes=items, total_count=len(items))


@router.get("/{class_id}/students", response_model=TeacherClassStudentsResponse)
def list_class_students(
    class_id: str,
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
) -> TeacherClassStudentsResponse:
    """특정 반에 속한 학생 목록과 간단한 학습 요약을 조회한다."""
    classroom = classroom_service.get_class_for_user(class_id, current_user)
    if not classroom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="반을 찾을 수 없습니다.",
        )

    students = classroom_service.list_students_for_class(class_id, current_user)
    items = [
        _to_student_summary(student, learning_record_service)
        for student in students
    ]
    return TeacherClassStudentsResponse(
        class_id=class_id,
        students=items,
        total_count=len(items),
    )


@router.get("/{class_id}/summary", response_model=TeacherClassSummaryResponse)
def get_class_summary(
    class_id: str,
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
) -> TeacherClassSummaryResponse:
    """반 전체의 공통 약점과 참여 지표를 집계해 조회한다."""
    classroom = classroom_service.get_class_for_user(class_id, current_user)
    if not classroom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="반을 찾을 수 없습니다.",
        )

    summary = learning_record_service.get_class_weakness_summary(classroom.student_ids)
    return TeacherClassSummaryResponse(
        class_id=class_id,
        name=classroom.name,
        student_count=summary["student_count"],
        active_student_count=summary["active_student_count"],
        participation_rate=summary["participation_rate"],
        total_solved_count=summary["total_solved_count"],
        total_wrong_count=summary["total_wrong_count"],
        weak_concepts=[
            ClassWeakConceptSummary(**weak_concept)
            for weak_concept in summary["weak_concepts"]
        ],
    )


@router.get("/search-students", response_model=UserSearchResponse)
def search_students(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
) -> UserSearchResponse:
    """반에 추가할 학생을 이름 또는 이메일로 검색한다."""
    users = classroom_service.search_students(q)
    return UserSearchResponse(
        users=[UserSearchResult(user_id=u["user_id"], display_name=u["display_name"], email=u["email"]) for u in users]
    )


@router.post("/{class_id}/students", status_code=status.HTTP_204_NO_CONTENT)
def add_student_to_class(
    class_id: str,
    body: AddStudentRequest,
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
) -> None:
    """담당 반에 학생을 추가한다."""
    success = classroom_service.add_student_to_class(class_id, current_user, body.student_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="반을 찾을 수 없습니다.")


@router.delete("/{class_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_student_from_class(
    class_id: str,
    student_id: str,
    current_user: User = Depends(get_current_teacher),
    classroom_service: ClassroomService = Depends(get_classroom_service),
) -> None:
    """담당 반에서 학생을 제거한다."""
    classroom_service.remove_student_from_class(class_id, current_user, student_id)


def _to_student_summary(
    student: dict,
    learning_record_service: LearningRecordService,
) -> TeacherStudentSummaryResponse:
    """학생 목록 화면에 필요한 최근 활동과 약점 개념 요약을 만든다."""
    records = learning_record_service.get_records(student["user_id"])
    profile = learning_record_service.get_weakness_profile(
        student["user_id"],
        min_wrong_count=1,
    )
    return TeacherStudentSummaryResponse(
        user_id=student["user_id"],
        email=student.get("email", ""),
        display_name=student.get("display_name", ""),
        weak_concepts=[
            weak_concept.concept_key
            for weak_concept in profile.weak_concepts[:3]
        ],
        recent_activity_at=records[0].created_at if records else None,
    )
