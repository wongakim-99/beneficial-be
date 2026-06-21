from datetime import datetime, timezone

from app.domains.auth.model.auth_models import User
from app.domains.classroom.service.classroom_service import ClassroomService


class FakeClassroomRepository:
    def __init__(self):
        self.classes = [
            {
                "class_id": "class_1",
                "name": "돌봄 1반",
                "teacher_id": "teacher_1",
                "student_ids": ["student_1", "student_2"],
            },
            {
                "class_id": "class_2",
                "name": "돌봄 2반",
                "teacher_id": "teacher_2",
                "student_ids": ["student_3"],
            },
        ]
        self.users = [
            {
                "user_id": "student_1",
                "email": "s1@example.com",
                "display_name": "학생1",
                "role": "student",
            },
            {
                "user_id": "student_2",
                "email": "s2@example.com",
                "display_name": "학생2",
                "role": "student",
            },
        ]

    def find_all_classes(self):
        return self.classes

    def find_classes_by_teacher(self, teacher_id):
        return [
            classroom
            for classroom in self.classes
            if classroom["teacher_id"] == teacher_id
        ]

    def find_class_by_id(self, class_id):
        return next(
            (
                classroom
                for classroom in self.classes
                if classroom["class_id"] == class_id
            ),
            None,
        )

    def find_classes_by_student(self, student_id):
        return [
            classroom
            for classroom in self.classes
            if student_id in classroom["student_ids"]
        ]

    def find_users_by_ids(self, user_ids):
        return [
            user
            for user in self.users
            if user["user_id"] in user_ids
        ]


def _user(user_id: str, role: str) -> User:
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


def test_teacher_sees_only_owned_classes():
    service = ClassroomService(FakeClassroomRepository())

    classes = service.list_classes_for_user(_user("teacher_1", "teacher"))

    assert [classroom.class_id for classroom in classes] == ["class_1"]


def test_developer_sees_all_classes():
    service = ClassroomService(FakeClassroomRepository())

    classes = service.list_classes_for_user(_user("dev_1", "developer"))

    assert [classroom.class_id for classroom in classes] == ["class_1", "class_2"]


def test_teacher_access_is_limited_to_own_students():
    service = ClassroomService(FakeClassroomRepository())
    teacher = _user("teacher_1", "teacher")

    assert service.can_access_student(teacher, "student_1") is True
    assert service.can_access_student(teacher, "student_3") is False


def test_list_students_preserves_class_order():
    service = ClassroomService(FakeClassroomRepository())

    students = service.list_students_for_class(
        "class_1",
        _user("teacher_1", "teacher"),
    )

    assert [student["user_id"] for student in students] == ["student_1", "student_2"]
