from datetime import datetime
from typing import Any, Dict, List, Protocol

from app.infrastructure.db.mongo.mongo_client import MongoClient


class MessageRepository(Protocol):
    def create(self, message: Dict[str, Any]) -> str:
        ...

    def find_by_student(self, student_id: str, limit: int) -> List[Dict[str, Any]]:
        ...

    def find_by_teacher_and_student(
        self, teacher_id: str, student_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        ...

    def mark_read(self, message_id: str, student_id: str, read_at: datetime) -> bool:
        ...


class MongoMessageRepository:
    collection_name = "teacher_messages"

    def __init__(self, mongo_client: MongoClient):
        self.mongo_client = mongo_client

    def create(self, message: Dict[str, Any]) -> str:
        return self.mongo_client.insert_one(self.collection_name, message)

    def find_by_student(self, student_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.mongo_client.find_many(
            self.collection_name,
            {"student_id": student_id},
            limit=limit,
            sort=[("created_at", -1)],
        )

    def find_by_teacher_and_student(
        self, teacher_id: str, student_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        return self.mongo_client.find_many(
            self.collection_name,
            {"teacher_id": teacher_id, "student_id": student_id},
            limit=limit,
            sort=[("created_at", -1)],
        )

    def mark_read(self, message_id: str, student_id: str, read_at: datetime) -> bool:
        # 학생 본인에게 온 메시지만 읽음 처리한다.
        return self.mongo_client.update_one(
            self.collection_name,
            {"message_id": message_id, "student_id": student_id},
            {"read_at": read_at},
        )
