from pydantic import BaseModel, Field


class Unit(BaseModel):
    unit_id: str = Field(..., description="Stable unit identifier")
    name: str
    order: int
    lesson_ids: list[str] = Field(default_factory=list)


class Lesson(BaseModel):
    lesson_id: str = Field(..., description="Stable lesson identifier")
    unit_id: str
    name: str
    order: int
    concept_keys: list[str] = Field(default_factory=list)
    stage_ids: list[int] = Field(default_factory=lambda: [1, 2, 3])
