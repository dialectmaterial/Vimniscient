"""Play a mission through mission.lua in your real Neovim, in a hidden tmux
session: a save that leaves work open doesn't end it, the one that finishes does.

    uv run python tests/live_mission.py
"""

import os
import sqlite3
import sys
import tempfile
import time

from live_endless import SESSION, tmux, type_keys

SCRIPT = """
from vimniscient import missions
from vimniscient.progress import Progress
from vimniscient.session import run_mission
Progress().record_ungraded([run_mission(missions.missions()[0])], "mission")
"""

with tempfile.TemporaryDirectory() as data:
    script = os.path.join(data, "mission.py")
    with open(script, "w") as f:
        f.write(SCRIPT)
    tmux("kill-session", "-t", SESSION)
    tmux("new-session", "-d", "-s", SESSION, "-x", "120", "-y", "32", f"VIMNISCIENT_DATA={data} uv run python {script}")
    time.sleep(4)
    screen = tmux("capture-pane", "-t", SESSION, "-p")
    problems = [] if "mission" in screen and "Rename load_config" in screen else ["the goal isn't on screen"]
    type_keys(":w<CR>")
    if "mission" not in tmux("capture-pane", "-t", SESSION, "-p"):
        problems.append("a save with work left ended it")
    type_keys(":args *.py<CR>")
    type_keys(":argdo %s/load_config/read_config/g | update<CR>")
    time.sleep(1.5)
    rows = sqlite3.connect(os.path.join(data, "progress.db")).execute("SELECT status, phase, count FROM attempts").fetchall()
    tmux("kill-session", "-t", SESSION)
    print(rows)
    if not (len(rows) == 1 and rows[0][:2] == ("solved", "mission") and rows[0][2] > 20):
        problems.append(f"result: {rows}")
for problem in problems:
    print("FAIL", problem)
print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
