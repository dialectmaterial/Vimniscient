"""Generated practice texts: the same seed gives the same task, and the
reference solution reaches the target in Neovim, for many seeds of every kind.

    uv run python tests/check_generate.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from vimniscient.generate import KINDS, generate
from vimniscient.lessons import load_lessons

SEEDS = 150
parent = load_lessons()[0].tasks[0]
problems = []
tasks = []
for kind in KINDS:
    made = [generate(kind, str(n), parent) for n in range(SEEDS)]
    if generate(kind, "7", parent) != made[7]:
        problems.append(f"{kind}: seed 7 gave two different tasks")
    if any(t.start == t.target for t in made):
        problems.append(f"{kind}: a task that starts out solved")
    distinct = len({tuple(t.start) for t in made})
    print(f"{kind}: {distinct} different texts from {SEEDS} seeds")
    if distinct < SEEDS // 3:
        problems.append(f"{kind}: only {distinct} different texts")
    tasks += [{"id": f"{kind} seed {n}", "goal": t.goal, "start": t.start, "cursor": list(t.cursor),
               "target": t.target, "solution": t.solution, "ft": t.ft} for n, t in enumerate(made)]

# every lesson task that names a kind gets one in Recall and in reviews
for lesson in load_lessons():
    for t in lesson.tasks:
        if t.generator and t.generator not in KINDS:
            problems.append(f"{t.item_id}: no generator called {t.generator}")
        if t.generator and not t.choice(t.versions, "x").generated:
            problems.append(f"{t.item_id}: the last choice isn't generated")

script = Path(__file__).with_name("check_lessons.lua")
with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
    json.dump(tasks, f)
    f.flush()
    run = subprocess.run(["nvim", "--clean", "--headless", "-l", str(script), f.name],
                         capture_output=True, text=True)
print(run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr)
if run.returncode:
    problems.append("some generated tasks don't reach their target")
    print(run.stdout)
for p in problems:
    print("FAIL", p)
print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
