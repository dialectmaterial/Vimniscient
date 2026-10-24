"""Skip a Recall task in a real lesson and check what follows: the answer
typed once with the keys shown (Learn), then the task again on its next text
at the end. Runs `vimniscient run` in a hidden tmux session.

    uv run python tests/live_retry.py [lesson id]
"""

import os
import sqlite3
import sys
import tempfile
import time

from live_endless import SESSION, tmux, type_keys

from vimniscient.lessons import load_lessons, two_rounds

lesson_id = sys.argv[1] if len(sys.argv) > 1 else "w1d1-words"
lesson = next(lesson for lesson in load_lessons() if lesson.id == lesson_id)
session = two_rounds(lesson)
n = len(lesson.tasks)
skipped = session[n]  # the first Recall task
plan = [(t, "solved") for t in session[:n]]
plan += [(skipped, "skipped"), (skipped.as_phase("learn"), "solved")]
plan += [(t, "solved") for t in session[n + 1:]]
plan += [(skipped.next_version(), "solved")]

with tempfile.TemporaryDirectory() as data:
    tmux("kill-session", "-t", SESSION)
    tmux("new-session", "-d", "-s", SESSION, "-x", "120", "-y", "32",
         f"VIMNISCIENT_DATA={data} vimniscient run {lesson.id}; sleep 5")
    time.sleep(3.5)
    for task, outcome in plan:
        type_keys(":Skip<CR>" if outcome == "skipped" else task.solution)
    time.sleep(1)
    tmux("kill-session", "-t", SESSION)
    db = sqlite3.connect(os.path.join(data, "progress.db"))
    rows = db.execute("SELECT task, status, phase, count, ref FROM attempts ORDER BY id").fetchall()

problems = 0
for i, (task, outcome) in enumerate(plan):
    got = rows[i][:3] if i < len(rows) else None
    want = (task.index, outcome, task.phase)
    ok = got == want and (outcome != "solved" or rows[i][3] == rows[i][4])
    problems += not ok
    print(f"{'ok  ' if ok else 'FAIL'} want {want} got {rows[i] if i < len(rows) else None}")
problems += len(rows) != len(plan)
print(f"{problems} problems")
sys.exit(1 if problems else 0)
