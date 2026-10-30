"""`vimniscient eval`: does the training work? Three sittings of the same eight
skills, on texts from no lesson, with no hints: `pre` now, `post` after some
weeks of training, `delayed` a few weeks after that. Stored locally, never graded.
"""

from functools import cache
from importlib import resources
from statistics import median

import yaml

from vimniscient.keys import count_keys
from vimniscient.lessons import Lesson, Task, _parse_start

LESSON_ID = "eval"
HINT = "No hints in the test: :Skip what you don't know."
FORM = {"pre": "a", "post": "b", "delayed": "a"}


@cache
def forms() -> dict[str, tuple[dict, ...]]:
    data = yaml.safe_load((resources.files("vimniscient") / "eval.yaml").read_text(encoding="utf-8"))
    return {name: tuple(tasks) for name, tasks in data["forms"].items()}


def task(t: dict, index: int) -> Task:
    start, cursor = _parse_start(t["start"])
    return Task(goal=t["goal"], start=start, cursor=cursor, target=t["target"].split("\n"), solution="—", hint=HINT, ft="",
                lesson_id=LESSON_ID, index=index, ref_override=min(count_keys(way) for way in t["ways"]))


def lesson(stage: str) -> Lesson:
    tasks = [task(t, i) for i, t in enumerate(forms()[FORM[stage]])]
    return Lesson(id=LESSON_ID, week=0, day=0, title=f"Evaluation: {stage}", intro="", keys=[], tasks=tasks)


def summary(rows: list[tuple[str, float | None, int, int]]) -> tuple[int, float | None, float | None]:
    """(solved, median seconds, keys against the reference) from (status, seconds, count, ref) rows."""
    solved = [row for row in rows if row[0] == "solved"]
    seconds = [row[1] for row in solved if row[1] is not None]
    keys = sum(row[2] for row in solved) / sum(row[3] for row in solved) if solved else None
    return len(solved), median(seconds) if seconds else None, keys


def report(progress) -> str:
    lines = [f"{'':8}{'date':12}{'solved':8}{'median':9}keys/ref"]
    for stage in FORM:
        rows = progress.db.execute(
            "SELECT status, seconds, count, ref, ts FROM attempts WHERE phase = ? ORDER BY id DESC LIMIT ?",
            (f"eval-{stage}", len(forms()[FORM[stage]]))).fetchall()
        if not rows:
            lines.append(f"{stage:8}not taken yet: vimniscient eval {stage}")
            continue
        solved, seconds, keys = summary([row[:4] for row in rows])
        time = f"{seconds:.1f}s" if seconds is not None else "-"
        ratio = f"{keys:.2f}" if keys is not None else "-"
        lines.append(f"{stage:8}{rows[0][4][:10]:12}{f'{solved}/{len(rows)}':8}{time:9}{ratio}")
    return "\n".join(lines)
