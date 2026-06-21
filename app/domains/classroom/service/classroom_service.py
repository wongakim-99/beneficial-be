import secrets
from datetime import datetime, timezone

from app.domains.auth.model.auth_models import User
from app.domains.classroom.model.classroom_models import Classroom
from app.domains.classroom.repository.classroom_repository import ClassroomRepository


class ClassroomService:
    def __init__(self, repository: ClassroomRepository):
        self.repository = repository

    def create_class(self, name: str, teacher_id: str) -> Classroom:
        now = datetime.now(timezone.utc)
        class_doc = {
            "class_id": f"class_{secrets.token_urlsafe(12)}",
            "name": name.strip(),
            "teacher_id": teacher_id,
            "student_ids": [],
            "created_at": now,
            "updated_at": now,
        }
        self.repository.create_class(class_doc)
        return Classroom(**class_doc)

    def list_classes_for_user(self, user: User) -> list[Classroom]:
        if user.role == "developer":
            class_docs = self.repository.find_all_classes()
        else:
            class_docs = self.repository.find_classes_by_teacher(user.user_id)
        return [Classroom(**doc) for doc in class_docs]

    def get_class_for_user(self, class_id: str, user: User) -> Classroom | None:
        class_doc = self.repository.find_class_by_id(class_id)
        if not class_doc:
            return None

        classroom = Classroom(**class_doc)
        if user.role == "developer" or classroom.teacher_id == user.user_id:
            return classroom
        return None

    def list_students_for_class(self, class_id: str, user: User) -> list[dict]:
        classroom = self.get_class_for_user(class_id, user)
        if not classroom:
            return []

        users = self.repository.find_users_by_ids(classroom.student_ids)
        user_by_id = {student["user_id"]: student for student in users}
        return [
            user_by_id[student_id]
            for student_id in classroom.student_ids
            if student_id in user_by_id
        ]

    def can_access_student(self, user: User, student_id: str) -> bool:
        if user.role == "developer":
            return True

        classrooms = self.repository.find_classes_by_student(student_id)
        return any(classroom.get("teacher_id") == user.user_id for classroom in classrooms)

    def list_classes_for_student(self, student_id: str) -> list[Classroom]:
        class_docs = self.repository.find_classes_by_student(student_id)
        return [Classroom(**doc) for doc in class_docs]

    def get_my_class_info(self, student_id: str) -> dict | None:
        class_docs = self.repository.find_classes_by_student(student_id)
        if not class_docs:
            return None
        classroom = class_docs[0]
        teacher_doc = self.repository.find_user_by_id(classroom["teacher_id"])
        if not teacher_doc:
            return None
        return {
            "class_id": classroom["class_id"],
            "class_name": classroom["name"],
            "teacher_display_name": teacher_doc.get("display_name", ""),
            "teacher_school_name": teacher_doc.get("school_name"),
        }

    def search_students(self, query: str) -> list[dict]:
        return self.repository.search_students_by_query(query)

    def add_student_to_class(self, class_id: str, user: User, student_id: str) -> bool:
        classroom = self.get_class_for_user(class_id, user)
        if not classroom:
            return False
        return self.repository.add_student_to_class(class_id, student_id)

    def remove_student_from_class(self, class_id: str, user: User, student_id: str) -> bool:
        classroom = self.get_class_for_user(class_id, user)
        if not classroom:
            return False
        return self.repository.remove_student_from_class(class_id, student_id)
