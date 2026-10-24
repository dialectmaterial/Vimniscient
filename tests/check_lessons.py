"""Check that every lesson loads and every reference solution reaches its target.

    uv run python tests/check_lessons.py            # plain Vim lessons, in nvim --clean
    uv run python tests/check_lessons.py --lazyvim  # LazyVim lessons, in your own config
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from vimniscient.lessons import load_lessons

lazyvim = "--lazyvim" in sys.argv
lessons = [lesson for lesson in load_lessons() if lesson.lazyvim == lazyvim]
already = [f"{lesson.id}#{i}" for lesson in lessons for i, t in enumerate(lesson.tasks, 1) if t.start == t.target]
if already:
    sys.exit(f"tasks that start out solved: {', '.join(already)}")
tasks = [
    {
        "id": f"{lesson.id}#{i}",
        "goal": t.goal,
        "start": t.start,
        "cursor": list(t.cursor),
        "target": t.target,
        "solution": t.solution,
        "ft": t.ft,
    }
    for lesson in lessons
    for i, t in enumerate(lesson.tasks, 1)
]
script = Path(__file__).with_name("check_lessons.lua")
with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
    json.dump(tasks, f)
    f.flush()
    if lazyvim:
        with tempfile.TemporaryDirectory() as cwd:
            cmd = ["nvim", "--headless", "-i", "NONE", "-n", "-S", str(script)]
            env = os.environ | {"VIMNISCIENT_TASKS": f.name, "VIMNISCIENT_LAZY": "1"}
            code = subprocess.run(cmd, env=env, cwd=cwd, stderr=subprocess.DEVNULL).returncode
    else:
        cmd = ["nvim", "--clean", "--headless", "-l", str(script), f.name]
        code = subprocess.run(cmd, stderr=subprocess.DEVNULL).returncode
print(f"{len(lessons)} lessons")
sys.exit(code)
