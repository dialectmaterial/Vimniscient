"""Lessons the app puts together itself: review, placement, VimGolf and Endless."""



from typing import TYPE_CHECKING

from vimniscient import endless, vimgolf
from vimniscient.lessons import Lesson, Task

if TYPE_CHECKING:
    pass


ENDLESS_INTRO = (
    "Tasks from every lesson, one after another, for as long as you like. Each one you solve "
    "climbs a level. New lessons join the mix as you climb, and the key budget shrinks: about "
    "twice the reference at first, exactly the reference by level {ramp}.\n\n"
    "Go over the budget, `:Skip`, or ask for the answer, and it's a miss. A miss shows the answer, "
    "then you type it in with the keys shown (**Learn**). A couple of tasks later it comes back on "
    "another text, from memory (**Recall**). `:q` stops; your level is kept, and the next run starts "
    "{below} levels below it."
)


def endless_lesson(start: int, best: int) -> Lesson:
    record = f" Your best is level **{best}**." if best else ""
    return Lesson(
        id="endless",
        week=0,
        day=0,
        title="Endless",
        intro=f"**Starting at level {start}.**{record}\n\n"
        + ENDLESS_INTRO.format(ramp=endless.RAMP, below=endless.RESTART_BELOW),
        keys=[],
        tasks=[],
    )


def review_lesson(tasks: list[Task]) -> Lesson:
    return Lesson(
        id="review",
        week=0,
        day=0,
        title="Review",
        intro="Tasks from earlier days that are due again. Spaced repetition brings each one back "
        "just before you'd forget it, sooner when it went badly and later when it went well.",
        keys=[],
        tasks=tasks,
    )


def vimgolf_lesson(challenge: vimgolf.Challenge) -> Lesson:
    best = challenge.best
    # The runner finishes by itself, so the reference is the best score minus saving (ZZ).
    ref = max(1, best - vimgolf.SAVE_KEYS) if best else None
    best_text = (
        f"The best score on vimgolf.com is **{best}** ({challenge.entries} entries). VimGolf scores "
        f"include `ZZ` to save, so your score is your keys + {vimgolf.SAVE_KEYS}."
        if best
        else ""
    )
    task = Task(
        goal=f"VimGolf: {challenge.title}",
        start=challenge.start,
        cursor=(1, 0),
        target=challenge.target,
        solution="—",
        hint="No hints in VimGolf. Other people's solutions are on vimgolf.com; the link is on the results screen.",
        ft="",
        lesson_id="vimgolf",
        ref_override=ref,
    )
    return Lesson(
        id="vimgolf",
        week=0,
        day=0,
        title=f"VimGolf: {challenge.title}",
        intro=f"Today's challenge from [vimgolf.com]({challenge.url}): make the text match, in as few "
        f"keystrokes as you can. {best_text}",
        keys=[],
        tasks=[task],
    )


def placement_lesson(lessons: list[Lesson]) -> Lesson:
    """The first and last task of every lesson except the weekly reviews."""
    tasks = [t for lesson in lessons if not lesson.review for t in (lesson.tasks[0], lesson.tasks[-1])]
    return Lesson(
        id="placement",
        week=0,
        day=0,
        title="Placement test",
        intro="Two tasks from every lesson, so you can skip what you already know. A lesson counts "
        "as known when you solve both of its tasks without `:Hint` and in at most about 1.5× the "
        "reference keystrokes. Don't guess: `:Skip` whatever you don't know. That's what the "
        "test is for.",
        keys=[],
        tasks=tasks,
    )
