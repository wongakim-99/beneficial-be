"""교사가 담당 학생에게 메시지를 보내고 조회하는 라우터.

경로 prefix: /teacher/students/{student_id}/messages
주 사용자: 교사, 개발자
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domains.auth.dependency.auth_dependencies import get_current_teacher
from app.domains.auth.model.auth_models import User
from app.domains.messaging.dependency.messaging_dependencies import get_messaging_service
from app.domains.messaging.model.messaging_models import TeacherMessage
from app.domains.messaging.schema.messaging_schemas import (
    MessagesResponse,
    SendMessageRequest,
    TeacherMessageResponse,
)
from app.domains.messaging.service.messaging_service import MessagingService

router = APIRouter(prefix="/teacher/students/{student_id}/messages", tags=["teacher"])


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


@router.post("", response_model=TeacherMessageResponse, status_code=status.HTTP_201_CREATED)
def send_message(
    student_id: str,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_teacher),
    messaging_service: MessagingService = Depends(get_messaging_service),
) -> TeacherMessageResponse:
    """담당 학생에게 메시지를 보낸다."""
    message = messaging_service.send_message(current_user, student_id, body.content)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="담당 학생이 아닙니다.",
        )
    return _to_response(message)


@router.get("", response_model=MessagesResponse)
def list_sent_messages(
    student_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_teacher),
    messaging_service: MessagingService = Depends(get_messaging_service),
) -> MessagesResponse:
    """교사가 해당 학생에게 보낸 메시지 목록을 조회한다."""
    messages = messaging_service.list_messages_for_teacher(current_user, student_id, limit)
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="담당 학생이 아닙니다.",
        )
    items = [_to_response(message) for message in messages]
    return MessagesResponse(
        messages=items,
        total_count=len(items),
        unread_count=sum(1 for item in items if not item.is_read),
    )
