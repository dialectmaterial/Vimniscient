"""Multi-file missions (missions.yaml): real files in a throwaway folder, your
own Neovim with all its plugins, and a check that runs when you save. Nothing
outside that folder is touched, and leaving just deletes it. Ungraded."""

from dataclasses import dataclass
from functools import cache
from importlib import resources

import yaml

from vimniscient.keys import count_keys
from vimniscient.lessons import Lesson, Task

LESSON_ID = "mission"


@dataclass
class Mission:
    index: int
    after: str
    title: str
    goal: str
    hint: str
    files: dict[str, str]
    targets: dict[str, str]
    ways: list[str]

    @property
    def task(self) -> Task:
        return Task(goal=self.goal, start=[""], cursor=(1, 0), target=[""], solution="—", hint=self.hint, ft="",
                    lesson_id=LESSON_ID, index=self.index, ref_override=min(count_keys(way) for way in self.ways))


@cache
def missions() -> tuple[Mission, ...]:
    data = yaml.safe_load((resources.files("vimniscient") / "missions.yaml").read_text(encoding="utf-8"))
    return tuple(Mission(index=i, **m) for i, m in enumerate(data["missions"]))


def pick(lessons: list[Lesson], progress) -> Mission | None:
    """The unlocked mission you've gone longest without, never-tried ones first."""
    done = {lesson.id for lesson in lessons if progress.is_done(lesson)}
    last = progress.last_tried("mission")
    return min((m for m in missions() if m.after in done), key=lambda m: last.get(m.index, ""), default=None)
