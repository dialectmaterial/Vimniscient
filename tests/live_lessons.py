"""Type every reference solution into the real runner (your LazyVim), at a
realistic speed, through a hidden tmux session. Progress goes to a throwaway
data folder.

    uv run python tests/live_lessons.py              # the LazyVim lessons
    uv run python tests/live_lessons.py w1d1-words   # any lessons by id
    uv run python tests/live_lessons.py --all
"""

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

from vimniscient.keys import split_keys
from vimniscient.lessons import load_lessons, two_rounds

PACE = 0.08  # seconds between keys, a fast typist
SPECIAL = {"<Esc>": "Escape", "<CR>": "Enter", "<C-a>": "C-a", "<C-x>": "C-x", "<C-v>": "C-v", "<C-r>": "C-r", " ": "Space", "<Space>": "Space"}
SESSION = "vimniscient-live"


def tmux(*args: str) -> str:
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout


def send(token: str) -> None:
    if token in SPECIAL:
        tmux("send-keys", "-t", SESSION, SPECIAL[token])
    elif token.startswith("<") and token.endswith(">") and len(token) > 2:
        raise SystemExit(f"add {token} to SPECIAL")
    else:
        tmux("send-keys", "-t", SESSION, "-l", "\\;" if token == ";" else token)


def goal_label() -> str | None:
    """learn 2/6, recall 3/6, … from the frame's footer."""
    m = re.search(r"(learn|recall|task) \d+/\d+", tmux("capture-pane", "-pt", SESSION))
    return m.group(0) if m else None


args = sys.argv[1:]
lessons = load_lessons()
if "--all" in args:
    chosen = lessons
elif args:
    chosen = [lesson for lesson in lessons if lesson.id in args]
else:
    chosen = [lesson for lesson in lessons if lesson.lazyvim]

failed = 0
with tempfile.TemporaryDirectory() as data:
    for lesson in chosen:
        tmux("kill-session", "-t", SESSION)
        tmux("new-session", "-d", "-s", SESSION, "-x", "120", "-y", "32",
             f"VIMNISCIENT_DATA={data} vimniscient run {lesson.id}; sleep 5")
        time.sleep(3.5)
        session = two_rounds(lesson)  # the order `vimniscient run` uses today
        for task in session:
            label = goal_label()
            for token in split_keys(task.solution):
                send(token)
                time.sleep(PACE)
            time.sleep(2.2)
            if goal_label() == label:  # still on this task: it wasn't solved
                for token in [":Skip", "<CR>"]:
                    tmux("send-keys", "-t", SESSION, *(["Enter"] if token == "<CR>" else ["-l", token]))
                time.sleep(0.6)
        time.sleep(1)
        tmux("kill-session", "-t", SESSION)
        db = sqlite3.connect(os.path.join(data, "progress.db"))
        rows = db.execute(
            "SELECT task, status, count, ref, keys, phase, seconds, first FROM attempts WHERE lesson = ? ORDER BY id",
            (lesson.id,)
        ).fetchall()
        db.execute("DELETE FROM attempts WHERE lesson = ?", (lesson.id,))
        db.commit()
        # solved at the reference count, and timed: the first key comes before the end
        bad = [r for r in rows if r[1] != "solved" or r[2] != r[3] or not (r[6] and 0 <= (r[7] or 0) <= r[6])]
        failed += len(bad) + (len(session) - len(rows))
        for task, status, count, ref, keys, phase, seconds, first in bad:
            print(f"FAIL {lesson.id}#{task + 1} ({phase}): {status} {count}/{ref} typed {keys!r} in {seconds}s (first key {first}s)")
        times = sorted(r[6] for r in rows if r[6])
        typical = f", {times[len(times) // 2]:.1f}s a task" if times else ""
        print(f"{lesson.id}: {len(rows) - len(bad)}/{len(session)} ok{typical}", flush=True)
print(f"{failed} problems")
sys.exit(1 if failed else 0)
