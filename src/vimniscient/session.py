"""Running a lesson in the user's own Neovim (see nvim/runner.lua)."""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from vimniscient.lessons import Lesson, Task


@dataclass
class TaskResult:
    task: Task
    status: str  # solved | skipped | quit | unseen
    keys: str
    count: int
    hints: int


def run_lesson(lesson: Lesson) -> list[TaskResult]:
    runner = resources.files("vimniscient") / "nvim" / "runner.lua"
    with tempfile.TemporaryDirectory(prefix="vimniscient-") as tmp, resources.as_file(runner) as runner_path:
        tmp_path = Path(tmp)
        session_path = tmp_path / "session.json"
        result_path = tmp_path / "results.json"
        practice = tmp_path / "practice.txt"
        practice.write_text("\n".join(lesson.tasks[0].start), encoding="utf-8")
        session_path.write_text(
            json.dumps(
                {
                    "title": f"{lesson.label}: {lesson.title}",
                    "result_path": str(result_path),
                    "tasks": [
                        {
                            "goal": t.goal,
                            "start": t.start,
                            "cursor": list(t.cursor),
                            "target": t.target,
                            "ref": t.ref,
                            "hint": t.hint,
                            "solution": t.solution,
                            "ft": t.ft,
                        }
                        for t in lesson.tasks
                    ],
                }
            ),
            encoding="utf-8",
        )
        # cwd=tmp keeps session plugins away from the user's real projects;
        # -i NONE gives every lesson clean registers and history.
        subprocess.run(
            ["nvim", "-i", "NONE", str(practice), "-S", str(runner_path)],
            cwd=tmp,
            env=os.environ | {"VIMNISCIENT_SESSION": str(session_path)},
        )
        raw = json.loads(result_path.read_text()) if result_path.exists() else []

    results = []
    for i, task in enumerate(lesson.tasks):
        r = raw[i] if i < len(raw) else {}
        results.append(
            TaskResult(
                task=task,
                status=r.get("status", "unseen"),
                keys=r.get("keys", ""),
                count=r.get("count", 0),
                hints=r.get("hints", 0),
            )
        )
    return results
