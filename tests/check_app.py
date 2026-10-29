"""Every screen of the app, driven headless (no Neovim, no desktop): it opens,
shows what it should, and the keys that move between screens work.

    uv run python tests/check_app.py
"""

import asyncio
import os
import sys
import tempfile

os.environ["VIMNISCIENT_DATA"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from dataclasses import replace  # noqa: E402

from textual.widgets import Static  # noqa: E402

from vimniscient.app import CardScreen, LessonScreen, MainScreen, ResultsScreen, StatsScreen, VimniscientApp  # noqa: E402
from vimniscient.lessons import two_rounds  # noqa: E402
from vimniscient.session import TaskResult  # noqa: E402

problems = []


def check(what: str, ok: bool, detail: object = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {what}" + (f": {detail}" if not ok and detail != "" else ""))
    if not ok:
        problems.append(what)


def text(screen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())


async def main() -> None:
    app = VimniscientApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        check("opens on the main screen", isinstance(app.screen, MainScreen), type(app.screen).__name__)
        steps = [s.id for s in app.plan()]
        check("Today lists the routine", steps[:4] == ["cards", "drills", "review", "lesson"], steps)

        await pilot.press("s")
        await pilot.pause(0.3)
        check("s opens stats", isinstance(app.screen, StatsScreen), type(app.screen).__name__)
        await pilot.press("escape")
        await pilot.pause(0.2)
        check("esc goes back", isinstance(app.screen, MainScreen), type(app.screen).__name__)

        await pilot.press("c")
        await pilot.pause(0.3)
        check("c opens cards", isinstance(app.screen, CardScreen), type(app.screen).__name__)
        if isinstance(app.screen, CardScreen):
            card = app.screen.queue[0]
            check("a first card is introduced, answer shown", app.screen.intro and card.shown in text(app.screen, "#card-feedback"))
            await pilot.press("x", "enter")
            await pilot.pause(0.2)
            check("a wrong copy asks again", app.screen.pending is None and "type it as shown" in text(app.screen, "#card-feedback"))
            for key in card.answers[0]:
                await pilot.press(key)
            await pilot.press("enter")
            await pilot.pause(0.2)
            check("the right copy is taken", app.screen.pending is not None)
            await pilot.press("escape")
            await pilot.pause(0.2)
        check("cards close", isinstance(app.screen, MainScreen), type(app.screen).__name__)

        lesson = app.lessons[0]
        app.push_screen(LessonScreen(lesson))
        await pilot.pause(0.3)
        check("a lesson's intro opens", isinstance(app.screen, LessonScreen))
        await pilot.press("escape")
        await pilot.pause(0.2)

        tasks = two_rounds(lesson)
        results = [TaskResult(t, "solved" if i != 8 else "skipped", t.solution, t.ref, 0, seconds=4.0, first=1.0)
                   for i, t in enumerate(tasks)]
        app.push_screen(ResultsScreen(replace(lesson, tasks=tasks), results))
        await pilot.pause(0.3)
        check("results open", isinstance(app.screen, ResultsScreen))
        summary = text(app.screen, "#results-summary")
        check("results say how it went", summary.startswith("5 of 6 recalled") and "4.0s a task" in summary, summary)
        check("results explain a missed task", bool(app.screen.query("#results-why")))
        await pilot.press("enter")
        await pilot.pause(0.2)
        check("results close", isinstance(app.screen, MainScreen), type(app.screen).__name__)

        await pilot.press("e")
        await pilot.pause(0.3)
        check("e opens endless's intro", isinstance(app.screen, LessonScreen) and app.screen.lesson.id == "endless")
        await pilot.press("escape")
        await pilot.pause(0.2)

        await pilot.press("p")
        await pilot.pause(0.3)
        check("p opens the placement test", isinstance(app.screen, LessonScreen) and app.screen.lesson.id == "placement")
        await pilot.press("escape")
        await pilot.pause(0.2)
        check("and back", isinstance(app.screen, MainScreen), type(app.screen).__name__)


asyncio.run(main())
print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
