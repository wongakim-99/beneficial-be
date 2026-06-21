from typing import Optional

from app.common.security import utc_now
from app.domains.auth.model.auth_models import User
from app.domains.classroom.service.classroom_service import ClassroomService
from app.domains.messaging.model.messaging_models import TeacherMessage
from app.domains.messaging.repository.message_repository import MessageRepository


class MessagingService:
    """교사 → 학생 메시지 전송/조회.

    교사 권한 검증은 classroom 도메인의 담당 학생 확인을 재사용한다.
    """

    def __init__(
        self,
        repository: MessageRepository,
        classroom_service: ClassroomService,
    ):
        self.repository = repository
        self.classroom_service = classroom_service

    def send_message(
        self, teacher: User, student_id: str, content: str
    ) -> Optional[TeacherMessage]:
        """담당 학생에게만 메시지를 보낸다. 권한 없으면 None."""
        if not self.classroom_service.can_access_student(teacher, student_id):
            return None
        message = TeacherMessage(
            teacher_id=teacher.user_id,
            student_id=student_id,
            content=content,
        )
        self.repository.create(message.model_dump())
        return message

    def list_messages_for_teacher(
        self, teacher: User, student_id: str, limit: int = 50
    ) -> Optional[list[TeacherMessage]]:
        """교사가 해당 학생에게 보낸 메시지 목록. 권한 없으면 None."""
        if not self.classroom_service.can_access_student(teacher, student_id):
            return None
        docs = self.repository.find_by_teacher_and_student(
            teacher.user_id, student_id, limit
        )
        return [TeacherMessage(**doc) for doc in docs]

    def list_messages_for_student(
        self, student_id: str, limit: int = 50
    ) -> list[TeacherMessage]:
        """학생 본인에게 온 메시지 목록(시간 역순)."""
        docs = self.repository.find_by_student(student_id, limit)
        return [TeacherMessage(**doc) for doc in docs]

    def mark_read(self, student_id: str, message_id: str) -> bool:
        """학생 본인 메시지를 읽음 처리한다. 대상이 없으면 False."""
        return self.repository.mark_read(message_id, student_id, utc_now())
