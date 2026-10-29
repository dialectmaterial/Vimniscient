"""Task timing: an old progress database gains the seconds/first columns with
its attempts left unknown (NULL), and new attempts store their times.

    uv run python tests/check_timing.py
"""

import os
import sqlite3
import sys
import tempfile

data = tempfile.mkdtemp()
os.environ["VIMNISCIENT_DATA"] = data

# a database from before timing (and before the Learn/Recall rounds)
old = sqlite3.connect(os.path.join(data, "progress.db"))
old.execute("""CREATE TABLE attempts (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, lesson TEXT NOT NULL,
    task INTEGER NOT NULL, status TEXT NOT NULL, count INTEGER NOT NULL, ref INTEGER NOT NULL,
    keys TEXT NOT NULL, hints INTEGER NOT NULL)""")
old.execute("INSERT INTO attempts (ts, lesson, task, status, count, ref, keys, hints) "
            "VALUES ('2026-10-24T10:00:00', 'w1d1-words', 0, 'solved', 3, 3, 'ciw', 0)")
old.commit()
old.close()

from vimniscient.lessons import load_lessons  # noqa: E402 (after VIMNISCIENT_DATA)
from vimniscient.progress import Progress  # noqa: E402
from vimniscient.session import TaskResult  # noqa: E402

problems = []


def check(what: str, got, want) -> None:
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {what}: {got!r}" + ("" if ok else f", want {want!r}"))
    if not ok:
        problems.append(what)


progress = Progress()
columns = [row[1] for row in progress.db.execute("PRAGMA table_info(attempts)")]
check("columns added", [c for c in ("phase", "seconds", "first") if c in columns], ["phase", "seconds", "first"])
check("old attempt untimed", progress.db.execute("SELECT seconds, first, phase FROM attempts").fetchone(),
      (None, None, "recall"))

task = load_lessons()[0].tasks[0]
progress.record([
    TaskResult(task, "solved", task.solution, task.ref, 0, seconds=4.25, first=1.5),
    TaskResult(task.as_phase("learn"), "solved", task.solution, task.ref, 0),  # no time sent: unknown
])
check("new attempts", progress.db.execute("SELECT seconds, first FROM attempts WHERE id > 1 ORDER BY id").fetchall(),
      [(4.25, 1.5), (None, None)])
check("opening it again", Progress().db.execute("SELECT COUNT(*) FROM attempts").fetchone(), (3,))

print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
