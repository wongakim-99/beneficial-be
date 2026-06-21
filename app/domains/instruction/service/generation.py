from pydantic import BaseModel, Field

from app.domains.instruction.models import GeneratedProblem
from app.domains.progress.util import CONCEPT_KEY_BY_ANSWER
from app.infrastructure.external.openai_client import OpenAIClient


class GeneratedProblemCandidate(BaseModel):
    sentence_part1: str = Field(..., description="빈칸 앞 문장")
    correct_answer: str = Field(..., description="빈칸 정답")
    sentence_part2: str = Field(..., description="빈칸 뒤 문장")
    full_sentence: str = Field(..., description="정답을 넣은 완성 문장")
    explanation: str = Field(..., description="초등학생용 짧은 해설")
    visual_hint: str | None = Field(None, description="프론트 아이콘 키")
    accent_color: str | None = Field(None, description="프론트 색상 토큰")


class GeneratedProblemBatch(BaseModel):
    problems: list[GeneratedProblemCandidate] = Field(default_factory=list)


class OpenAIProblemGenerator:
    def __init__(
        self,
        openai_client: OpenAIClient,
        model: str = "gpt-4o-2024-08-06",
    ):
        self.openai_client = openai_client
        self.model = model

    async def generate(
        self,
        concept_key: str,
        count: int,
        lesson_id: str,
        difficulty: str | None = None,
    ) -> list[GeneratedProblem]:
        allowed_answers = _answers_for_concept(concept_key)
        messages = [
            {
                "role": "system",
                "content": (
                    "너는 초등학생 한국어 맞춤법 문제를 만드는 교사용 도구다. "
                    "반드시 JSON 스키마에 맞춰 Stage 3 빈칸 문제만 만든다. "
                    "문장은 초등학생이 이해할 수 있게 짧고 자연스럽게 작성한다. "
                    "해설은 120자 이내로 쓴다."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"concept_key: {concept_key}\n"
                    f"lesson_id: {lesson_id}\n"
                    f"난이도: {difficulty or 'normal'}\n"
                    f"문제 수: {count}\n"
                    f"정답 후보는 다음 목록 안에서만 고른다: {', '.join(allowed_answers)}\n\n"
                    "각 문제는 sentence_part1 + correct_answer + sentence_part2가 "
                    "full_sentence와 같은 뜻과 표기를 가져야 한다. "
                    "sentence_part1에는 빈칸 앞 문장만, sentence_part2에는 빈칸 뒤 문장만 넣어라."
                ),
            },
        ]
        parsed = await self.openai_client.parse_chat_completion(
            messages=messages,
            response_format=GeneratedProblemBatch,
            model=self.model,
            max_tokens=1200,
            temperature=0.4,
        )
        return [
            GeneratedProblem(
                sentence_part1=candidate.sentence_part1,
                correct_answer=candidate.correct_answer,
                sentence_part2=candidate.sentence_part2,
                full_sentence=candidate.full_sentence,
                explanation=candidate.explanation,
                visual_hint=candidate.visual_hint,
                accent_color=candidate.accent_color,
                validation_status="pending",
            )
            for candidate in parsed.problems[:count]
        ]


def _answers_for_concept(concept_key: str) -> list[str]:
    answers = [
        answer
        for answer, mapped_concept_key in CONCEPT_KEY_BY_ANSWER.items()
        if mapped_concept_key == concept_key
    ]
    return sorted(set(answers))
