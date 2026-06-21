from app.domains.instruction.model.instruction_models import GeneratedProblem
from app.domains.progress.util import CONCEPT_KEY_BY_ANSWER


def validate_generated_problem(
    problem: GeneratedProblem,
    concept_key: str,
    existing_full_sentences: set[str],
    seen_full_sentences: set[str],
) -> list[str]:
    reasons = []
    if not problem.sentence_part1.strip() and not problem.sentence_part2.strip():
        reasons.append("빈칸 앞/뒤 문장 중 하나는 필요합니다.")
    if not problem.correct_answer.strip():
        reasons.append("정답이 비어 있습니다.")
    if not problem.full_sentence.strip():
        reasons.append("완성 문장이 비어 있습니다.")
    if len(problem.explanation.strip()) > 120:
        reasons.append("해설은 120자 이하여야 합니다.")

    allowed_answers = answers_for_concept(concept_key)
    if problem.correct_answer.strip() not in allowed_answers:
        reasons.append("정답이 concept_key의 허용 답안 목록에 없습니다.")

    expected_full_sentence = compose_full_sentence(
        problem.sentence_part1,
        problem.correct_answer,
        problem.sentence_part2,
    )
    if normalize_sentence(problem.full_sentence) != normalize_sentence(expected_full_sentence):
        reasons.append("완성 문장이 빈칸 앞/정답/뒤 문장 조합과 일치하지 않습니다.")

    normalized = normalize_sentence(problem.full_sentence)
    if normalized in {normalize_sentence(s) for s in existing_full_sentences}:
        reasons.append("기존 기본 문제와 중복됩니다.")
    if normalized in seen_full_sentences:
        reasons.append("같은 생성 요청 안에서 중복된 문제입니다.")
    return reasons


def allowed_concept_keys() -> set[str]:
    return set(CONCEPT_KEY_BY_ANSWER.values())


def answers_for_concept(concept_key: str) -> set[str]:
    return {
        answer
        for answer, mapped_concept_key in CONCEPT_KEY_BY_ANSWER.items()
        if mapped_concept_key == concept_key
    }


def compose_full_sentence(part1: str, answer: str, part2: str) -> str:
    left = part1.strip()
    middle = answer.strip()
    right = part2.strip()

    sentence = f"{left} {middle}" if left else middle

    if not right:
        return sentence
    if right[0] in ".,?!)]}":
        return f"{sentence}{right}"
    return f"{sentence} {right}"


def normalize_sentence(sentence: str) -> str:
    return " ".join(sentence.strip().split())
