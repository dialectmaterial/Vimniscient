"""Loading lessons from the YAML files in `lessons/`.

A task's `start` text marks the cursor with ▮ (placed before the character
the cursor sits on). `solution` is the reference solution in Vim key
notation; its length is the task's reference keystroke count.
"""

from dataclasses import dataclass
from importlib import resources

import yaml

from vimniscient.keys import count_keys

CURSOR = "▮"


@dataclass
class Task:
    goal: str
    start: list[str]
    cursor: tuple[int, int]  # (1-based line, 0-based byte column), as nvim wants
    target: list[str]
    solution: str
    hint: str
    ft: str
    lesson_id: str = ""
    index: int = 0  # position in its lesson
    ref_override: int | None = None  # when there's no reference solution (VimGolf)

    @property
    def item_id(self) -> str:
        return f"task:{self.lesson_id}#{self.index}"

    @property
    def ref(self) -> int:
        return self.ref_override if self.ref_override is not None else count_keys(self.solution)


@dataclass
class Lesson:
    id: str
    week: int
    day: int
    title: str
    intro: str
    keys: list[str]
    tasks: list[Task]

    @property
    def label(self) -> str:
        return f"Week {self.week} · Day {self.day}"


def _parse_start(text: str) -> tuple[list[str], tuple[int, int]]:
    lines = text.split("\n")
    marked = [i for i, line in enumerate(lines) if CURSOR in line]
    if len(marked) != 1 or lines[marked[0]].count(CURSOR) != 1:
        raise ValueError(f"start text needs exactly one {CURSOR}: {text!r}")
    row = marked[0]
    col = len(lines[row].split(CURSOR)[0].encode())
    lines[row] = lines[row].replace(CURSOR, "")
    return lines, (row + 1, col)


def _load(source: str, name: str) -> Lesson:
    data = yaml.safe_load(source)
    lesson_id = name.removesuffix(".yaml")
    tasks = []
    for i, t in enumerate(data["tasks"]):
        start, cursor = _parse_start(t["start"])
        tasks.append(
            Task(
                goal=t["goal"],
                start=start,
                cursor=cursor,
                target=t["target"].split("\n"),
                solution=t["solution"],
                hint=t.get("hint", ""),
                ft=t.get("ft", data.get("ft", "")),
                lesson_id=lesson_id,
                index=i,
            )
        )
    return Lesson(
        id=lesson_id,
        week=data["week"],
        day=data["day"],
        title=data["title"],
        intro=data.get("intro", "").strip(),
        keys=data.get("keys", []),
        tasks=tasks,
    )


def load_lessons() -> list[Lesson]:
    folder = resources.files("vimniscient") / "lessons"
    lessons = [
        _load(f.read_text(encoding="utf-8"), f.name)
        for f in folder.iterdir()
        if f.name.endswith(".yaml")
    ]
    return sorted(lessons, key=lambda lesson: (lesson.week, lesson.day))
