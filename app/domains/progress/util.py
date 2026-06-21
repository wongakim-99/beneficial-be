from datetime import datetime, timezone
from typing import Any, Dict

CONCEPT_KEY_BY_ANSWER = {
    # Stage 2/3 활용형
    "가르쳐": "가르치다/가르키다",
    "가르켰다": "가르치다/가르키다",
    "맞췄다": "맞추다/맞히다",
    "맞혀": "맞추다/맞히다",
    "맞혔다": "맞추다/맞히다",
    "잃어버렸다": "잊다/잃다",
    "잊었다": "잊다/잃다",
    "메고": "메다/매다",
    "매고": "메다/매다",
    "매었다": "메다/매다",
    "바란다": "바라다/바래다",
    "바랬다": "바라다/바래다",
    "부쳤다": "부치다/붙이다",
    "붙였다": "부치다/붙이다",
    "부치신다": "부치다/붙이다",
    "돼": "되/돼",
    "되고": "되/돼",
    "돼서": "되/돼",
    "안": "안/않다",
    "않다": "안/않다",
    "않고": "안/않다",
    "반드시": "반드시/반듯이",
    "반듯이": "반드시/반듯이",
    "이따가": "이따가/있다가",
    "있다가": "이따가/있다가",
    # Stage 1 기본형 (카드 쌍 word1/word2)
    "가르치다": "가르치다/가르키다",
    "가르키다": "가르치다/가르키다",
    "맞추다": "맞추다/맞히다",
    "맞히다": "맞추다/맞히다",
    "잊다": "잊다/잃다",
    "잃다": "잊다/잃다",
    "메다": "메다/매다",
    "매다": "메다/매다",
    "바라다": "바라다/바래다",
    "바래다": "바라다/바래다",
    "부치다": "부치다/붙이다",
    "붙이다": "부치다/붙이다",
    "되다": "되/돼",
    "돼다": "되/돼",
}


def resolve_concept_key(correct_answer: str, user_answer: str | None = None) -> str:
    correct = correct_answer.strip()
    submitted = (user_answer or "").strip()
    return (
        CONCEPT_KEY_BY_ANSWER.get(correct)
        or CONCEPT_KEY_BY_ANSWER.get(submitted)
        or correct
    )


def build_problem_key(
    stage: int,
    lesson_id: str | None,
    problem_id: str | int | None,
) -> str | None:
    if lesson_id is None or problem_id is None:
        return None
    return f"stage{stage}:{lesson_id}:{problem_id}"


def infer_lesson_id(stage: int, problem_id: str | int | None) -> str | None:
    if problem_id is None:
        return None

    if stage == 1:
        pair_no = _extract_last_int(problem_id)
        if pair_no is None:
            return None
        return f"lesson_{((pair_no - 1) // 2) + 1}"

    numeric_problem_id = _extract_last_int(problem_id)
    if numeric_problem_id is None:
        return None

    if stage == 2:
        return f"lesson_{((numeric_problem_id - 1) // 4) + 1}"
    if stage == 3:
        return f"lesson_{((numeric_problem_id - 1) // 5) + 1}"
    return None


def _extract_last_int(value: str | int) -> int | None:
    if isinstance(value, int):
        return value
    parts = str(value).split("_")
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return None


def _calculate_priority(wrong_count: int) -> float:
    return min(1.0, round(0.5 + wrong_count * 0.15, 2))


def _record_created_at(record: Dict[str, Any]) -> datetime:
    created_at = record.get("created_at")
    if not isinstance(created_at, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)
