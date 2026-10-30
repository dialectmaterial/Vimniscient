"""Today's routine, without the interface: which steps are left and roughly how
long each takes. The main screen shows it; the reminders read it.

The routine fits a daily budget (settings.minutes(), 15 by default), less what
you've practised today already. The next lesson comes first, then due reviews,
due cards, drills and new cards, as far as the time goes. What doesn't fit stays
due and comes tomorrow; a few due reviews and cards always come along, so the
backlog doesn't grow while lessons fill the budget."""

import math
from dataclasses import dataclass

from vimniscient import drills, habits, settings, transfer
from vimniscient.cards import Card, Deck
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
# Even when the lesson takes up the budget, this much review comes along.
MIN_DUE_CARDS = 5
MIN_REVIEW_TASKS = 2


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


def review_tasks(progress: Progress, lessons: list[Lesson], limit: int | None = None) -> list[Task]:
    due = progress.due_tasks(lessons, limit=limit)
    return due + habit_tasks(progress, lessons, due)


def lesson_minutes(lesson: Lesson, task_seconds: float = LESSON_TASK_SECONDS) -> int:
    return minutes(len(lesson.tasks) * 2 * task_seconds + LESSON_READING_SECONDS)


@dataclass
class Work:
    """What today's routine holds, after the budget: the cards, drills and review
    tasks to do, and how many are due in all (the rest wait for tomorrow)."""

    cards: list[Card]
    drills: list[drills.Drill]
    review: list[Task]
    lesson: Lesson | None
    due_cards: int
    due_review: int
    due_drills: int
    new_cards: int  # of `cards`, the new ones
    seconds: dict[str, float]  # about how long each step takes
    budget: float  # seconds left of today's budget, before this work


def todays_work(progress: Progress, lessons: list[Lesson], decks: dict[str, Deck], drill_list: list[drills.Drill],
                budget_minutes: int | None = None) -> Work:
    task_seconds = progress.typical_task_seconds()
    lesson_task = task_seconds or LESSON_TASK_SECONDS
    review_task = task_seconds * 1.3 if task_seconds else REVIEW_TASK_SECONDS  # no keys shown, so slower
    budget = max(0.0, (budget_minutes or settings.minutes()) * 60
                 - progress.seconds_today(CARD_SECONDS, lesson_task))

    due_cards = progress.due_cards(decks, lessons, limit=None)
    new_cards = progress.new_cards(decks, lessons)
    review = review_tasks(progress, lessons, limit=None)
    todays_drills_ = todays_drills(progress, drill_list)
    nxt = progress.next_lesson(lessons)
    lesson = nxt if nxt and not progress.lesson_today() else None  # one a day, budget or not

    left = budget
    if lesson:
        left -= len(lesson.tasks) * 2 * lesson_task + LESSON_READING_SECONDS
    take = {"review": 0, "due": 0, "drills": 0, "new": 0}
    if budget > 0:  # a little review always, then whatever fits
        take["review"] = min(MIN_REVIEW_TASKS, len(review))
        take["due"] = min(MIN_DUE_CARDS, len(due_cards))
        left -= take["review"] * review_task + take["due"] * CARD_SECONDS
        for key, items, cost in (("review", review, review_task), ("due", due_cards, CARD_SECONDS),
                                 ("drills", todays_drills_, DRILL_SECONDS), ("new", new_cards, CARD_SECONDS)):
            fits = max(0, int(left // cost))
            extra = min(fits, len(items) - take[key])
            take[key] += extra
            left -= extra * cost
    cards = due_cards[: take["due"]] + new_cards[: take["new"]]
    return Work(
        cards=cards,
        drills=todays_drills_[: take["drills"]],
        review=review[: take["review"]],
        lesson=lesson,
        due_cards=len(due_cards),
        due_review=len(review),
        due_drills=len(todays_drills_),
        new_cards=take["new"],
        seconds={
            "cards": len(cards) * CARD_SECONDS,
            "drills": take["drills"] * DRILL_SECONDS,
            "review": take["review"] * review_task,
            "lesson": len(lesson.tasks) * 2 * lesson_task + LESSON_READING_SECONDS if lesson else 0,
        },
        budget=budget,
    )


def plan(progress: Progress, lessons: list[Lesson], decks: dict[str, Deck], drill_list: list[drills.Drill],
         work: Work | None = None) -> list[Step]:
    """Today's steps in order, then Endless."""
    work = work or todays_work(progress, lessons, decks, drill_list)
    nxt = progress.next_lesson(lessons)
    lesson_done = progress.lesson_today()
    golf_done = progress.vimgolf_done_today()
    best = progress.endless_best()
    picks = transfer.pick(lessons, progress)
    if nxt is None:
        lesson_detail = "all done"
    elif lesson_done:
        lesson_detail = f"done today · next W{nxt.week} D{nxt.day}"
    else:
        lesson_detail = f"W{nxt.week} D{nxt.day} · {nxt.title}"
    due_taken = len(work.cards) - work.new_cards
    if work.cards:
        due = (f"{due_taken} of {work.due_cards} due" if due_taken < work.due_cards else f"{due_taken} due")
        cards_detail = f"{due} · {work.new_cards} new"
    else:
        cards_detail = f"done · {work.due_cards} wait for tomorrow" if work.due_cards else "done"
    if work.review:
        review_detail = (f"{len(work.review)} of {work.due_review} tasks" if len(work.review) < work.due_review
                         else plural(len(work.review), "task"))
    else:
        review_detail = f"done · {work.due_review} wait for tomorrow" if work.due_review else "nothing due"
    return [
        Step("cards", "Cards", cards_detail, bool(work.cards), minutes(work.seconds["cards"])),
        Step("drills", "Drills", plural(len(work.drills), "drill") if work.drills
             else f"{plural(work.due_drills, 'drill')} wait for tomorrow" if work.due_drills else "done",
             bool(work.drills), minutes(work.seconds["drills"])),
        Step("review", "Review", review_detail, bool(work.review), minutes(work.seconds["review"])),
        Step("lesson", "Lesson", lesson_detail, work.lesson is not None, minutes(work.seconds["lesson"])),
        Step("vimgolf", "VimGolf", "done" if golf_done else "optional · today's challenge",
             False if golf_done else None),
        Step("quick", "Quick", "optional · 1, 2 or 5 minutes", None),
        Step("transfer", "Choose", f"optional · {len(picks)} tasks, your keys" if picks else "opens after Week 1 · Day 2", None),
        Step("endless", "Endless", f"best level {best}" if best else "as long as you like", None),
    ]


def left(steps: list[Step]) -> list[Step]:
    """The routine steps still to do today."""
    return [s for s in steps if s.todo]
