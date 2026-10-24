"""Play endless mode through the real runner (your LazyVim), in a hidden tmux
session, and check that a miss brings a Learn copy and later a Recall:

    rung 1 solved, rung 2 missed (over budget), its Learn copy solved,
    rungs 3 and 4 solved, then the Recall of rung 2 on its next text.

    uv run python tests/live_endless.py
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
import time

from vimniscient import endless
from vimniscient.cards import has_lazyvim
from vimniscient.keys import split_keys
from vimniscient.lessons import load_lessons

SEED = "live-test"
PACE = 0.08
SPECIAL = {"<Esc>": "Escape", "<CR>": "Enter", "<C-a>": "C-a", "<C-x>": "C-x", "<C-v>": "C-v", "<C-r>": "C-r", " ": "Space", "<Space>": "Space"}
SESSION = "vimniscient-endless"


def tmux(*args: str) -> str:
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout


def send(token: str) -> None:
    if token in SPECIAL:
        tmux("send-keys", "-t", SESSION, SPECIAL[token])
    else:
        tmux("send-keys", "-t", SESSION, "-l", "\\;" if token == ";" else token)


def type_keys(keys: str) -> None:
    for token in split_keys(keys):
        send(token)
        time.sleep(PACE)
    time.sleep(2.2)


def main() -> None:
    lessons = [lesson for lesson in load_lessons() if not lesson.lazyvim or has_lazyvim()]
    rungs = endless.ladder(lessons, 1, seed=SEED)
    (t1, v1), (t2, v2), (t3, v3), (t4, v4) = rungs[:4]
    plan = [
        ("climb", t1.version(v1), "solved"),
        ("climb", t2.version(v2), "failed"),
        ("learn", t2.version(v2), "solved"),
        ("climb", t3.version(v3), "solved"),
        ("climb", t4.version(v4), "solved"),
        ("recall", t2.version(v2 + 1), "solved"),
    ]

    with tempfile.TemporaryDirectory() as data:
        tmux("kill-session", "-t", SESSION)
        tmux("new-session", "-d", "-s", SESSION, "-x", "120", "-y", "32",
             f"VIMNISCIENT_DATA={data} vimniscient endless --seed {SEED}; sleep 5")
        time.sleep(3.5)
        for phase, task, outcome in plan:
            if outcome == "failed":
                type_keys("<Esc>" * (endless.budget(task.ref, 2) + 1))
            else:
                type_keys(task.solution)
        for token in [":q", "<CR>"]:
            tmux("send-keys", "-t", SESSION, *(["Enter"] if token == "<CR>" else ["-l", token]))
        time.sleep(1.5)
        tmux("kill-session", "-t", SESSION)
        db = sqlite3.connect(os.path.join(data, "progress.db"))
        rows = db.execute("SELECT lesson, task, status FROM attempts WHERE phase = 'endless' ORDER BY id").fetchall()
        run = db.execute("SELECT start, level, climbed, missed, fixed FROM endless_runs").fetchall()

    expected = [(task.lesson_id, task.index, outcome) for _, task, outcome in plan]
    problems = 0
    for i, want in enumerate(expected):
        got = rows[i] if i < len(rows) else None
        ok = got == want
        problems += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {plan[i][0]:6} want {want} got {got}")
    print("run:", run)
    if run != [(1, 4, 3, 1, 1)]:
        problems += 1
        print("FAIL run summary, want [(1, 4, 3, 1, 1)]")
    print(f"{problems} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
