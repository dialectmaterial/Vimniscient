"""Running a lesson in the user's own Neovim (see nvim/runner.lua)."""

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from vimniscient.lessons import Lesson, Task
from vimniscient.missions import Mission
from vimniscient.mnemonics import hooks

# The app's theme colours (hex), so lessons look like the rest of it; set by the app.
COLORS: dict[str, str] = {}


@dataclass
class TaskResult:
    task: Task
    status: str  # solved | failed (endless) | skipped | quit | unseen
    keys: str
    count: int
    hints: int
    level: int = 0  # endless mode: the level the task was given at
    budget: int | None = None  # endless mode: the most keys allowed
    seconds: float | None = None  # from the task appearing to it ending; None when not timed
    first: float | None = None  # before the first key


def mouse_wheel(on: bool) -> None:
    """With the mouse off, terminals like foot turn the wheel into arrow keys (alternate
    scroll mode, DECSET 1007): it would scroll lists, and type arrows into lessons.
    Off while Vimniscient runs, Neovim included; back on when it quits."""
    if sys.__stdout__ and sys.__stdout__.isatty():
        sys.__stdout__.write("\x1b[?1007h" if on else "\x1b[?1007l")
        sys.__stdout__.flush()


def task_json(t: Task) -> dict:
    return {
        "goal": t.goal,
        "start": t.start,
        "cursor": list(t.cursor),
        "target": t.target,
        "ref": t.ref,
        "hint": t.hint,
        "solution": t.solution,
        "ft": t.ft,
        "phase": t.phase,
        "why": hooks(t.solution) if t.solution != "—" else [],  # what the keys stand for
    }


def run_nvim(session: dict, first: list[str]) -> list[dict]:
    """Start Neovim with the runner on `session`; returns the raw results it wrote."""
    runner = resources.files("vimniscient") / "nvim" / "runner.lua"
    with tempfile.TemporaryDirectory(prefix="vimniscient-") as tmp, resources.as_file(runner) as runner_path:
        tmp_path = Path(tmp)
        session_path = tmp_path / "session.json"
        result_path = tmp_path / "results.json"
        practice = tmp_path / "practice.txt"
        practice.write_text("\n".join(first), encoding="utf-8")
        session_path.write_text(json.dumps(session | {"result_path": str(result_path), "colors": COLORS or None}), encoding="utf-8")
        # cwd=tmp keeps session plugins away from the user's real projects;
        # -i NONE gives every lesson clean registers and history.
        mouse_wheel(False)  # the runner turns the mouse off; this keeps the wheel from typing arrows
        try:
            subprocess.run(
                ["nvim", "-i", "NONE", str(practice), "-S", str(runner_path)],
                cwd=tmp,
                env=os.environ | {"VIMNISCIENT_SESSION": str(session_path)},
            )
        finally:
            mouse_wheel(True)
        return json.loads(result_path.read_text()) if result_path.exists() else []


def run_mission(mission: Mission) -> TaskResult:
    """A mission in your own Neovim, on throwaway files in a folder of their own."""
    script = resources.files("vimniscient") / "nvim" / "mission.lua"
    with tempfile.TemporaryDirectory(prefix="vimniscient-") as tmp, resources.as_file(script) as script_path:
        root = Path(tmp)
        work = root / "project"  # the session file stays out of the project your plugins see
        work.mkdir()
        for name, text in mission.files.items():
            (work / name).write_text(text, encoding="utf-8")
        result_path = root / "result.json"
        session_path = root / "session.json"
        session_path.write_text(json.dumps({
            "goal": mission.goal, "hint": mission.hint, "result_path": str(result_path),
            "targets": {name: text.splitlines() for name, text in mission.targets.items()},
        }), encoding="utf-8")
        mouse_wheel(False)
        try:
            subprocess.run(["nvim", "-i", "NONE", next(iter(mission.files)), "-S", str(script_path)], cwd=work,
                           env=os.environ | {"VIMNISCIENT_MISSION": str(session_path)})
        finally:
            mouse_wheel(True)
        raw = json.loads(result_path.read_text()) if result_path.exists() else {"status": "quit", "keys": "", "count": 0}
    return TaskResult(mission.task, raw["status"], raw["keys"], raw["count"], raw.get("hints", 0),
                      seconds=raw.get("seconds"), first=raw.get("first"))


def run_lesson(lesson: Lesson, retry: bool = False) -> list[TaskResult]:
    """With `retry`, a skipped Recall task is shown, typed once with the keys
    shown, and asked again on its next text at the end (see runner.lua)."""
    totals = {phase: sum(t.phase == phase for t in lesson.tasks) for phase in ("learn", "recall")}
    seen = {"learn": 0, "recall": 0}
    tasks = []
    for n, t in enumerate(lesson.tasks):
        seen[t.phase] += 1
        two_rounds = totals["learn"] > 0
        tasks.append(
            task_json(t)
            | {
                "n": n,
                "label": f"{t.phase.upper()} {seen[t.phase]}/{totals[t.phase]}" if two_rounds else None,
                "show": t.solution if t.phase == "learn" else "",
            }
            | ({"again": task_json(t.next_version())} if retry and t.phase == "recall" else {})
        )
    raw = run_nvim({"title": f"{lesson.label} · {lesson.title}" if lesson.week else lesson.title, "tasks": tasks, "retry": retry}, lesson.tasks[0].start)
    if not raw:  # Neovim never got going: every task unseen
        raw = [{"n": n} for n in range(len(lesson.tasks))]
    results = []
    for r in raw:
        task = lesson.tasks[r["n"]]
        if r.get("extra") == "learn":
            task = task.as_phase("learn")
        elif r.get("extra") == "recall":
            task = task.next_version().as_phase("recall")
        results.append(
            TaskResult(
                task=task,
                status=r.get("status", "unseen"),
                keys=r.get("keys", ""),
                count=r.get("count", 0),
                hints=r.get("hints", 0),
                seconds=r.get("seconds"),
                first=r.get("first"),
            )
        )
    return results


def run_endless(pool: dict[str, Task], rungs: list[tuple[str, int]], level: int, ramp: int, gap: int) -> list[TaskResult]:
    """Endless mode: the runner climbs `rungs` (task id, version) from `level` on,
    and slots in a Learn and a Recall for every task missed (see endless.py)."""
    today = date.today().isoformat()  # a task's generated text is new each day, and the same all run
    session = {
        "title": "Endless",
        "tasks": [],
        "endless": {
            "pool": {item_id: [task_json(task.choice(v, f"{item_id}:{today}")) for v in range(task.choices)]
                     for item_id, task in pool.items()},
            "rungs": [{"id": item_id, "v": v} for item_id, v in rungs],
            "level": level,
            "ramp": ramp,
            "gap": gap,
        },
    }
    item_id, v = rungs[0]
    raw = run_nvim(session, pool[item_id].choice(v, f"{item_id}:{today}").start)
    return [
        TaskResult(
            task=pool[r["id"]].choice(r["v"], f"{r['id']}:{today}").as_phase(r["phase"]),
            status=r["status"],
            keys=r["keys"],
            count=r["count"],
            hints=r["hints"],
            level=r["level"],
            budget=r.get("budget"),
            seconds=r.get("seconds"),
            first=r.get("first"),
        )
        for r in raw
        if r.get("id") in pool and r["status"] != "unseen"
    ]
