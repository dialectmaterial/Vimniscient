#!/usr/bin/env python3
"""Play the app in real Neovim, in a hidden tmux session: whole lessons, a skipped task
coming back, the start of an Endless run, and a mission.

    cargo build --examples
    python3 tests/live.py [lesson ids]
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "target/debug/vimniscient"
TASKS = ROOT / "target/debug/examples/tasks"
SESSION = "vimniscient-live"
SPECIAL = {"<Esc>": "Escape", "<CR>": "Enter", "<C-a>": "C-a", "<C-x>": "C-x", "<C-v>": "C-v", "<C-r>": "C-r", " ": "Space", "<Space>": "Space"}
problems = []


def split_keys(keys: str) -> list[str]:
    return re.findall(r"<[^<>\s]+>|.", keys, re.S)


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

    # a skipped Recall task: shown, typed once, and asked again on its next text at the end
    with tempfile.TemporaryDirectory() as fresh:
        plan = json.loads(subprocess.check_output([TASKS, "plan", "w2d1-dot"]))
        start(f"{BIN} run w2d1-dot", fresh)
        skipped = None
        for task in plan:
            if task["phase"] == "recall" and skipped is None:
                skipped = task
                play(":Skip<CR>")
                play(task["solution"])
            else:
                play(task["solution"])
        play(skipped["again"])
        time.sleep(1)
        got = rows(fresh, "SELECT status, phase FROM attempts ORDER BY id")
        counts = {pair: got.count(pair) for pair in set(got)}
        print("retry:", counts, flush=True)
        if counts.get(("skipped", "recall")) != 1 or len(got) != len(plan) + 2 or any(r[0] not in ("solved", "skipped") for r in got):
            problems.append(f"retry: {got}")

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
