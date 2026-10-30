"""Missions: every way does the whole job in Neovim, on real files, and each
mission has at least two.

    uv run python tests/check_missions.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["VIMNISCIENT_DATA"] = tempfile.mkdtemp()

from vimniscient import missions  # noqa: E402
from vimniscient.lessons import load_lessons  # noqa: E402
from vimniscient.progress import Progress  # noqa: E402

PLAY = """
local keys = vim.api.nvim_replace_termcodes(vim.env.WAY, true, false, true)
vim.api.nvim_feedkeys(keys, "xt", false)
vim.cmd("qa!")
"""
problems = []
ids = {lesson.id for lesson in load_lessons()}
for m in missions.missions():
    if m.after not in ids or len(set(m.ways)) < 2 or set(m.files) != set(m.targets):
        problems.append(f"{m.title}: malformed")
    for way in m.ways:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "project"
            work.mkdir()
            for name, text in m.files.items():
                (work / name).write_text(text)
            play = Path(tmp) / "play.lua"
            play.write_text(PLAY)
            subprocess.run(["nvim", "--clean", "--headless", "-n", next(iter(m.files)), "-S", str(play)], cwd=work,
                           env=os.environ | {"WAY": way}, capture_output=True, timeout=20)
            wrong = [name for name, text in m.targets.items() if (work / name).read_text() != text]
            print(f"{'ok  ' if not wrong else 'FAIL'} {m.title}: {way}" + (f" {wrong}" if wrong else ""))
            if wrong:
                problems.append(way)

p = Progress()
lessons = load_lessons()
if missions.pick(lessons, p) is not None:
    problems.append("a mission before its lesson")
print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
