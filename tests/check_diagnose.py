"""Strategy feedback: it fires on the habits it names, stays quiet on typed text,
and no reference solution in the curriculum, written or generated, sets it off.

    uv run python tests/check_diagnose.py
"""

import sys

from vimniscient.diagnose import diagnose, normal_keys
from vimniscient.generate import KINDS, generate
from vimniscient.keys import count_keys
from vimniscient.lessons import load_lessons

problems = []


def check(what: str, ok: bool, detail: object = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {what}" + (f": {detail}" if not ok else ""))
    if not ok:
        problems.append(what)


def says(keys: str, ref: int = 2) -> str:
    return diagnose(keys, count_keys(keys), ref)


check("jjjj is noticed", "j 4 times" in says("jjjjdd"), says("jjjjdd"))
check("lllll suggests f", "f, t" in says("llllldw"), says("llllldw"))
check("xxx is noticed", "x over and over" in says("xxxx"), says("xxxx"))
check("a repeated edit is noticed", ". repeats" in says("A;<Esc>jA;<Esc>jA;<Esc>j"), says("A;<Esc>jA;<Esc>jA;<Esc>j"))
check("the dot is fine", says("A;<Esc>j.j.j.jjj", 20) == "", says("A;<Esc>j.j.j.jjj", 20))
check("an edit breaks a run", says("llrxllrxll") == "", says("llrxllrxll"))
check("at or under the reference: quiet", diagnose("jjjjdd", 6, 6) == "")
check("typed text isn't a habit", says("ciwhellllllo<Esc>") == "", says("ciwhellllllo<Esc>"))
check("nor text after o", says("oxxxxx jjjjj<Esc>") == "", says("oxxxxx jjjjj<Esc>"))
check("nor a search", says("/jjjjjj<CR>dd") == "", says("/jjjjjj<CR>dd"))
check("nor a : line", says(":s/xxxx/y<CR>w") == "", says(":s/xxxx/y<CR>w"))
check("f takes its letter", normal_keys("fjjj") == [["j", "j"]], normal_keys("fjjj"))
check("visual c types text", says("vjjjcjjjjjj<Esc>") == "", says("vjjjcjjjjjj<Esc>"))
check("macros: q closes without a letter", normal_keys("qaxqjjj") == [["x"], ["j", "j", "j"]], normal_keys("qaxqjjj"))

fired = []
for lesson in load_lessons():
    for task in lesson.tasks:
        for version in [task, *task.variants]:
            text = diagnose(version.solution, version.ref + 1, version.ref)
            if text:
                fired.append((version.item_id, version.solution, text))
parent = load_lessons()[0].tasks[0]
for kind in KINDS:
    for n in range(60):
        version = generate(kind, str(n), parent)
        text = diagnose(version.solution, version.ref + 1, version.ref)
        if text:
            fired.append((kind, version.solution, text))
check("no reference solution sets a rule off", not fired, fired[:5])

print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
