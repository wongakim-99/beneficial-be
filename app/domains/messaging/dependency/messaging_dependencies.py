from app.domains.classroom.repository.classroom_repository import MongoClassroomRepository
from app.domains.classroom.service.classroom_service import ClassroomService
from app.domains.messaging.repository.message_repository import MongoMessageRepository
from app.domains.messaging.service.messaging_service import MessagingService
from app.infrastructure.db.mongo.mongo_client import get_mongo_client


def get_messaging_service() -> MessagingService:
    mongo_client = get_mongo_client()
    return MessagingService(
        repository=MongoMessageRepository(mongo_client),
        classroom_service=ClassroomService(MongoClassroomRepository(mongo_client)),
    )
