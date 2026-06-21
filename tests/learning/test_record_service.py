from datetime import datetime, timedelta, timezone

from app.domains.progress.service.learning_record_service import LearningRecordService
from app.domains.progress.util import build_problem_key, infer_lesson_id, resolve_concept_key


class FakeLearningRecordRepository:
    def __init__(self):
        self.records = []

    def create_record(self, record):
        self.records.append(record)
        return "record_1"

    def find_records_by_user(self, user_id):
        return [record for record in self.records if record["user_id"] == user_id]


class FakeClassroomRepository:
    def __init__(self, classrooms):
        self.classrooms = classrooms

    def find_classes_by_student(self, student_id):
        return [
            classroom
            for classroom in self.classrooms
            if student_id in classroom.get("student_ids", [])
        ]


def test_record_answer_stores_agent_readable_fields():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    record = service.record_answer(
        user_id="user_123",
        stage=3,
        question_id="stage3_problem_16",
        user_answer="되",
        correct_answer="돼",
        is_correct=False,
    )

    assert record.user_id == "user_123"
    assert record.concept_key == "되/돼"
    assert record.user_answer == "되"
    assert record.correct_answer == "돼"
    assert repository.records[0]["is_correct"] is False
    assert repository.records[0]["lesson_id"] == "lesson_4"
    assert repository.records[0]["unit_id"] == "unit_1"
    assert repository.records[0]["problem_key"] == "stage3:lesson_4:stage3_problem_16"
    assert repository.records[0]["attempt_no"] == 1
    assert repository.records[0]["source"] == "base"


def test_record_answer_denormalizes_class_id_from_classroom():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(
        repository,
        classroom_repository=FakeClassroomRepository(
            [
                {
                    "class_id": "class_1",
                    "student_ids": ["user_123"],
                }
            ]
        ),
    )

    service.record_answer(
        user_id="user_123",
        stage=2,
        question_id="stage2_problem_1",
        problem_id=1,
        user_answer="가르쳐",
        correct_answer="가르쳐",
        is_correct=True,
    )

    assert repository.records[0]["class_id"] == "class_1"


def test_record_answer_keeps_explicit_class_id_over_classroom_lookup():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(
        repository,
        classroom_repository=FakeClassroomRepository(
            [
                {
                    "class_id": "class_lookup",
                    "student_ids": ["user_123"],
                }
            ]
        ),
    )

    service.record_answer(
        user_id="user_123",
        class_id="class_explicit",
        stage=2,
        question_id="stage2_problem_1",
        problem_id=1,
        user_answer="가르쳐",
        correct_answer="가르쳐",
        is_correct=True,
    )

    assert repository.records[0]["class_id"] == "class_explicit"


def test_weakness_profile_groups_wrong_answers_by_concept():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)
    now = datetime.now(timezone.utc)
    repository.records.extend(
        [
            {
                "user_id": "user_123",
                "concept_key": "되/돼",
                "is_correct": False,
                "created_at": now - timedelta(days=1),
            },
            {
                "user_id": "user_123",
                "concept_key": "되/돼",
                "is_correct": False,
                "created_at": now,
            },
            {
                "user_id": "user_123",
                "concept_key": "맞추다/맞히다",
                "is_correct": False,
                "created_at": now,
            },
            {
                "user_id": "other_user",
                "concept_key": "되/돼",
                "is_correct": False,
                "created_at": now,
            },
        ]
    )

    profile = service.get_weakness_profile("user_123", min_wrong_count=2)

    assert profile.user_id == "user_123"
    assert len(profile.weak_concepts) == 1
    assert profile.weak_concepts[0].concept_key == "되/돼"
    assert profile.weak_concepts[0].wrong_count == 2


def test_class_weakness_summary_aggregates_across_students():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)
    now = datetime.now(timezone.utc)
    repository.records.extend(
        [
            # student_a: 되/돼 오답 2건
            {"user_id": "student_a", "concept_key": "되/돼", "is_correct": False, "created_at": now - timedelta(days=1)},
            {"user_id": "student_a", "concept_key": "되/돼", "is_correct": False, "created_at": now},
            # student_b: 되/돼 오답 1건 + 맞추다/맞히다 오답 1건 + 정답 1건
            {"user_id": "student_b", "concept_key": "되/돼", "is_correct": False, "created_at": now},
            {"user_id": "student_b", "concept_key": "맞추다/맞히다", "is_correct": False, "created_at": now},
            {"user_id": "student_b", "concept_key": "되/돼", "is_correct": True, "created_at": now},
        ]
    )

    # student_c는 기록이 없어 비활동 학생
    summary = service.get_class_weakness_summary(["student_a", "student_b", "student_c"])

    assert summary["student_count"] == 3
    assert summary["active_student_count"] == 2
    assert summary["participation_rate"] == 67  # round(2/3*100)
    assert summary["total_solved_count"] == 5
    assert summary["total_wrong_count"] == 4  # student_a 2 + student_b 2

    # 오답 합계 내림차순 정렬
    weak = summary["weak_concepts"]
    assert weak[0]["concept_key"] == "되/돼"
    assert weak[0]["wrong_count"] == 3  # student_a 2 + student_b 1
    assert weak[0]["student_count"] == 2  # 두 학생 모두 틀림
    assert weak[1]["concept_key"] == "맞추다/맞히다"
    assert weak[1]["wrong_count"] == 1
    assert weak[1]["student_count"] == 1


def test_class_weakness_summary_handles_empty_class():
    service = LearningRecordService(FakeLearningRecordRepository())

    summary = service.get_class_weakness_summary([])

    assert summary["student_count"] == 0
    assert summary["active_student_count"] == 0
    assert summary["participation_rate"] == 0
    assert summary["weak_concepts"] == []


def test_get_records_returns_user_records_as_models():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)
    service.record_answer(
        user_id="user_123",
        stage=3,
        question_id="stage3_problem_16",
        user_answer="되",
        correct_answer="돼",
        is_correct=False,
    )
    service.record_answer(
        user_id="other_user",
        stage=3,
        question_id="stage3_problem_17",
        user_answer="되고",
        correct_answer="되고",
        is_correct=True,
    )

    records = service.get_records("user_123")

    assert len(records) == 1
    assert records[0].user_id == "user_123"
    assert records[0].concept_key == "되/돼"


def test_resolve_concept_key_falls_back_to_answer():
    assert resolve_concept_key("돼") == "되/돼"
    assert resolve_concept_key("처음보는정답") == "처음보는정답"


def test_resolve_concept_key_handles_stage1_base_forms():
    # Stage 1 카드 쌍은 기본형(가르치다/가르키다 등)으로 노출되므로 매핑이 필요하다
    assert resolve_concept_key("가르치다") == "가르치다/가르키다"
    assert resolve_concept_key("가르키다") == "가르치다/가르키다"
    assert resolve_concept_key("되다") == "되/돼"  # Stage 2/3와 동일 concept_key
    assert resolve_concept_key("돼다") == "되/돼"
    assert resolve_concept_key("맞추다") == "맞추다/맞히다"
    assert resolve_concept_key("이따가") == "이따가/있다가"


def test_record_stage1_card_check_correct_saves_record():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    is_correct, concept_key = service.record_stage1_card_check(
        pair_id="pair_1",
        correct_word="가르치다",
        chosen_word="가르치다",
        user_id="user_123",
    )

    assert is_correct is True
    assert concept_key == "가르치다/가르키다"
    assert len(repository.records) == 1
    record = repository.records[0]
    assert record["stage"] == 1
    assert record["question_id"] == "stage1_pair_1"
    assert record["lesson_id"] == "lesson_1"
    assert record["problem_id"] == "pair_1"
    assert record["problem_key"] == "stage1:lesson_1:pair_1"
    assert record["is_correct"] is True
    assert record["concept_key"] == "가르치다/가르키다"


def test_record_stage1_card_check_wrong_saves_record():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    is_correct, concept_key = service.record_stage1_card_check(
        pair_id="pair_1",
        correct_word="가르치다",
        chosen_word="가르키다",
        user_id="user_123",
    )

    assert is_correct is False
    assert concept_key == "가르치다/가르키다"
    assert repository.records[0]["is_correct"] is False
    assert repository.records[0]["user_answer"] == "가르키다"


def test_record_stage1_card_check_anonymous_does_not_save():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    is_correct, concept_key = service.record_stage1_card_check(
        pair_id="pair_1",
        correct_word="가르치다",
        chosen_word="가르키다",
        user_id=None,
    )

    assert is_correct is False
    assert concept_key == "가르치다/가르키다"
    assert repository.records == []  # 비로그인은 저장 안 됨


def test_record_stage2_answer_correct_saves_record():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    is_correct, concept_key = service.record_stage2_answer(
        problem_id=1,
        correct_answer="가르쳐",
        user_answer="가르쳐",
        user_id="user_123",
    )

    assert is_correct is True
    assert concept_key == "가르치다/가르키다"
    record = repository.records[0]
    assert record["stage"] == 2
    assert record["question_id"] == "stage2_problem_1"
    assert record["lesson_id"] == "lesson_1"
    assert record["problem_id"] == 1
    assert record["problem_key"] == "stage2:lesson_1:1"
    assert record["is_correct"] is True


def test_record_answer_increments_attempt_no_per_problem_key():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    first = service.record_answer(
        user_id="user_123",
        stage=2,
        question_id="stage2_problem_1",
        problem_id=1,
        user_answer="가르켜",
        correct_answer="가르쳐",
        is_correct=False,
    )
    second = service.record_answer(
        user_id="user_123",
        stage=2,
        question_id="stage2_problem_1",
        problem_id=1,
        user_answer="가르쳐",
        correct_answer="가르쳐",
        is_correct=True,
    )

    assert first.attempt_no == 1
    assert second.attempt_no == 2


def test_learning_record_key_helpers_map_existing_content_ranges():
    assert infer_lesson_id(1, "pair_3") == "lesson_2"
    assert infer_lesson_id(2, 13) == "lesson_4"
    assert infer_lesson_id(3, 21) == "lesson_5"
    assert build_problem_key(2, "lesson_1", 1) == "stage2:lesson_1:1"


def test_record_stage2_answer_wrong_creates_weak_concept():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    service.record_stage2_answer(
        problem_id=13, correct_answer="되고", user_answer="돼고", user_id="user_123"
    )
    service.record_stage2_answer(
        problem_id=14, correct_answer="돼", user_answer="되", user_id="user_123"
    )

    profile = service.get_weakness_profile("user_123", min_wrong_count=2)
    assert len(profile.weak_concepts) == 1
    assert profile.weak_concepts[0].concept_key == "되/돼"
    assert profile.weak_concepts[0].wrong_count == 2


def test_record_stage2_answer_anonymous_does_not_save():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    is_correct, _ = service.record_stage2_answer(
        problem_id=1, correct_answer="가르쳐", user_answer="가르켜", user_id=None
    )

    assert is_correct is False
    assert repository.records == []


def test_stage1_and_stage2_share_same_concept_key():
    """Stage 1 기본형과 Stage 2 활용형이 같은 weak_concept으로 묶이는지 검증."""
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)

    service.record_stage1_card_check(
        pair_id="pair_1",
        correct_word="가르치다",
        chosen_word="가르키다",  # 오답
        user_id="user_123",
    )
    service.record_stage2_answer(
        problem_id=1,
        correct_answer="가르쳐",
        user_answer="가르켜",  # 오답
        user_id="user_123",
    )

    profile = service.get_weakness_profile("user_123", min_wrong_count=2)
    assert len(profile.weak_concepts) == 1
    # Stage 1, Stage 2 오답이 같은 concept_key 아래 집계됨
    assert profile.weak_concepts[0].concept_key == "가르치다/가르키다"
    assert profile.weak_concepts[0].wrong_count == 2


def test_student_progress_metrics_are_positive_only():
    repository = FakeLearningRecordRepository()
    service = LearningRecordService(repository)
    now = datetime.now(timezone.utc)
    repository.records.extend(
        [
            {
                "user_id": "user_123",
                "question_id": "stage2_problem_1",
                "is_correct": True,
                "created_at": now,
            },
            {
                "user_id": "user_123",
                "question_id": "stage2_problem_2",
                "is_correct": True,
                "created_at": now - timedelta(minutes=1),
            },
            {
                "user_id": "user_123",
                "question_id": "stage2_problem_3",
                "is_correct": False,
                "created_at": now - timedelta(minutes=2),
            },
        ]
    )

    metrics = service.get_student_progress_metrics("user_123")

    assert metrics == {
        "today_solved_count": 3,
        "total_solved_count": 3,
        "streak_correct_count": 2,
        "completed_question_count": 2,
    }
    assert "wrong_count" not in metrics
