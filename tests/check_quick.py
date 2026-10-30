"""Quick practice: the right tasks, on any text, for the time you have, and ungraded.

    uv run python tests/check_quick.py
"""

import os
import sys
import tempfile

os.environ["VIMNISCIENT_DATA"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from vimniscient import quick  # noqa: E402
from vimniscient.lessons import load_lessons  # noqa: E402
from vimniscient.progress import Progress  # noqa: E402
from vimniscient.session import TaskResult  # noqa: E402

lessons = load_lessons()
problems = []


def check(what: str, ok: bool, detail: object = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {what}" + (f": {detail}" if not ok else ""))
    if not ok:
        problems.append(what)


check("nothing done, no skills", quick.pools(lessons, set()) == {})
done = {lesson.id for lesson in lessons[:9]}
pools = quick.pools(lessons, done)
check("a skill only draws on done lessons", all(t.lesson_id in done for tasks in pools.values() for t in tasks))
check("macros aren't open yet", "macros" not in pools, list(pools))
check("a minute at 12s a task is five", quick.how_many(1, None) == 5, quick.how_many(1, None))
check("your own speed counts", quick.how_many(5, 30.0) == 10)
check("always at least two", quick.how_many(1, 300.0) == 2)
picked = quick.tasks(pools["repeats"], 12, "s")
check("more tasks than the pool: all used", {t.index for t in picked} == {t.index for t in pools["repeats"]} and len(picked) == 12)
check("the same seed, the same tasks", [t.goal for t in quick.tasks(pools["repeats"], 12, "s")] == [t.goal for t in picked])
nav = quick.navigation(10, lessons[0].tasks[0], "s")
check("navigation has a # to find", all("#" in "".join(t.start) and "#" not in "".join(t.target) for t in nav))
p = Progress()
p.record_ungraded([TaskResult(nav[0], "solved", nav[0].solution, nav[0].ref, 0, seconds=3.0, first=1.0)], "quick")
check("recorded, for the streak", p.streak() == 1)
check("graded nothing", p.db.execute("SELECT COUNT(*) FROM items").fetchone() == (0,))

print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
