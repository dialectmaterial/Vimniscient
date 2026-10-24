"""Endless mode: tasks from every lesson, one after another, getting harder.

Each task you solve climbs a level. Two things make the climb harder:
- the mix: it starts with the first lesson and takes in the next one every
  LEVELS_PER_LESSON levels, half the time picking from the newest lesson;
- the key budget: about twice the reference at level 1, shrinking to exactly
  the reference by level RAMP (the runner works it out, see runner.lua).

Going over the budget, :Skip, or asking for the answer counts as a miss. A
miss shows the answer, gives the task again with the keys shown (Learn), and
GAP tasks later brings it back on another text, from memory (Recall).
"""

import math
import random
from collections import deque

from vimniscient.lessons import Lesson, Task

LEVELS_PER_LESSON = 4
RAMP = 200
GAP = 2
RUNGS = 1000  # more than anyone climbs in a sitting; the runner wraps around after
RESTART_BELOW = 10  # a new run starts this many levels below where the last one ended


def unlocked(level: int, lessons: int) -> int:
    """How many lessons are in the mix at `level`."""
    return max(1, min(lessons, 1 + (level - 1) // LEVELS_PER_LESSON))


def budget(ref: int, level: int) -> int:
    """The most keys allowed at `level`; mirrors budget() in runner.lua."""
    slack = max(0.0, 1 - (level - 1) / RAMP)
    return ref + math.ceil(ref * slack) + (1 if slack > 0 else 0)


def ladder(lessons: list[Lesson], start: int, length: int = RUNGS, seed: object = None) -> list[tuple[Task, int]]:
    """The tasks to climb from level `start` on, as (task, version)."""
    rng = random.Random(seed)
    recent: deque[str] = deque(maxlen=8)
    rungs = []
    for level in range(start, start + length):
        mix = lessons[: unlocked(level, len(lessons))]
        lesson = mix[-1] if rng.random() < 0.5 else rng.choice(mix)
        task = rng.choice([t for t in lesson.tasks if t.item_id not in recent] or lesson.tasks)
        recent.append(task.item_id)
        rungs.append((task, rng.randrange(task.versions)))
    return rungs


def summary(results: list, start: int) -> dict[str, int]:
    climbed = sum(r.task.phase == "climb" and r.status == "solved" for r in results)
    return {
        "start": start,
        "level": start + climbed,
        "climbed": climbed,
        "missed": sum(r.status in ("failed", "skipped") and r.task.phase != "learn" for r in results),
        "fixed": sum(r.task.phase == "recall" and r.status == "solved" for r in results),
    }
