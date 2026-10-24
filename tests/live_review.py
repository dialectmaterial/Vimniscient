"""Run a review session (tasks without round labels, as review, placement and
VimGolf have) through the real runner, skipping one task: it has to come back
as a Learn copy and again at the end. Runs in a hidden tmux session.

    uv run python tests/live_review.py
"""

import os
import sqlite3
import sys
import tempfile
import time

from live_endless import SESSION, tmux, type_keys

from vimniscient.lessons import load_lessons

lessons = {lesson.id: lesson for lesson in load_lessons()}
tasks = [lessons["w1d2-pairs"].tasks[0].version(1), lessons["w1d4-find"].tasks[1], lessons["w1d5-lines"].tasks[0]]
skipped = tasks[1]
plan = [(tasks[0], "solved"), (skipped, "skipped"), (skipped.as_phase("learn"), "solved"),
        (tasks[2], "solved"), (skipped.next_version(), "solved")]

SCRIPT = """
from vimniscient.app import review_lesson
from vimniscient.lessons import load_lessons
from vimniscient.progress import Progress
from vimniscient.session import run_lesson
lessons = {lesson.id: lesson for lesson in load_lessons()}
tasks = [lessons["w1d2-pairs"].tasks[0].version(1), lessons["w1d4-find"].tasks[1], lessons["w1d5-lines"].tasks[0]]
Progress().record(run_lesson(review_lesson(tasks), retry=True))
"""

with tempfile.TemporaryDirectory() as data:
    script = os.path.join(data, "review.py")
    with open(script, "w") as f:
        f.write(SCRIPT)
    tmux("kill-session", "-t", SESSION)
    tmux("new-session", "-d", "-s", SESSION, "-x", "120", "-y", "32",
         f"VIMNISCIENT_DATA={data} {sys.executable} {script} 2>{data}/err; sleep 5")
    time.sleep(3.5)
    for task, outcome in plan:
        type_keys(":Skip<CR>" if outcome == "skipped" else task.solution)
    time.sleep(1)
    screen = tmux("capture-pane", "-pt", SESSION)
    tmux("kill-session", "-t", SESSION)
    db = sqlite3.connect(os.path.join(data, "progress.db"))
    rows = db.execute("SELECT lesson, task, status, phase FROM attempts ORDER BY id").fetchall()

problems = 0
for i, (task, outcome) in enumerate(plan):
    want = (task.lesson_id, task.index, outcome, task.phase)
    got = rows[i] if i < len(rows) else None
    problems += got != want
    print(f"{'ok  ' if got == want else 'FAIL'} want {want} got {got}")
problems += len(rows) != len(plan)
if problems and "Error" in screen:
    print(screen)
print(f"{problems} problems")
sys.exit(1 if problems else 0)
