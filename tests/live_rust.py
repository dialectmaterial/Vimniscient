"""Play the Rust binary in real Neovim, in a hidden tmux session: whole lessons, the
start of an Endless run, and a mission. The keys come from the binary's own plan.

    cargo build --examples --manifest-path rust/Cargo.toml
    uv run python tests/live_rust.py [lesson ids]
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from vimniscient.keys import split_keys

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "rust/target/debug/vimniscient"
TASKS = ROOT / "rust/target/debug/examples/tasks"
SESSION = "vimniscient-rust"
SPECIAL = {"<Esc>": "Escape", "<CR>": "Enter", "<C-a>": "C-a", "<C-x>": "C-x", "<C-v>": "C-v", "<C-r>": "C-r", " ": "Space", "<Space>": "Space"}
problems = []


def tmux(*args: str) -> str:
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout


def send(token: str) -> None:
    if token in SPECIAL:
        tmux("send-keys", "-t", SESSION, SPECIAL[token])
    else:
        tmux("send-keys", "-t", SESSION, "-l", "\;" if token == ";" else token)


def play(keys: str) -> None:
    for token in split_keys(keys):
        send(token)
        time.sleep(0.08)
    time.sleep(2.2)


def start(command: str, data: str) -> None:
    tmux("kill-session", "-t", SESSION)
    tmux("new-session", "-d", "-s", SESSION, "-x", "120", "-y", "32", f"VIMNISCIENT_DATA={data} {command}; sleep 5")
    time.sleep(3.5)


def rows(data: str, sql: str) -> list:
    return sqlite3.connect(os.path.join(data, "progress.db")).execute(sql).fetchall()


with tempfile.TemporaryDirectory() as data:
    for lesson in sys.argv[1:] or ["w1d1-words", "w2d3-cgn", "w5d2-any-quote-bracket"]:
        plan = json.loads(subprocess.check_output([TASKS, "plan", lesson]))
        start(f"{BIN} run {lesson}", data)
        for task in plan:
            play(task["solution"])
        time.sleep(1)
        got = rows(data, f"SELECT status, count, ref, seconds, phase FROM attempts WHERE lesson = '{lesson}'")
        good = [r for r in got if r[0] == "solved" and r[1] == r[2] and r[3]]
        print(f"{lesson}: {len(good)}/{len(plan)} solved at the reference", flush=True)
        if len(good) != len(plan):
            problems.append(f"{lesson}: {[r for r in got if r not in good]}")

    with tempfile.TemporaryDirectory() as fresh:
        rungs = json.loads(subprocess.check_output([TASKS, "endless", "live"]))
        start(f"{BIN} endless --seed live", fresh)
        for task in rungs[:4]:
            play(task["solution"])
        tmux("send-keys", "-t", SESSION, "-l", ":q")
        tmux("send-keys", "-t", SESSION, "Enter")
        time.sleep(1.5)
        got = rows(fresh, "SELECT level, climbed FROM endless_runs")
        print("endless:", got, flush=True)
        if not got or got[0][1] != 4:
            problems.append(f"endless: {got}")

    with tempfile.TemporaryDirectory() as fresh:
        start(f"{TASKS} mission", fresh)
        time.sleep(1)
        if "Rename load_config" not in tmux("capture-pane", "-t", SESSION, "-p"):
            problems.append("the mission's goal isn't on screen")
        play(":args *.py<CR>")
        play(":argdo %s/load_config/read_config/g | update<CR>")
        time.sleep(1.5)
        got = rows(fresh, "SELECT status, phase FROM attempts")
        print("mission:", got, flush=True)
        if got != [("solved", "mission")]:
            problems.append(f"mission: {got}")
tmux("kill-session", "-t", SESSION)
for problem in problems:
    print("FAIL", problem)
print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
