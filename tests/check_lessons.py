"""Check that every lesson loads and every reference solution reaches its target.

    uv run python tests/check_lessons.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from vimniscient.lessons import load_lessons

lessons = load_lessons()
tasks = [
    {
        "id": f"{lesson.id}#{i}",
        "goal": t.goal,
        "start": t.start,
        "cursor": list(t.cursor),
        "target": t.target,
        "solution": t.solution,
    }
    for lesson in lessons
    for i, t in enumerate(lesson.tasks, 1)
]
with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
    json.dump(tasks, f)
    f.flush()
    script = Path(__file__).with_name("check_lessons.lua")
    code = subprocess.run(["nvim", "--clean", "--headless", "-l", str(script), f.name], stderr=subprocess.DEVNULL).returncode
print(f"{len(lessons)} lessons")
sys.exit(code)
