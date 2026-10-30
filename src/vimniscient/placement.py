"""The placement test, by skill: a binary search along each skill's lessons.

Lessons of a skill build on each other, so each round tests the middle of what's
still open: a pass moves further along, a miss looks earlier. Skills never touch
each other's result. Weekly reviews and week 6 aren't tested; a review counts
as known once its week's other lessons all are.
"""

from vimniscient import srs
from vimniscient.cards import has_lazyvim
from vimniscient.lessons import Lesson, Task


class Search:
    def __init__(self, lessons: list[Lesson], lazyvim: bool | None = None) -> None:
        self.lessons = lessons
        self.seen: set[str] = set()
        lazyvim = has_lazyvim() if lazyvim is None else lazyvim
        tested = [lesson for lesson in lessons if lesson.skill != "mixed" and (lazyvim or not lesson.lazyvim)]
        self.skills: dict[str, list[Lesson]] = {}
        for lesson in tested:
            self.skills.setdefault(lesson.skill, []).append(lesson)
        self.low = dict.fromkeys(self.skills, 0)  # lessons before this are known
        self.high = {skill: len(found) for skill, found in self.skills.items()}  # from here on, not

    @property
    def finished(self) -> bool:
        return all(self.low[skill] >= self.high[skill] for skill in self.skills)

    def _middle(self, skill: str) -> Lesson | None:
        low, high = self.low[skill], self.high[skill]
        return self.skills[skill][(low + high) // 2] if low < high else None

    def round(self) -> list[Task]:
        """The first and last task of the middle lesson of every skill still open."""
        tasks = []
        for skill in self.skills:
            lesson = self._middle(skill)
            if lesson:
                tasks += lesson.tasks[:1] if len(lesson.tasks) == 1 else [lesson.tasks[0], lesson.tasks[-1]]
        return tasks

    def update(self, results: list) -> None:
        passed: dict[str, list[bool]] = {}
        for r in results:
            passed.setdefault(r.task.lesson_id, []).append(srs.task_grade(r.status, r.count, r.task.ref, r.hints) in (srs.GOOD, srs.EASY))
        for skill in self.skills:
            lesson = self._middle(skill)
            if lesson is None or lesson.id not in passed:
                continue
            middle = (self.low[skill] + self.high[skill]) // 2
            if all(passed[lesson.id]):
                self.low[skill] = middle + 1
            else:
                self.high[skill] = middle

    def known(self) -> list[Lesson]:
        found = [lesson for skill, lessons in self.skills.items() for lesson in lessons[: self.low[skill]]]
        for week in {lesson.week for lesson in found}:
            days = [lesson for lesson in self.lessons if lesson.week == week]
            if all(lesson in found or lesson.skill == "mixed" for lesson in days):
                found += [lesson for lesson in days if lesson not in found]
        return sorted(found, key=lambda lesson: (lesson.week, lesson.day))
