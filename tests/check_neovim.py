#!/usr/bin/env python3
"""Every solution, typed at full speed into a real Neovim: all lesson texts, generated
tasks, Choose and eval ways, and every mission way on real files.

    cargo build --examples
    python3 tests/check_neovim.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "target/debug/examples/tasks"
SCRIPT = ROOT / "tests/check_lessons.lua"
PLAY = 'local keys = vim.api.nvim_replace_termcodes(vim.env.WAY, true, false, true)\nvim.api.nvim_feedkeys(keys, "xt", false)\nvim.cmd("qa!")\n'
failed = 0

for name in ("written", "lazyvim", "generated", "ways"):
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        f.write(subprocess.check_output([TASKS, name], text=True))
        f.flush()
        if name == "lazyvim":  # in your own config
            with tempfile.TemporaryDirectory() as cwd:
                run = subprocess.run(["nvim", "--headless", "-i", "NONE", "-n", "-S", str(SCRIPT)], cwd=cwd, capture_output=True, text=True,
                                     env=os.environ | {"VIMNISCIENT_TASKS": f.name, "VIMNISCIENT_LAZY": "1"})
        else:
            run = subprocess.run(["nvim", "--clean", "--headless", "-l", str(SCRIPT), f.name], capture_output=True, text=True)
    lines = [line for line in run.stdout.splitlines() if line.startswith("FAIL") or "failed" in line]
    print(name + ":", *lines[-5:], sep="\n  " if len(lines) > 1 else " ")
    failed += run.returncode != 0

for mission in json.loads(subprocess.check_output([TASKS, "missions"])):
    for way in mission["ways"]:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "project"
            work.mkdir()
            for file, text in mission["files"].items():
                (work / file).write_text(text)
            play = Path(tmp) / "play.lua"
            play.write_text(PLAY)
            subprocess.run(["nvim", "--clean", "--headless", "-n", next(iter(mission["files"])), "-S", str(play)], cwd=work,
                           env=os.environ | {"WAY": way}, capture_output=True, timeout=20)
            wrong = [file for file, text in mission["targets"].items() if (work / file).read_text() != text]
            if wrong:
                failed += 1
                print(f"FAIL {mission['title']}: {way} {wrong}")
print("missions: done")
print(f"{failed} problems")
sys.exit(1 if failed else 0)
