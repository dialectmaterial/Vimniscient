"""Spaced repetition: a small SM-2 variant shared by cards and Vim tasks."""

from dataclasses import dataclass
from datetime import date, timedelta

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4


@dataclass
class Item:
    id: str
    kind: str  # card | task
    ease: float = 2.5
    interval: float = 0.0  # days
    due: date | None = None
    reps: int = 0
    lapses: int = 0
    created: date | None = None


def review(item: Item, grade: int, today: date) -> Item:
    """Schedule the next review after answering with `grade`."""
    if grade == AGAIN:
        item.lapses += 1
        item.reps = 0
        item.interval = 1
        item.ease = max(1.3, item.ease - 0.2)
    elif grade == HARD:
        item.reps += 1
        item.interval = max(1, item.interval * 1.2)
        item.ease = max(1.3, item.ease - 0.15)
    elif grade == GOOD:
        item.interval = 1 if item.reps == 0 else 3 if item.reps == 1 else item.interval * item.ease
        item.reps += 1
    else:  # EASY: known already, or done without effort
        item.interval = 4 if item.reps == 0 else item.interval * item.ease * 1.3
        item.reps += 1
        item.ease += 0.15
    item.created = item.created or today
    item.due = today + timedelta(days=max(1, round(item.interval)))
    return item


def task_grade(status: str, count: int, ref: int, hints: int) -> int | None:
    """How well a Vim task went; None when it says nothing (not reached, or quit midway)."""
    if status in ("unseen", "quit"):
        return None
    if status != "solved":
        return AGAIN
    if hints:
        return HARD
    if count <= ref:
        return EASY
    if count <= ref * 1.5 + 1:
        return GOOD
    return HARD
