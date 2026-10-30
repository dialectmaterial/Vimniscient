"""Quick practice: a minute or two on one skill, whenever there's time.

Tasks come from the lessons you've done, on any of their texts, or for
navigation from the generators. Like Endless, it counts for the streak and
grades nothing.
"""

import random

from vimniscient.lessons import SKILLS, Lesson, Task

MINUTES = (1, 2, 5)
DEFAULT_MINUTES = 2
TASK_SECONDS = 12.0  # until there's a timed history to go by
NAVIGATION = "navigation"
ANY = "any"
NAV_KINDS = ("nav-down", "nav-up", "nav-find")
TITLES = {NAVIGATION: "Navigation", ANY: "Any skill", "text-objects": "Text objects", "ex": "Ex commands"}


def title(skill: str) -> str:
    return TITLES.get(skill, skill.capitalize())


def pools(lessons: list[Lesson], done: set[str]) -> dict[str, list[Task]]:
    """The tasks each skill can draw on, skills with nothing done yet left out."""
    finished = [lesson for lesson in lessons if lesson.id in done]
    found = {ANY: [t for lesson in finished for t in lesson.tasks]}
    for skill in SKILLS:
        found[skill] = [t for lesson in finished if lesson.skill == skill for t in lesson.tasks]
    return {skill: tasks for skill, tasks in found.items() if tasks}


def how_many(minutes: int, typical: float | None) -> int:
    return max(2, round(minutes * 60 / (typical or TASK_SECONDS)))


def build(skill: str, count: int, found: dict[str, list[Task]], parent: Task, seed: object) -> list[Task]:
    return navigation(count, parent, seed) if skill == NAVIGATION else tasks(found[skill], count, seed)


def navigation(count: int, parent: Task, seed: object) -> list[Task]:
    rng = random.Random(f"nav:{seed}")
    return [parent.generate_kind(rng.choice(NAV_KINDS), f"{seed}:{n}") for n in range(count)]


def tasks(pool: list[Task], count: int, seed: object) -> list[Task]:
    """`count` tasks from `pool`, each on a random text; repeats only once all have come up."""
    rng = random.Random(f"quick:{seed}")
    order: list[Task] = []
    while len(order) < count:
        order += rng.sample(pool, len(pool))
    return [t.choice(rng.randrange(t.choices), f"{t.item_id}:{seed}:{n}") for n, t in enumerate(order[:count])]
