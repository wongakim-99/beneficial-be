import logging
from typing import Any, Dict, List, Optional

from app.domains.content.stage3.schemas import (
    Stage3AnswerResponse,
    Stage3ProblemsResponse,
    Stage3ProblemResponse,
    Stage3ProgressResponse,
)
from app.domains.progress.service.learning_record_service import LearningRecordService
from app.domains.progress.util import infer_lesson_id
from app.infrastructure.db.mongo.mongo_client import MongoClient, get_mongo_client

logger = logging.getLogger(__name__)

DEFAULT_STAGE3_LESSON_ID = "lesson_1"


class Stage3Service:
    problems_collection = "stage3_problems"
    progress_collection = "stage3_progress"

    def __init__(
        self,
        mongo_client: MongoClient,
        learning_record_service: LearningRecordService = None,
        instruction_service=None,
    ):
        self.mongo_client = mongo_client
        self.learning_record_service = learning_record_service
        self.instruction_service = instruction_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_problems(self, lesson_id: str = DEFAULT_STAGE3_LESSON_ID) -> Stage3ProblemsResponse:
        stage3_data = self._load_lesson_data(lesson_id)
        problems = [
            Stage3ProblemResponse(
                problem_id=p["problem_id"],
                sentence_part1=p["sentence_part1"],
                sentence_part2=p["sentence_part2"],
                visual_hint=p.get("visual_hint") or _stage3_visual_hint(p["problem_id"]),
                accent_color=p.get("accent_color") or _stage3_accent_color(p["problem_id"]),
                badge="첫학습",
            )
            for p in stage3_data["problems"]
        ]
        return Stage3ProblemsResponse(
            success=True,
            lesson_id=lesson_id,
            title=stage3_data.get("title"),
            instruction=stage3_data["instruction"],
            total_problems=len(problems),
            problems=problems,
        )

    def get_next_problem(
        self,
        user_id: str,
        lesson_id: str = DEFAULT_STAGE3_LESSON_ID,
    ) -> Optional[Dict[str, Any]]:
        if self.instruction_service:
            assigned_problem = self.instruction_service.get_next_assigned_problem(
                student_id=user_id,
                lesson_id=lesson_id,
                stage=3,
            )
            if assigned_problem:
                return assigned_problem

        progress = self._load_progress(user_id, lesson_id)
        lesson_problem_ids = self._get_problem_ids_for_lesson(lesson_id)
        total = len(lesson_problem_ids)

        if not progress:
            problem = (
                self._get_problem_by_id(lesson_problem_ids[0], lesson_id)
                if lesson_problem_ids
                else None
            )
            if problem:
                problem["badge"] = "첫학습"
            return problem

        next_index = progress.get("next_problem_index", 1)
        completed = set(progress.get("completed_problems", []))

        # 순차 진행 (차시 내 1→N), 완료된 문제 건너뜀
        while (
            next_index <= total
            and lesson_problem_ids[next_index - 1] in completed
        ):
            next_index += 1

        if next_index <= total:
            problem = self._get_problem_by_id(lesson_problem_ids[next_index - 1], lesson_id)
            if problem:
                problem["badge"] = "첫학습"
            return problem

        # 모든 문제를 시도한 뒤 복습 출제
        review_problems = progress.get("review_problems", [])
        if review_problems and progress.get("next_problem_index", 1) > total:
            review_index = progress.get("review_problem_index", 0)
            if review_index >= len(review_problems):
                review_index = 0
                self._patch_progress(user_id, lesson_id, {"review_problem_index": 0})

            problem = self._get_problem_by_id(review_problems[review_index], lesson_id)
            if problem:
                problem["badge"] = "재도전"
            return problem

        return None

    def submit_answer(
        self,
        problem_id: int | str,
        user_answer: str,
        user_id: str,
        lesson_id: str | None = None,
        assignment_id: str | None = None,
    ) -> Stage3AnswerResponse:
        if assignment_id:
            if not self.instruction_service:
                raise ValueError("배정 문제를 처리할 instruction_service가 필요합니다.")
            result = self.instruction_service.submit_student_answer(
                student_id=user_id,
                assignment_id=assignment_id,
                problem_id=str(problem_id),
                user_answer=user_answer,
                learning_record_service=self.learning_record_service,
            )
            return Stage3AnswerResponse(success=True, **result)

        if not isinstance(problem_id, int):
            raise ValueError("기본 Stage 3 문제 ID는 정수여야 합니다.")

        lesson_id = lesson_id or infer_lesson_id(3, problem_id) or DEFAULT_STAGE3_LESSON_ID
        problem = self._get_problem_by_id(problem_id, lesson_id)
        if not problem:
            raise ValueError(f"문제 ID {problem_id}를 찾을 수 없습니다")

        is_correct = user_answer.strip() == problem["correct_answer"].strip()
        status, badge = self._determine_status(problem_id, is_correct, user_id, lesson_id)
        self._update_progress(problem_id, is_correct, user_id, lesson_id)

        if self.learning_record_service:
            self.learning_record_service.record_answer(
                user_id=user_id,
                stage=3,
                question_id=f"stage3_problem_{problem_id}",
                lesson_id=lesson_id,
                problem_id=problem_id,
                user_answer=user_answer,
                correct_answer=problem["correct_answer"],
                is_correct=is_correct,
            )

        return Stage3AnswerResponse(
            success=True,
            problem_id=problem_id,
            is_correct=is_correct,
            user_answer=user_answer,
            correct_answer=problem["correct_answer"],
            explanation=problem["explanation"],
            full_sentence=problem["full_sentence"],
            status=status,
            badge=badge,
        )

    def get_progress(
        self,
        user_id: str,
        lesson_id: str = DEFAULT_STAGE3_LESSON_ID,
    ) -> Stage3ProgressResponse:
        progress = self._load_progress(user_id, lesson_id)
        if not progress:
            total = len(self._get_problem_ids_for_lesson(lesson_id))
            progress = self._create_initial_progress(user_id, lesson_id, total)
            self.mongo_client.insert_one(self.progress_collection, progress)

        is_completed = len(progress.get("completed_problems", [])) >= progress.get(
            "total_problems", 0
        )
        return Stage3ProgressResponse(
            success=True, progress=progress, is_completed=is_completed
        )

    def reset_progress(
        self,
        user_id: str,
        lesson_id: str = DEFAULT_STAGE3_LESSON_ID,
    ) -> None:
        self.mongo_client.delete_one(
            self.progress_collection, {"user_id": user_id, "lesson_id": lesson_id}
        )
        total = len(self._get_problem_ids_for_lesson(lesson_id))
        self.mongo_client.insert_one(
            self.progress_collection, self._create_initial_progress(user_id, lesson_id, total)
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_progress(self, user_id: str, lesson_id: str) -> Optional[Dict[str, Any]]:
        progress = self.mongo_client.find_one(
            self.progress_collection, {"user_id": user_id, "lesson_id": lesson_id}
        )
        if progress:
            return progress

        if lesson_id == DEFAULT_STAGE3_LESSON_ID:
            legacy = self.mongo_client.find_one(
                self.progress_collection,
                {"user_id": user_id, "lesson_id": {"$exists": False}},
            )
            if legacy:
                lesson_problem_ids = set(self._get_problem_ids_for_lesson(lesson_id))
                normalized = {
                    **legacy,
                    "lesson_id": lesson_id,
                    "total_problems": len(lesson_problem_ids),
                    "completed_problems": [
                        pid
                        for pid in legacy.get("completed_problems", [])
                        if pid in lesson_problem_ids
                    ],
                    "review_problems": [
                        pid
                        for pid in legacy.get("review_problems", [])
                        if pid in lesson_problem_ids
                    ],
                    "current_problem_id": (
                        legacy.get("current_problem_id")
                        if legacy.get("current_problem_id") in lesson_problem_ids
                        else None
                    ),
                }
                self.mongo_client.update_one(
                    self.progress_collection,
                    {"user_id": user_id, "lesson_id": {"$exists": False}},
                    {
                        key: value
                        for key, value in normalized.items()
                        if key not in ("_id", "user_id")
                    },
                )
                return normalized
        return None

    def _patch_progress(self, user_id: str, lesson_id: str, fields: Dict[str, Any]) -> None:
        self.mongo_client.update_one(
            self.progress_collection, {"user_id": user_id, "lesson_id": lesson_id}, fields
        )

    def _create_initial_progress(
        self,
        user_id: str,
        lesson_id: str,
        total: int,
    ) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "lesson_id": lesson_id,
            "total_problems": total,
            "correct_count": 0,
            "wrong_count": 0,
            "review_problems": [],
            "completed_problems": [],
            "current_problem_id": None,
            "next_problem_index": 1,
            "review_problem_index": 0,
        }

    def _update_progress(
        self,
        problem_id: int,
        is_correct: bool,
        user_id: str,
        lesson_id: str,
    ) -> None:
        progress = self._load_progress(user_id, lesson_id)
        if not progress:
            total = len(self._get_problem_ids_for_lesson(lesson_id))
            progress = self._create_initial_progress(user_id, lesson_id, total)
            self.mongo_client.insert_one(self.progress_collection, progress)
            # reload to get the inserted doc
            progress = self._load_progress(user_id, lesson_id)

        if is_correct:
            progress["correct_count"] = progress.get("correct_count", 0) + 1
            if problem_id not in progress.get("completed_problems", []):
                progress["completed_problems"] = progress.get("completed_problems", []) + [problem_id]
            if problem_id in progress.get("review_problems", []):
                progress["review_problems"] = [
                    pid for pid in progress["review_problems"] if pid != problem_id
                ]
                progress["review_problem_index"] = progress.get("review_problem_index", 0) + 1
        else:
            progress["wrong_count"] = progress.get("wrong_count", 0) + 1
            if problem_id not in progress.get("review_problems", []):
                progress["review_problems"] = progress.get("review_problems", []) + [problem_id]

        progress["current_problem_id"] = problem_id
        lesson_problem_ids = self._get_problem_ids_for_lesson(lesson_id)
        try:
            local_problem_index = lesson_problem_ids.index(problem_id) + 1
        except ValueError:
            local_problem_index = progress.get("next_problem_index", 1)
        next_index = progress.get("next_problem_index", 1)

        if local_problem_index == next_index and next_index <= len(lesson_problem_ids):
            progress["next_problem_index"] = next_index + 1
        elif problem_id in progress.get("review_problems", []) and not is_correct:
            progress["review_problem_index"] = progress.get("review_problem_index", 0) + 1

        # _id 는 filter 에서만 사용하므로 update dict 에서 제거
        update_fields = {
            k: v for k, v in progress.items() if k not in ("_id", "user_id", "lesson_id")
        }
        self.mongo_client.update_one(
            self.progress_collection, {"user_id": user_id, "lesson_id": lesson_id}, update_fields
        )

    def _determine_status(
        self,
        problem_id: int,
        is_correct: bool,
        user_id: str,
        lesson_id: str,
    ) -> tuple:
        if is_correct:
            return "correct", "훌륭해요!"

        progress = self._load_progress(user_id, lesson_id)
        if progress and problem_id in progress.get("review_problems", []):
            return "review", "재도전"
        return "review", "잠시후복습"

    def _get_problem_by_id(
        self,
        problem_id: int,
        lesson_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        data = self._load_lesson_data(lesson_id) if lesson_id else self._load_problems_data()
        if not data:
            return None
        for p in data.get("problems", []):
            if p["problem_id"] == problem_id:
                problem = dict(p)
                problem["visual_hint"] = problem.get("visual_hint") or _stage3_visual_hint(problem_id)
                problem["accent_color"] = problem.get("accent_color") or _stage3_accent_color(problem_id)
                problem.pop("image", None)
                return problem
        return None

    def _load_problems_data(self) -> Dict[str, Any]:
        data = self.mongo_client.find_one(
            self.problems_collection, {"_id": "stage3_problems"}
        )
        if not data:
            raise RuntimeError("3단계 문제 데이터를 찾을 수 없습니다")
        return data

    def _load_lesson_data(self, lesson_id: str) -> Dict[str, Any]:
        data = self.mongo_client.find_one(
            self.problems_collection,
            {"lesson_id": lesson_id},
        )
        if data:
            return data

        legacy_data = self._load_problems_data()
        lesson_problem_ids = set(_legacy_problem_ids_for_lesson(lesson_id, legacy_data))
        problems = [
            problem
            for problem in legacy_data.get("problems", [])
            if problem.get("problem_id") in lesson_problem_ids
        ]
        return {
            "_id": f"stage3_{lesson_id}",
            "lesson_id": lesson_id,
            "title": legacy_data.get("title"),
            "instruction": legacy_data["instruction"],
            "problems": problems,
            "total_problems": len(problems),
        }

    def _get_total_problems(self) -> int:
        data = self.mongo_client.find_one(
            self.problems_collection, {"_id": "stage3_problems"}
        )
        return data.get("total_problems", 0) if data else 0

    def _get_problem_ids_for_lesson(self, lesson_id: str) -> List[int]:
        data = self._load_lesson_data(lesson_id)
        return sorted(p["problem_id"] for p in data.get("problems", []))


def get_stage3_service(
    learning_record_service: LearningRecordService = None,
    instruction_service=None,
) -> Stage3Service:
    return Stage3Service(
        mongo_client=get_mongo_client(),
        learning_record_service=learning_record_service,
        instruction_service=instruction_service,
    )


def _stage3_visual_hint(problem_id: int) -> str:
    lesson_hints = {
        1: "book-open",
        2: "backpack",
        3: "send",
        4: "check-circle",
        5: "clock",
    }
    lesson_no = ((problem_id - 1) // 5) + 1
    return lesson_hints.get(lesson_no, "pencil")


def _stage3_accent_color(problem_id: int) -> str:
    colors = ["primary", "success", "warning", "info", "secondary"]
    return colors[((problem_id - 1) // 5) % len(colors)]


def _lesson_number(lesson_id: str) -> int:
    try:
        return max(1, int(str(lesson_id).split("_")[-1]))
    except (TypeError, ValueError):
        return 1


def _legacy_problem_ids_for_lesson(lesson_id: str, legacy_data: Dict[str, Any]) -> List[int]:
    lesson_no = _lesson_number(lesson_id)
    problem_ids = sorted(p["problem_id"] for p in legacy_data.get("problems", []))
    start = (lesson_no - 1) * 5
    return problem_ids[start : start + 5]
