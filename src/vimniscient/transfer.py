"""Choose: edits with no hint, where you pick the strategy (see transfer.yaml).

Several solutions count, and the results show another way without rejecting
yours. Like Endless it counts for the streak and grades nothing.
"""

from dataclasses import dataclass
from functools import cache
from importlib import resources

import yaml

from vimniscient.keys import count_keys
from vimniscient.lessons import Lesson, Task, _parse_start

LESSON_ID = "transfer"
PER_RUN = 4
HINT = "No hints here: choosing the keys is the exercise. :Skip shows ways to do it on the results."


@dataclass
class Challenge:
    after: str  # the lesson that unlocks it
    task: Task
    ways: list[str]


@cache
def challenges() -> tuple[Challenge, ...]:
    data = yaml.safe_load((resources.files("vimniscient") / "transfer.yaml").read_text(encoding="utf-8"))
    found = []
    for index, t in enumerate(data["tasks"]):
        start, cursor = _parse_start(t["start"])
        # a solution of "—" keeps the runner from giving anything away, as in VimGolf
        task = Task(goal=t["goal"], start=start, cursor=cursor, target=t["target"].split("\n"), solution="—", hint=HINT,
                    ft="", lesson_id=LESSON_ID, index=index, ref_override=min(count_keys(way) for way in t["ways"]))
        found.append(Challenge(t["after"], task, t["ways"]))
    return tuple(found)


def unlocked(done: set[str]) -> list[Challenge]:
    return [c for c in challenges() if c.after in done]


def pick(lessons: list[Lesson], progress, most: int = PER_RUN) -> list[Challenge]:
    """The unlocked tasks you've gone longest without, never-tried ones first."""
    open_ = unlocked({lesson.id for lesson in lessons if progress.is_done(lesson)})
    last = progress.last_tried("transfer")
    return sorted(open_, key=lambda c: last.get(c.task.index, ""))[:most]


def note(picks: list[Challenge], results: list) -> str:
    """What the results say after a run: another way for each task."""
    by_goal = {c.task.goal: c for c in picks}
    lines = [f"{r.task.goal}  {'  or  '.join(ways)}" for r in results
             if (ways := another_way(by_goal[r.task.goal], r.keys, r.status == "solved"))]
    return "Another way\n" + "\n".join(lines) if lines else ""


def another_way(challenge: Challenge, keys: str, solved: bool) -> list[str]:
    """The ways worth showing after a try: another one, or all of them after a skip."""
    if not solved:
        return challenge.ways
    return [way for way in challenge.ways if way != keys][:1]
