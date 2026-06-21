"""학생이 본인에게 온 교사 메시지를 조회/읽음 처리하는 라우터.

경로 prefix: /student/me/messages
주 사용자: 학생
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domains.auth.dependency.auth_dependencies import get_current_student
from app.domains.auth.model.auth_models import User
from app.domains.messaging.dependency.messaging_dependencies import get_messaging_service
from app.domains.messaging.model.messaging_models import TeacherMessage
from app.domains.messaging.schema.messaging_schemas import (
    MessagesResponse,
    TeacherMessageResponse,
)
from app.domains.messaging.service.messaging_service import MessagingService

router = APIRouter(prefix="/student/me/messages", tags=["student"])


def _to_response(message: TeacherMessage) -> TeacherMessageResponse:
    return TeacherMessageResponse(
        message_id=message.message_id,
        teacher_id=message.teacher_id,
        student_id=message.student_id,
        content=message.content,
        created_at=message.created_at,
        read_at=message.read_at,
        is_read=message.read_at is not None,
    )


@router.get("", response_model=MessagesResponse)
def list_my_messages(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_student),
    messaging_service: MessagingService = Depends(get_messaging_service),
) -> MessagesResponse:
    """학생 본인에게 온 메시지를 시간 역순으로 조회한다."""
    messages = messaging_service.list_messages_for_student(current_user.user_id, limit)
    items = [_to_response(message) for message in messages]
    return MessagesResponse(
        messages=items,
        total_count=len(items),
        unread_count=sum(1 for item in items if not item.is_read),
    )


@router.patch("/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_message_read(
    message_id: str,
    current_user: User = Depends(get_current_student),
    messaging_service: MessagingService = Depends(get_messaging_service),
) -> None:
    """본인 메시지를 읽음 처리한다."""
    marked = messaging_service.mark_read(current_user.user_id, message_id)
    if not marked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="메시지를 찾을 수 없습니다.",
        )
