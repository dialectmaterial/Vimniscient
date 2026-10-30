"""`vimniscient doctor`: does this machine work with the trainer? Required
checks stop it working; the rest say what you'd be missing."""

import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass

from vimniscient.cards import has_lazyvim, has_plugin

MIN_NVIM = (0, 10)
MIN_SIZE = (80, 24)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    required: bool = True

    @property
    def mark(self) -> str:
        return "✓" if self.passed else "✗" if self.required else "·"


def _nvim() -> list[Check]:
    if not shutil.which("nvim"):
        return [Check("Neovim", False, f"not found; install {MIN_NVIM[0]}.{MIN_NVIM[1]} or newer")]
    out = subprocess.run(["nvim", "--version"], capture_output=True, text=True).stdout
    found = re.search(r"v(\d+)\.(\d+)", out)
    version = (int(found[1]), int(found[2])) if found else (0, 0)
    good = version >= MIN_NVIM
    checks = [Check("Neovim", good, f"{version[0]}.{version[1]}" + ("" if good else f"; {MIN_NVIM[0]}.{MIN_NVIM[1]} or newer needed"))]
    try:
        run = subprocess.run(["nvim", "--headless", "-i", "NONE", "+qa"], capture_output=True, text=True, timeout=30)
        problem = next((line for line in run.stderr.splitlines() if re.search(r"(?i)error", line)), "")
        checks.append(Check("Your config", run.returncode == 0 and not problem, problem[:90] or "starts cleanly"))
    except subprocess.TimeoutExpired:
        checks.append(Check("Your config", False, "Neovim didn't start within 30 seconds"))
    return checks


def _terminal() -> Check:
    size = shutil.get_terminal_size()
    good = size.columns >= MIN_SIZE[0] and size.lines >= MIN_SIZE[1]
    return Check("Terminal size", good, f"{size.columns}×{size.lines}" + ("" if good else f"; {MIN_SIZE[0]}×{MIN_SIZE[1]} or larger is needed"), required=False)


def _data() -> Check:
    from vimniscient.progress import DATA_DIR

    path = DATA_DIR / "progress.db"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(path).execute("SELECT 1")
        return Check("Progress data", True, str(path))
    except (OSError, sqlite3.Error) as error:
        return Check("Progress data", False, f"{path}: {error}")


def checks() -> list[Check]:
    optional = [
        Check("LazyVim", has_lazyvim(), "week 5 lessons and the LazyVim cards" + ("" if has_lazyvim() else " stay hidden"), required=False),
        Check("hardtime.nvim", has_plugin("hardtime.nvim"), "habit cards and drills", required=False),
        Check("Hyprland", bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")), "Omarchy drills", required=False),
    ]
    return [*_nvim(), _data(), _terminal(), *optional]
