from fastapi import APIRouter, Depends, HTTPException

from app.domains.auth.dependency.auth_dependencies import get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.content.schema.catalog_schemas import (
    ContentUnitsResponse,
    LessonDetailResponse,
    LessonSummaryResponse,
    UnitSummaryResponse,
)
from app.domains.content.dependency.catalog_dependencies import get_content_catalog_service
from app.domains.content.service.catalog_service import ContentCatalogService

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/units", response_model=ContentUnitsResponse)
def get_content_units(
    current_user: User = Depends(get_current_user),
    content_service: ContentCatalogService = Depends(get_content_catalog_service),
) -> ContentUnitsResponse:
    units = []
    for unit, lessons in content_service.list_units_with_lessons():
        units.append(
            UnitSummaryResponse(
                unit_id=unit.unit_id,
                name=unit.name,
                order=unit.order,
                lessons=[
                    LessonSummaryResponse(
                        lesson_id=lesson.lesson_id,
                        unit_id=lesson.unit_id,
                        name=lesson.name,
                        order=lesson.order,
                        concept_keys=lesson.concept_keys,
                        stage_ids=lesson.stage_ids,
                    )
                    for lesson in lessons
                ],
            )
        )

    return ContentUnitsResponse(units=units, total_count=len(units))


@router.get("/lessons/{lesson_id}", response_model=LessonDetailResponse)
def get_content_lesson(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    content_service: ContentCatalogService = Depends(get_content_catalog_service),
) -> LessonDetailResponse:
    lesson = content_service.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="차시 정보를 찾을 수 없습니다")

    return LessonDetailResponse(
        lesson_id=lesson.lesson_id,
        unit_id=lesson.unit_id,
        name=lesson.name,
        order=lesson.order,
        concept_keys=lesson.concept_keys,
        stage_ids=lesson.stage_ids,
    )
