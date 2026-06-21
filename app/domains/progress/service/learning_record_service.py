from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional

from app.common.security import utc_now
from app.domains.progress.model.progress_models import (
    LearningRecord,
    StudentWeaknessProfile,
    WeakConcept,
)
from app.domains.progress.repository.learning_record_repository import LearningClassroomRepository, LearningRecordRepository
from app.domains.progress.util import (
    _calculate_priority,
    _record_created_at,
    build_problem_key,
    infer_lesson_id,
    resolve_concept_key,
)


class LearningRecordService:
    def __init__(
        self,
        repository: LearningRecordRepository,
        classroom_repository: "LearningClassroomRepository | None" = None,
    ):
        self.repository = repository
        self.classroom_repository = classroom_repository

    def record_answer(
        self,
        user_id: str,
        stage: int,
        question_id: str,
        user_answer: str,
        correct_answer: str,
        is_correct: bool,
        concept_key: Optional[str] = None,
        temp_user_id: Optional[str] = None,
        class_id: Optional[str] = None,
        unit_id: Optional[str] = None,
        lesson_id: Optional[str] = None,
        problem_id: str | int | None = None,
        problem_key: Optional[str] = None,
        source: str = "base",
        assignment_id: Optional[str] = None,
    ) -> LearningRecord:
        lesson_id = lesson_id or infer_lesson_id(stage, problem_id or question_id)
        unit_id = unit_id or ("unit_1" if lesson_id else None)
        problem_key = problem_key or build_problem_key(
            stage=stage,
            lesson_id=lesson_id,
            problem_id=problem_id or question_id,
        )
        resolved_class_id = class_id or self._resolve_class_id(user_id)
        record = LearningRecord(
            user_id=user_id,
            temp_user_id=temp_user_id,
            class_id=resolved_class_id,
            unit_id=unit_id,
            lesson_id=lesson_id,
            stage=stage,
            question_id=question_id,
            problem_key=problem_key,
            problem_id=problem_id,
            concept_key=concept_key or resolve_concept_key(correct_answer, user_answer),
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
            attempt_no=self._next_attempt_no(user_id=user_id, problem_key=problem_key),
            source=source,
            assignment_id=assignment_id,
        )
        self.repository.create_record(
            record.model_dump() if hasattr(record, "model_dump") else record.dict()
        )
        return record

    def get_weakness_profile(
        self,
        user_id: str,
        min_wrong_count: int = 2,
    ) -> StudentWeaknessProfile:
        records = self.repository.find_records_by_user(user_id)
        wrong_count_by_concept: Dict[str, int] = defaultdict(int)
        last_wrong_at_by_concept: Dict[str, datetime] = {}

        for record in records:
            if record.get("is_correct"):
                continue
            concept_key = record.get("concept_key")
            if not concept_key:
                continue
            wrong_count_by_concept[concept_key] += 1
            created_at = record.get("created_at")
            if isinstance(created_at, datetime):
                last_wrong_at_by_concept[concept_key] = max(
                    created_at,
                    last_wrong_at_by_concept.get(concept_key, created_at),
                )

        weak_concepts = []
        for concept_key, wrong_count in wrong_count_by_concept.items():
            if wrong_count < min_wrong_count:
                continue
            weak_concepts.append(
                WeakConcept(
                    concept_key=concept_key,
                    wrong_count=wrong_count,
                    last_wrong_at=last_wrong_at_by_concept[concept_key],
                    priority=_calculate_priority(wrong_count),
                )
            )

        weak_concepts.sort(key=lambda item: item.priority, reverse=True)
        return StudentWeaknessProfile(user_id=user_id, weak_concepts=weak_concepts)

    def get_class_weakness_summary(self, user_ids: list[str]) -> dict:
        """반 소속 학생들의 학습 기록을 합쳐 공통 약점과 참여 지표를 만든다.

        - wrong_count: 개념별 반 전체 오답 합계
        - student_count: 개념별로 한 번 이상 틀린 학생 수
        - 참여 지표: 활동 학생 수, 전체 풀이/오답 수
        """
        wrong_count_by_concept: Dict[str, int] = defaultdict(int)
        student_count_by_concept: Dict[str, int] = defaultdict(int)
        last_wrong_at_by_concept: Dict[str, datetime] = {}
        active_student_count = 0
        total_solved_count = 0
        total_wrong_count = 0

        for user_id in user_ids:
            records = self.repository.find_records_by_user(user_id)
            if records:
                active_student_count += 1
            concepts_wrong_by_student: set[str] = set()
            for record in records:
                total_solved_count += 1
                if record.get("is_correct"):
                    continue
                concept_key = record.get("concept_key")
                if not concept_key:
                    continue
                total_wrong_count += 1
                wrong_count_by_concept[concept_key] += 1
                if concept_key not in concepts_wrong_by_student:
                    student_count_by_concept[concept_key] += 1
                    concepts_wrong_by_student.add(concept_key)
                created_at = record.get("created_at")
                if isinstance(created_at, datetime):
                    last_wrong_at_by_concept[concept_key] = max(
                        created_at,
                        last_wrong_at_by_concept.get(concept_key, created_at),
                    )

        weak_concepts = [
            {
                "concept_key": concept_key,
                "wrong_count": wrong_count,
                "student_count": student_count_by_concept[concept_key],
                "last_wrong_at": last_wrong_at_by_concept.get(concept_key),
            }
            for concept_key, wrong_count in wrong_count_by_concept.items()
        ]
        weak_concepts.sort(key=lambda item: item["wrong_count"], reverse=True)

        total_students = len(user_ids)
        participation_rate = (
            round(active_student_count / total_students * 100) if total_students else 0
        )
        return {
            "student_count": total_students,
            "active_student_count": active_student_count,
            "participation_rate": participation_rate,
            "total_solved_count": total_solved_count,
            "total_wrong_count": total_wrong_count,
            "weak_concepts": weak_concepts,
        }

    def get_records(self, user_id: str) -> list[LearningRecord]:
        return [
            LearningRecord(**record)
            for record in self.repository.find_records_by_user(user_id)
        ]

    def get_student_progress_metrics(self, user_id: str) -> Dict[str, int]:
        records = sorted(
            self.repository.find_records_by_user(user_id),
            key=_record_created_at,
            reverse=True,
        )
        today = utc_now().date()

        today_solved_count = sum(
            1 for record in records if _record_created_at(record).date() == today
        )
        streak_correct_count = 0
        for record in records:
            if record.get("is_correct"):
                streak_correct_count += 1
                continue
            break

        completed_question_ids = {
            record.get("question_id")
            for record in records
            if record.get("is_correct") and record.get("question_id")
        }

        return {
            "today_solved_count": today_solved_count,
            "total_solved_count": len(records),
            "streak_correct_count": streak_correct_count,
            "completed_question_count": len(completed_question_ids),
        }

    def calculate_progress_rate(self, user_id: str, units_with_lessons: list) -> int:
        """Stage 2를 통과한 차시 수 / 전체 차시 수로 진행도를 계산한다."""
        try:
            total_lessons = sum(len(lessons) for _, lessons in units_with_lessons)
            if total_lessons == 0:
                return 0
            records = self.get_records(user_id)
            completed_lesson_ids = {
                record.lesson_id
                for record in records
                if record.is_correct and record.lesson_id and record.stage == 2
            }
            return round(len(completed_lesson_ids) / total_lessons * 100)
        except Exception:
            return 0

    def build_progress_badges(self, metrics: dict[str, int], progress_rate: int) -> list[str]:
        badges = []
        if metrics["total_solved_count"] > 0:
            badges.append("첫 학습 시작")
        if metrics["streak_correct_count"] >= 3:
            badges.append("연속 정답")
        if progress_rate >= 100:
            badges.append("전체 학습 완료")
        return badges

    def record_stage1_card_check(
        self,
        pair_id: str,
        correct_word: str,
        chosen_word: str,
        user_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        is_correct = chosen_word.strip() == correct_word.strip()
        concept_key = resolve_concept_key(correct_word, chosen_word)
        if user_id:
            self.record_answer(
                user_id=user_id,
                stage=1,
                question_id=f"stage1_{pair_id}",
                lesson_id=infer_lesson_id(1, pair_id),
                problem_id=pair_id,
                user_answer=chosen_word,
                correct_answer=correct_word,
                is_correct=is_correct,
                concept_key=concept_key,
            )
        return is_correct, concept_key

    def record_stage2_answer(
        self,
        problem_id: int,
        correct_answer: str,
        user_answer: str,
        user_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        is_correct = user_answer.strip() == correct_answer.strip()
        concept_key = resolve_concept_key(correct_answer, user_answer)
        if user_id:
            self.record_answer(
                user_id=user_id,
                stage=2,
                question_id=f"stage2_problem_{problem_id}",
                lesson_id=infer_lesson_id(2, problem_id),
                problem_id=problem_id,
                user_answer=user_answer,
                correct_answer=correct_answer,
                is_correct=is_correct,
                concept_key=concept_key,
            )
        return is_correct, concept_key

    def _next_attempt_no(self, user_id: str, problem_key: str | None) -> int:
        if not problem_key:
            return 1
        records = self.repository.find_records_by_user(user_id)
        previous_attempts = sum(
            1 for record in records if record.get("problem_key") == problem_key
        )
        return previous_attempts + 1

    def _resolve_class_id(self, user_id: str) -> str | None:
        if self.classroom_repository is None:
            return None
        classrooms = self.classroom_repository.find_classes_by_student(user_id)
        if not classrooms:
            return None
        return classrooms[0].get("class_id")
