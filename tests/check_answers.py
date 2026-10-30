"""Check that answers written in the usual different ways are accepted.

    uv run python tests/check_answers.py
"""

import sys

from vimniscient.answer import is_correct

CASES = [
    # (typed, expected, style, case_sensitive, should match)
    ("ciw", ["ciw"], "keys", True, True),
    ("leader + ,", ["<leader>,"], "keys", True, True),
    ("leader + c", ["PREFIX + C"], "combo", False, True),
    ("ciW", ["ciw"], "keys", True, False),
    ("ctrl-a", ["<C-a>"], "keys", True, True),
    ("Ctrl+R", ["<C-r>"], "keys", True, True),
    ("^r", ["<C-r>"], "keys", True, True),
    ("<c-A>", ["<C-a>"], "keys", True, True),
    ("space ff", ["<leader>ff"], "keys", True, True),
    ("<Space>ff", ["<leader>ff"], "keys", True, True),
    ("<leader>ff", ["<leader><Space>", "<leader>ff"], "keys", True, True),
    ("leader space", ["<leader><Space>"], "keys", True, True),
    ("<leader>fF", ["<leader>ff"], "keys", True, False),
    ("<leader>", ["<leader><Space>"], "keys", True, False),
    ("space space", ["<leader><Space>"], "keys", True, True),
    ("f", ["f<Space>"], "keys", True, False),
    ("f<space>", ["f<Space>"], "keys", True, True),
    ("f space", ["f<Space>"], "keys", True, True),
    ("n N", ["nN"], "keys", True, True),
    (":%s/foo/bar/g", [":%s/foo/bar/g<CR>"], "keys", True, True),
    ("alt-.", ["<M-.>"], "keys", False, True),
    ("ciw<esc>", ["ciw<Esc>"], "keys", True, True),
    ("super shift b", ["SUPER SHIFT + B"], "combo", False, True),
    ("Super+Shift+B", ["SUPER SHIFT + RETURN", "SUPER SHIFT + B"], "combo", False, True),
    ("shift super b", ["SUPER SHIFT + B"], "combo", False, True),
    ("super b", ["SUPER SHIFT + B"], "combo", False, False),
    ("super enter", ["SUPER + RETURN"], "combo", False, True),
    ("ctrl-shift-c", ["CTRL SHIFT + C"], "combo", False, True),
    ("shift pgup", ["SHIFT + PAGE_UP"], "combo", False, True),
    ("ctrl +", ["CTRL + PLUS"], "combo", False, True),
    ("ctrl =", ["CTRL + PLUS", "CTRL + EQUAL"], "combo", False, True),
    ("prefix c", ["PREFIX + c"], "combo", True, True),
    ("prefix C", ["PREFIX + c"], "combo", True, False),
    ("prefix shift c", ["PREFIX + C"], "combo", True, True),
    ("alt shift enter", ["ALT + SHIFT + ENTER"], "combo", True, True),
    ("copy mode v", ["COPY MODE + v"], "combo", True, True),
]

failed = 0
for typed, expected, style, case, want in CASES:
    got = is_correct(typed, expected, style, case)
    if got != want:
        failed += 1
        print(f"FAIL {typed!r} vs {expected} ({style}): got {got}, want {want}")
print(f"{len(CASES)} cases, {failed} failed")
sys.exit(1 if failed else 0)
