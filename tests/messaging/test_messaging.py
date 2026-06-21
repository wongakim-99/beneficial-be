from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.domains.auth.model.auth_models import User
from app.domains.messaging.controller.student_message_router import (
    list_my_messages,
    mark_message_read,
)
from app.domains.messaging.controller.teacher_message_router import (
    list_sent_messages,
    send_message,
)
from app.domains.messaging.schema.messaging_schemas import SendMessageRequest
from app.domains.messaging.service.messaging_service import MessagingService


def _user(user_id: str = "teacher_1", role: str = "teacher") -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id=user_id,
        email=f"{user_id}@example.com",
        password_hash="hash",
        display_name=user_id,
        role=role,
        created_at=now,
        updated_at=now,
    )


class FakeClassroomService:
    def __init__(self, allowed: bool = True):
        self.allowed = allowed

    def can_access_student(self, user, student_id):
        return self.allowed


class FakeMessageRepository:
    def __init__(self):
        self.messages = []

    def create(self, message):
        self.messages.append(message)
        return message["message_id"]

    def find_by_student(self, student_id, limit=50):
        items = [m for m in self.messages if m["student_id"] == student_id]
        items.sort(key=lambda m: m["created_at"], reverse=True)
        return items[:limit]

    def find_by_teacher_and_student(self, teacher_id, student_id, limit=50):
        items = [
            m
            for m in self.messages
            if m["teacher_id"] == teacher_id and m["student_id"] == student_id
        ]
        items.sort(key=lambda m: m["created_at"], reverse=True)
        return items[:limit]

    def mark_read(self, message_id, student_id, read_at):
        for m in self.messages:
            if m["message_id"] == message_id and m["student_id"] == student_id:
                m["read_at"] = read_at
                return True
        return False


def _service(allowed: bool = True) -> MessagingService:
    return MessagingService(FakeMessageRepository(), FakeClassroomService(allowed))


# ── 서비스 단위 테스트 ──────────────────────────────────────────────

def test_send_message_stores_for_owned_student():
    service = _service(allowed=True)

    message = service.send_message(_user(), "student_1", "오늘 정말 잘했어!")

    assert message is not None
    assert message.student_id == "student_1"
    assert message.read_at is None
    assert len(service.repository.messages) == 1


def test_send_message_blocked_for_non_owned_student():
    service = _service(allowed=False)

    message = service.send_message(_user(), "student_x", "안돼")

    assert message is None
    assert service.repository.messages == []


def test_mark_read_sets_read_at_and_unknown_returns_false():
    service = _service(allowed=True)
    sent = service.send_message(_user(), "student_1", "힘내")

    assert service.mark_read("student_1", sent.message_id) is True
    assert service.repository.messages[0]["read_at"] is not None
    assert service.mark_read("student_1", "missing") is False


# ── 라우터 테스트 ───────────────────────────────────────────────────

def test_send_message_endpoint_returns_unread_message():
    service = _service(allowed=True)

    response = send_message(
        student_id="student_1",
        body=SendMessageRequest(content="잘했어!"),
        current_user=_user(role="teacher"),
        messaging_service=service,
    )

    assert response.student_id == "student_1"
    assert response.is_read is False


def test_send_message_endpoint_blocks_non_owned_student():
    service = _service(allowed=False)

    with pytest.raises(HTTPException) as exc_info:
        send_message(
            student_id="student_x",
            body=SendMessageRequest(content="hi"),
            current_user=_user(role="teacher"),
            messaging_service=service,
        )

    assert exc_info.value.status_code == 403


def test_student_list_messages_counts_unread_then_marks_read():
    service = _service(allowed=True)
    teacher = _user("teacher_1", "teacher")
    service.send_message(teacher, "student_1", "메시지1")
    sent2 = service.send_message(teacher, "student_1", "메시지2")
    student = _user("student_1", "student")

    before = list_my_messages(limit=50, current_user=student, messaging_service=service)
    assert before.total_count == 2
    assert before.unread_count == 2

    mark_message_read(
        message_id=sent2.message_id,
        current_user=student,
        messaging_service=service,
    )

    after = list_my_messages(limit=50, current_user=student, messaging_service=service)
    assert after.unread_count == 1


def test_mark_message_read_missing_raises_404():
    service = _service(allowed=True)

    with pytest.raises(HTTPException) as exc_info:
        mark_message_read(
            message_id="nope",
            current_user=_user("student_1", "student"),
            messaging_service=service,
        )

    assert exc_info.value.status_code == 404


def test_teacher_list_sent_messages_blocks_non_owned():
    service = _service(allowed=False)

    with pytest.raises(HTTPException) as exc_info:
        list_sent_messages(
            student_id="student_x",
            limit=50,
            current_user=_user(role="teacher"),
            messaging_service=service,
        )

    assert exc_info.value.status_code == 403
