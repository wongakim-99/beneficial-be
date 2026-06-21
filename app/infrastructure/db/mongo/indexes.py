from app.common.logging.logging_config import get_logger
from app.infrastructure.db.mongo.mongo_client import MongoClient

logger = get_logger(__name__)

MONGO_INDEXES = [
    {
        "collection": "learning_records",
        "keys": [("user_id", 1), ("created_at", -1)],
        "name": "idx_learning_records_user_created_at",
    },
    {
        "collection": "learning_records",
        "keys": [("user_id", 1), ("concept_key", 1), ("is_correct", 1)],
        "name": "idx_learning_records_user_concept_correct",
    },
    {
        "collection": "learning_records",
        "keys": [("user_id", 1), ("problem_key", 1)],
        "name": "idx_learning_records_user_problem_key",
    },
    {
        "collection": "stage3_progress",
        "keys": [("user_id", 1), ("lesson_id", 1)],
        "name": "idx_stage3_progress_user_lesson_unique",
        "unique": True,
        "partial_filter_expression": {"lesson_id": {"$exists": True}},
    },
    {
        "collection": "teacher_assignments",
        "keys": [("student_id", 1), ("status", 1)],
        "name": "idx_teacher_assignments_student_status",
    },
    {
        "collection": "teacher_assignments",
        "keys": [("class_id", 1), ("status", 1)],
        "name": "idx_teacher_assignments_class_status",
    },
    {
        "collection": "teacher_assignments",
        "keys": [("teacher_id", 1), ("created_at", -1)],
        "name": "idx_teacher_assignments_teacher_created_at",
    },
    {
        "collection": "agent_call_logs",
        "keys": [("created_at", -1)],
        "name": "idx_agent_call_logs_created_at",
    },
    {
        "collection": "agent_call_logs",
        "keys": [("user_id", 1), ("created_at", -1)],
        "name": "idx_agent_call_logs_user_created_at",
    },
]


def ensure_mongo_indexes(mongo_client: MongoClient) -> list[str]:
    created_indexes = []
    for spec in MONGO_INDEXES:
        index_name = mongo_client.create_index(
            collection_name=spec["collection"],
            keys=spec["keys"],
            unique=spec.get("unique", False),
            name=spec["name"],
            partial_filter_expression=spec.get("partial_filter_expression"),
        )
        created_indexes.append(index_name)
    logger.info("[OK] MongoDB 인덱스 확인 완료: %s", ", ".join(created_indexes))
    return created_indexes
