"""Today's routine, without the interface: which steps are left and roughly how
long each takes. The main screen shows it; the reminders read it."""

import math
from dataclasses import dataclass

from vimniscient import drills, habits
from vimniscient.cards import Deck
from vimniscient.lessons import Lesson, Task
from vimniscient.progress import Progress

ROUTINE = ("cards", "drills", "review", "lesson")  # what `t` runs, in order; VimGolf and Endless are extras

# Rough times, for "about 12 minutes left". Erring on the long side is kinder
# than promising five minutes and taking fifteen.
CARD_SECONDS = 12
DRILL_SECONDS = 45
REVIEW_TASK_SECONDS = 45
LESSON_TASK_SECONDS = 35  # per round; a lesson runs every task twice (Learn, Recall)
LESSON_READING_SECONDS = 60


@dataclass
class Step:
    id: str
    label: str
    detail: str
    todo: bool | None  # None: optional, never "left to do" (VimGolf, Endless)
    minutes: int = 0  # about how long what's left of it takes


def minutes(seconds: float) -> int:
    return max(1, math.ceil(seconds / 60)) if seconds else 0


def plural(n: int, word: str, many: str = "") -> str:
    return f"{n} {word if n == 1 else many or word + 's'}"


def todays_drills(progress: Progress, drill_list: list[drills.Drill]) -> list[drills.Drill]:
    if not drills.Hyprland().available:
        return []
    return progress.due_drills(drill_list) + progress.new_drills(drill_list)


def habit_tasks(progress: Progress, lessons: list[Lesson], exclude: list[Task]) -> list[Task]:
    """One task from each lesson that fixes a habit hardtime keeps catching (lessons
    you've done only), skipping tasks already practised today."""
    taken = {t.item_id for t in exclude} | progress.practised_today()
    items = progress.items("task")
    tasks = []
    for lesson_id in habits.drill_lessons():
        lesson = next((lesson for lesson in lessons if lesson.id == lesson_id), None)
        if not lesson or not progress.is_done(lesson):
            continue
        # the task that has gone worst so far
        candidates = [t for t in lesson.tasks if t.item_id not in taken]
        if candidates:
            worst = min(candidates, key=lambda t: items[t.item_id].ease if t.item_id in items else 0)
            tasks.append(progress.version_for(worst))
            taken.add(worst.item_id)
    return tasks[:3]


def review_tasks(progress: Progress, lessons: list[Lesson]) -> list[Task]:
    due = progress.due_tasks(lessons)
    return due + habit_tasks(progress, lessons, due)


def lesson_minutes(lesson: Lesson) -> int:
    return minutes(len(lesson.tasks) * 2 * LESSON_TASK_SECONDS + LESSON_READING_SECONDS)


def plan(progress: Progress, lessons: list[Lesson], decks: dict[str, Deck], drill_list: list[drills.Drill]) -> list[Step]:
    """Today's steps in order, then Endless."""
    due, new = progress.due_cards(decks, lessons), progress.new_cards(decks, lessons)
    todays = todays_drills(progress, drill_list)
    review = review_tasks(progress, lessons)
    nxt = progress.next_lesson(lessons)
    lesson_done = progress.lesson_today()
    golf_done = progress.vimgolf_done_today()
    best = progress.endless_best()
    if nxt is None:
        lesson_detail = "all done"
    elif lesson_done:
        lesson_detail = f"done today · next W{nxt.week} D{nxt.day}"
    else:
        lesson_detail = f"W{nxt.week} D{nxt.day} · {nxt.title}"
    return [
        Step("cards", "Cards", f"{len(due)} due · {len(new)} new" if due or new else "done",
             bool(due or new), minutes((len(due) + len(new)) * CARD_SECONDS)),
        Step("drills", "Drills", plural(len(todays), "drill") if todays else "done",
             bool(todays), minutes(len(todays) * DRILL_SECONDS)),
        Step("review", "Review", plural(len(review), "task") if review else "nothing due",
             bool(review), minutes(len(review) * REVIEW_TASK_SECONDS)),
        Step("lesson", "Lesson", lesson_detail, nxt is not None and not lesson_done,
             lesson_minutes(nxt) if nxt and not lesson_done else 0),
        Step("vimgolf", "VimGolf", "done" if golf_done else "optional · today's challenge",
             False if golf_done else None),
        Step("endless", "Endless", f"best level {best}" if best else "as long as you like", None),
    ]


def left(steps: list[Step]) -> list[Step]:
    """The routine steps still to do today."""
    return [s for s in steps if s.todo]
