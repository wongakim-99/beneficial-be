from fastapi import APIRouter, Depends

from app.domains.auth.dependency.auth_dependencies import get_current_student
from app.domains.auth.dependency.auth_dependencies import get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.content.dependency.catalog_dependencies import get_content_catalog_service
from app.domains.content.service.catalog_service import ContentCatalogService
from app.domains.progress.dependency.learning_record_dependencies import get_learning_record_service
from app.domains.progress.schema.learning_record_schemas import (
    LearningRecordResponse,
    LearningRecordsResponse,
    StudentProgressResponse,
)
from app.domains.progress.service.learning_record_service import LearningRecordService

router = APIRouter(tags=["student"])


@router.get("/student/me/progress", response_model=StudentProgressResponse)
def get_my_progress(
    current_user: User = Depends(get_current_student),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
    content_service: ContentCatalogService = Depends(get_content_catalog_service),
) -> StudentProgressResponse:
    metrics = learning_record_service.get_student_progress_metrics(current_user.user_id)
    units_with_lessons = content_service.list_units_with_lessons()
    progress_rate = learning_record_service.calculate_progress_rate(
        current_user.user_id, units_with_lessons
    )
    return StudentProgressResponse(
        **metrics,
        progress_rate=progress_rate,
        badges=learning_record_service.build_progress_badges(metrics, progress_rate),
    )


@router.get("/student/learning/records/me", response_model=LearningRecordsResponse)
def get_my_learning_records(
    current_user: User = Depends(get_current_user),
    learning_record_service: LearningRecordService = Depends(get_learning_record_service),
):
    records = learning_record_service.get_records(current_user.user_id)
    response_records = [
        LearningRecordResponse(**record.model_dump())
        for record in records
    ]
    return LearningRecordsResponse(
        records=response_records,
        total_count=len(response_records),
    )
