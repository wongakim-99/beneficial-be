from app.domains.content.model.content_models import Lesson, Unit
from app.domains.content.repository.catalog_repository import ContentCatalogRepository


class ContentCatalogService:
    def __init__(self, repository: ContentCatalogRepository):
        self.repository = repository

    def list_units_with_lessons(self) -> list[tuple[Unit, list[Lesson]]]:
        lessons_by_unit: dict[str, list[Lesson]] = {}
        for lesson_doc in self.repository.find_lessons():
            lesson = Lesson(**lesson_doc)
            lessons_by_unit.setdefault(lesson.unit_id, []).append(lesson)

        units = []
        for unit_doc in self.repository.find_units():
            unit = Unit(**unit_doc)
            lessons = lessons_by_unit.get(unit.unit_id, [])
            if unit.lesson_ids:
                lesson_by_id = {lesson.lesson_id: lesson for lesson in lessons}
                lessons = [
                    lesson_by_id[lesson_id]
                    for lesson_id in unit.lesson_ids
                    if lesson_id in lesson_by_id
                ]
            units.append((unit, lessons))

        return units

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        lesson_doc = self.repository.find_lesson_by_id(lesson_id)
        if not lesson_doc:
            return None
        return Lesson(**lesson_doc)
