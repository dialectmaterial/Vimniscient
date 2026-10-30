"""What your own keys say about your strategy, on the results screen.

A few rules, each one certain from the keys alone, so that a task with nothing
clear to say says nothing. They only speak when you went over the reference,
and never about text you typed in insert mode (tests/check_diagnose.py checks
that no reference solution sets one off).
"""

import re

from vimniscient.keys import split_keys

MOTION_RUN = 4  # jjjj; Vjj in a reference is fine, and three presses aren't a habit
X_RUN = 3
MOTIONS = {"h", "j", "k", "l", "w", "b", "e"}
OPERATORS = {"c", "d", "y", ">", "<", "="}
TAKES_CHAR = {"f", "t", "F", "T", "r", "m", "'", "`", "@", '"'}
INSERTS = {"i", "a", "A", "I", "o", "O", "s", "S", "C", "R"}
_REPEAT = re.compile(r"((?:<[^<>\s]+>|.){3,}?)\1\1", re.S)


def _skip_line(tokens: list[str], i: int) -> int:
    while i < len(tokens) and tokens[i] != "<CR>":
        i += 1
    return i + 1


def _skip_insert(tokens: list[str], i: int) -> int:
    while i < len(tokens) and tokens[i] != "<Esc>":
        i += 1
    return i + 1


def _skip_motion(tokens: list[str], i: int) -> int:
    """Past what follows an operator: a count, then a motion or a text object."""
    while i < len(tokens) and tokens[i].isdigit():
        i += 1
    if i >= len(tokens):
        return i
    key = tokens[i]
    if key in ("/", "?"):
        return _skip_line(tokens, i + 1)
    return i + (2 if key in {"i", "a", "g", "f", "t", "F", "T", "'", "`"} else 1)


def normal_keys(keys: str) -> list[list[str]]:
    """The runs of keys pressed as commands: not typed text, search or `:` lines."""
    tokens, runs, run = split_keys(keys), [], []
    i, visual, recording = 0, False, False
    while i < len(tokens):
        key = tokens[i]
        i += 1
        if key in (":", "/", "?"):
            i, visual = _skip_line(tokens, i), False
        elif visual and key in {"c", "s", "I", "A"}:
            i, visual = _skip_insert(tokens, i), False
        elif visual and key in OPERATORS | {"x", "J", "U", "u", "<Esc>"}:
            visual = False
        elif key in OPERATORS:
            if tokens[i:i + 1] == [key]:  # dd, cc, yy
                i += 1
            else:
                i = _skip_motion(tokens, i)
            if key == "c":
                i = _skip_insert(tokens, i)
        elif key == "g" and tokens[i:i + 1] and tokens[i] in {"U", "u", "~"}:
            i = _skip_motion(tokens, i + 1)
        elif key == "g":
            i += 1
        elif key in TAKES_CHAR:
            i += 1
        elif key == "q":
            i += 0 if recording else 1
            recording = not recording
        elif key in INSERTS:
            i = _skip_insert(tokens, i)
        else:
            visual = visual or key in {"v", "V", "<C-v>"}
            run.append(key)
            continue
        if run:
            runs.append(run)
            run = []
    return [*runs, run] if run else runs


def _longest_run(runs: list[list[str]], wanted: set[str]) -> tuple[str, int]:
    best, length = "", 0
    for tokens in runs:
        last, n = "", 0
        for key in tokens:
            n = n + 1 if key == last else 1
            last = key
            if key in wanted and n > length:
                best, length = key, n
    return best, length


def diagnose(keys: str, count: int, ref: int) -> str:
    """One thing worth saying about how `keys` went about it, or nothing."""
    if count <= ref:
        return ""
    runs = normal_keys(keys)
    motion, length = _longest_run(runs, MOTIONS)
    if length >= MOTION_RUN:
        better = "f, t, / or a count" if motion in "hl" else "a count"
        return f"{motion} {length} times in a row: {better} gets there in one go."
    if _longest_run(runs, {"x"})[1] >= X_RUN:
        return "x over and over: a count, dw or diw takes it all at once."
    repeat = _REPEAT.search(keys)
    if repeat and not any("." in run for run in runs) and "<Esc>" in repeat.group(1):
        return f"You typed {repeat.group(1)} three times: . repeats the last change."
    return ""
