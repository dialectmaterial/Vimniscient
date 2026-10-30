"""Choose tasks: every way reaches the target in Neovim, each task has at least
two, what unlocks them exists, and they're recorded without grades.

    uv run python tests/check_transfer.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["VIMNISCIENT_DATA"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from vimniscient import transfer  # noqa: E402
from vimniscient.lessons import load_lessons  # noqa: E402
from vimniscient.progress import Progress  # noqa: E402
from vimniscient.session import TaskResult  # noqa: E402

problems = []
lessons = load_lessons()
ids = {lesson.id for lesson in lessons}
tasks = []
for c in transfer.challenges():
    if c.after not in ids:
        problems.append(f"{c.task.goal}: no lesson {c.after}")
    if len(set(c.ways)) < 2:
        problems.append(f"{c.task.goal}: only one way")
    tasks += [{"id": f"{c.task.index}: {way}", "goal": c.task.goal, "start": c.task.start, "cursor": list(c.task.cursor),
               "target": c.task.target, "solution": way, "ft": ""} for way in c.ways]

script = Path(__file__).with_name("check_lessons.lua")
with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
    json.dump(tasks, f)
    f.flush()
    run = subprocess.run(["nvim", "--clean", "--headless", "-l", str(script), f.name], capture_output=True, text=True)
print(run.stdout.strip())
if run.returncode:
    problems.append("some ways don't reach the target")

p = Progress()
if transfer.pick(lessons, p):
    problems.append("Choose is open before any lesson is done")
for lesson in lessons[:12]:
    p.db.execute("INSERT INTO placed (lesson, ts) VALUES (?, ?)", (lesson.id, "2026-10-01"))
p.db.commit()
first = transfer.pick(lessons, p)
if len(first) != transfer.PER_RUN:
    problems.append(f"picked {len(first)}")
items = p.db.execute("SELECT COUNT(*) FROM items").fetchone()
p.record_transfer([TaskResult(c.task, "solved", c.ways[0], c.task.ref, 0, seconds=3.0, first=1.0) for c in first])
if {c.task.index for c in transfer.pick(lessons, p)} & {c.task.index for c in first}:
    problems.append("the next run repeats tasks while untried ones wait")
if p.db.execute("SELECT COUNT(*) FROM items").fetchone() != items:
    problems.append("Choose graded something")
c = first[0]
if transfer.another_way(c, c.ways[0], True) != [c.ways[1]] or transfer.another_way(c, "", False) != c.ways:
    problems.append("another_way")

for problem in problems:
    print("FAIL", problem)
print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
