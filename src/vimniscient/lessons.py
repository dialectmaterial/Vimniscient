"""Loading lessons from the YAML files in `lessons/`.

A task's `start` text marks the cursor with ▮ (placed before the character
the cursor sits on). ␣ stands for a space where one has to survive editors
that strip trailing whitespace. `solution` is the reference solution in Vim key
notation; its length is the task's reference keystroke count.

A task can list `variants`: the same skill on other texts, so that recall and
review don't just replay a sentence you remember. A variant inherits whatever
it doesn't set (the solution, hint and filetype).

A lesson runs in two rounds: Learn, with the keys shown, then Recall, the same
skills on other texts, shuffled, without the keys. Which texts it picks
changes from day to day.
"""

import random
from dataclasses import dataclass, field, replace
from datetime import date
from importlib import resources

import yaml

from vimniscient.keys import count_keys

CURSOR = "▮"
SPACE = "␣"


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
    variants: list["Task"] = field(default_factory=list)
    phase: str = "recall"  # learn (keys shown) | recall (from memory) | climb (endless mode)
    generator: str = ""  # a kind in generate.py that makes new texts for this skill
    generated: str = ""  # the seed, on a task made by the generator
    # every version of the task, this one included (not compared: it holds the task itself)
    siblings: list["Task"] = field(default_factory=list, compare=False, repr=False)

    @property
    def item_id(self) -> str:
        return f"task:{self.lesson_id}#{self.index}"

    @property
    def versions(self) -> int:
        return 1 + len(self.variants)

    def version(self, n: int) -> "Task":
        """Version n of this task, cycling through the original and its variants."""
        n %= self.versions
        return self if n == 0 else self.variants[n - 1]

    def next_version(self) -> "Task":
        """The version after this one, for another go on a text not just seen."""
        if self.generated:  # a generated text: another one
            return self.generate(self.generated + "+")
        if len(self.siblings) < 2:
            return self
        i = next(i for i, t in enumerate(self.siblings) if t.start == self.start and t.target == self.target)
        return self.siblings[(i + 1) % len(self.siblings)]

    @property
    def choices(self) -> int:
        """The texts a recall can pick from: the versions, plus a generated one if it has a generator."""
        return self.versions + bool(self.generator)

    def choice(self, n: int, seed: str) -> "Task":
        """Text n of the choices; the last is generated from `seed` when there's a generator."""
        n %= self.choices
        return self.generate(seed) if n == self.versions else self.version(n)

    def generate_kind(self, kind: str, seed: str) -> "Task":
        from vimniscient.generate import generate

        return generate(kind, seed, self)

    def generate(self, seed: str) -> "Task":
        from vimniscient.generate import generate

        return generate(self.generator, seed, self.siblings[0] if self.siblings else self)

    def as_phase(self, phase: str) -> "Task":
        return replace(self, phase=phase)

    @property
    def ref(self) -> int:
        return self.ref_override if self.ref_override is not None else count_keys(self.solution)


SKILLS = ("text-objects", "motions", "edits", "repeats", "search", "visual", "macros", "registers", "ex", "mixed")


@dataclass
class Lesson:
    id: str
    week: int
    day: int
    title: str
    intro: str
    keys: list[str]
    tasks: list[Task]
    review: bool = False  # a mixed review day (skipped by the placement test)
    lazyvim: bool = False  # needs LazyVim's text objects/plugins (not checked in --clean)
    skill: str = "mixed"  # one of SKILLS: what placement and skill drills go by

    @property
    def label(self) -> str:
        return f"Week {self.week} · Day {self.day}"


def _parse_start(text: str) -> tuple[list[str], tuple[int, int]]:
    lines = text.replace(SPACE, " ").split("\n")
    marked = [i for i, line in enumerate(lines) if CURSOR in line]
    if len(marked) != 1 or lines[marked[0]].count(CURSOR) != 1:
        raise ValueError(f"start text needs exactly one {CURSOR}: {text!r}")
    row = marked[0]
    col = len(lines[row].split(CURSOR)[0].encode())
    lines[row] = lines[row].replace(CURSOR, "")
    return lines, (row + 1, col)


def _task(t: dict, parent: Task | None, lesson_id: str, index: int, ft: str) -> Task:
    start, cursor = _parse_start(t["start"])
    return Task(
        goal=t.get("goal") or parent.goal,
        start=start,
        cursor=cursor,
        target=t["target"].replace(SPACE, " ").split("\n"),
        solution=t.get("solution") or parent.solution,
        hint=t.get("hint") or (parent.hint if parent else ""),
        ft=t.get("ft", parent.ft if parent else ft),
        lesson_id=lesson_id,
        index=index,
        generator=t.get("generate", parent.generator if parent else ""),
    )


def _load(source: str, name: str) -> Lesson:
    data = yaml.safe_load(source)
    lesson_id = name.removesuffix(".yaml")
    tasks = []
    for i, t in enumerate(data["tasks"]):
        task = _task(t, None, lesson_id, i, data.get("ft", ""))
        task.variants = [_task(v, task, lesson_id, i, task.ft) for v in t.get("variants", [])]
        for version in (task, *task.variants):
            version.siblings = [task, *task.variants]
        tasks.append(task)
    return Lesson(
        id=lesson_id,
        week=data["week"],
        day=data["day"],
        title=data["title"],
        intro=data.get("intro", "").strip(),
        keys=data.get("keys", []),
        tasks=tasks,
        review=data.get("review", False),
        lazyvim=data.get("lazyvim", False),
        skill=data["skill"],
    )


def two_rounds(lesson: Lesson, day: date | None = None) -> list[Task]:
    """Learn (keys shown), then Recall (the same skills on other texts, shuffled,
    keys hidden). Which texts, and the order, change from day to day, so a
    lesson done again isn't the sentences you remember."""
    day = day or date.today()
    rng = random.Random(f"{lesson.id}:{day}")
    learn, recall = [], []
    for t in lesson.tasks:
        first = rng.randrange(t.versions)  # Learn keeps to the written texts
        second = rng.choice([n for n in range(t.choices) if n != first] or [first])
        learn.append(t.version(first).as_phase("learn"))
        recall.append(t.choice(second, f"{t.item_id}:{day}").as_phase("recall"))
    rng.shuffle(recall)
    return learn + recall


def load_lessons() -> list[Lesson]:
    folder = resources.files("vimniscient") / "lessons"
    lessons = [
        _load(f.read_text(encoding="utf-8"), f.name)
        for f in folder.iterdir()
        if f.name.endswith(".yaml")
    ]
    return sorted(lessons, key=lambda lesson: (lesson.week, lesson.day))
