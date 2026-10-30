"""Placement: experienced and new profiles land where they should, in fewer
tasks than the old 62, and one skill's result never touches another's. Plus
the evaluation's texts, which every way must solve, and `doctor`.

    uv run python tests/check_placement.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["VIMNISCIENT_DATA"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from vimniscient import doctor, evaluation, placement  # noqa: E402
from vimniscient.lessons import load_lessons  # noqa: E402
from vimniscient.progress import Progress  # noqa: E402
from vimniscient.session import TaskResult  # noqa: E402

lessons = load_lessons()
problems = []


def check(what: str, ok: bool, detail: object = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {what}" + (f": {detail}" if not ok else ""))
    if not ok:
        problems.append(what)


def play(knows) -> tuple[placement.Search, int]:
    """A whole test by someone who knows the lessons `knows` says yes to."""
    search, asked = placement.Search(lessons, lazyvim=True), 0
    while not search.finished:
        tasks = search.round()
        asked += len(tasks)
        lookup = {lesson.id: lesson for lesson in lessons}
        search.update([TaskResult(t, "solved" if knows(lookup[t.lesson_id]) else "skipped", t.solution, t.ref, 0) for t in tasks])
    return search, asked


expert, asked = play(lambda lesson: True)
check("an expert needs far fewer than 62 tasks", asked < 40, asked)
check("an expert knows everything tested", {lesson.id for lesson in expert.known()} >= {lesson.id for lesson in lessons if lesson.skill != "mixed"})
beginner, asked = play(lambda lesson: False)
check("a beginner knows nothing", beginner.known() == [], beginner.known())
check("a beginner is done in fewer too", asked <= 40, asked)
macros, _ = play(lambda lesson: lesson.skill == "macros")
check("one skill never marks another", {lesson.skill for lesson in macros.known()} == {"macros"}, macros.known())
early, _ = play(lambda lesson: lesson.skill == "ex" and lesson.week == 3)
check("a skill stops where you do", [lesson.id for lesson in early.known()] == ["w3d6-substitute"], early.known())
p = Progress()
p.mark_known(macros.known(), set())
check("known lessons get skipped", p.is_done(macros.known()[0]))
check("and it can be undone", p.reset_placement() == 2 and not p.is_done(macros.known()[0]))

tasks = [{"id": f"{form} {i}: {way}", "goal": t["goal"], "start": evaluation.task(t, i).start, "cursor": list(evaluation.task(t, i).cursor),
          "target": evaluation.task(t, i).target, "solution": way, "ft": ""}
         for form, items in evaluation.forms().items() for i, t in enumerate(items) for way in t["ways"]]
with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
    json.dump(tasks, f)
    f.flush()
    run = subprocess.run(["nvim", "--clean", "--headless", "-l", str(Path(__file__).with_name("check_lessons.lua")), f.name],
                         capture_output=True, text=True)
print(run.stdout.strip())
check("every evaluation task solves", run.returncode == 0)
check("the forms match in size", len({len(items) for items in evaluation.forms().values()}) == 1)
check("no answers leak", all(t.solution == "—" for t in evaluation.lesson("pre").tasks))
p.record_ungraded([TaskResult(evaluation.lesson("pre").tasks[0], "solved", "D", 3, 0, seconds=4.0)], "eval-pre")
report = evaluation.report(p)
check("the report shows a sitting", "1/1" in report and "not taken yet: vimniscient eval post" in report, report)

names = [c.name for c in doctor.checks()]
check("doctor checks the basics", {"Neovim", "Your config", "Progress data"} <= set(names), names)
print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
