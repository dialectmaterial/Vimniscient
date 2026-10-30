"""Practice texts made from a seed, for skills where any sentence will do.

A lesson task can name a `generate` kind. Its Learn round keeps the authored
text; Recall and reviews can get a generated one instead, so a skill gets
practised on sentences you haven't seen. The same seed always gives the same
task, so a run can be replayed and every kind can be checked in Neovim
(tests/check_generate.py).

The sentences stay mnemonic: they're the hooks from mnemonics.yaml, what keys
stand for.

Kinds:
  ciw-typo    two letters of a word swapped; ciw and type it right
  daw-double  a word doubled; daw deletes one copy and its space
  ciW-dotted  a word written with dots between its letters; ciW rewrites it
  ci-quote    a key's meaning, wrong, in double quotes; ci" fixes it
  di-paren    the arguments of a call; di( empties it
  da-paren    a call's arguments; da( takes the parentheses too
  di-bracket  a list of keys; di[ empties it
  dt-letter   filler before a word; dt and the word's first letter
  D-rest      filler after a sentence; D deletes to the end of the line
  J-split     a sentence over two lines; J joins them
  ddp-swap    two lines the wrong way round; ddp swaps them
  count-dw    a few filler words; a count on dw
  count-dd    a few filler lines; a count on dd
  count-x     stray x letters; a count on x
  nav-down, nav-up, nav-find    a # to find and delete: count, then f#, then x

Whole-line kinds, on a few sentences (LINE_KINDS, one line each): the dot,
visual mode, macros, visual block, and the Ex commands of weeks 3 and 4.
"""

import random
import re
from dataclasses import replace
from functools import cache
from importlib import resources

import yaml

from vimniscient.lessons import Task, load_lessons
from vimniscient.mnemonics import _tables
from vimniscient.mnemonics import hooks as key_hooks

FILLER = ("um", "well", "like", "so")


@cache
def sentences() -> list[str]:
    """The hooks of the keys week 1 teaches: nothing about keys you haven't met yet."""
    known = {hook for lesson in load_lessons() if lesson.week == 1 for key in lesson.keys for hook in key_hooks(key)}
    hooks = [hook for hook in dict.fromkeys(hook for table in _tables()[:2] for hook in table.values()) if hook in known]
    # as written: a capital would change the key ("u is down" is not "U is down")
    return [h + ("" if h.endswith(".") else ".") for h in hooks]


@cache
def meanings() -> list[tuple[str, str]]:
    """Single-letter keys with a one-word meaning: (c, change), (d, delete) ..."""
    data = yaml.safe_load((resources.files("vimniscient") / "mnemonics.yaml").read_text(encoding="utf-8"))
    known = {s.removesuffix(".") for s in sentences()}
    return [(key, entry["means"]) for key, entry in data.items() if entry["hook"].removesuffix(".") in known
            and re.fullmatch(r"[a-zA-Z]", key) and re.fullmatch(r"[a-z]+", entry.get("means") or "")]


_WORD = re.compile(r"(?<![\w'.-])[A-Za-z]{4,}(?![\w'-])")


def _words(sentence: str, spaced: bool) -> list[re.Match]:
    """Plain words of four letters or more; `spaced` wants a space on both sides (a WORD)."""
    found = list(_WORD.finditer(sentence))
    if spaced:
        found = [m for m in found if m.start() > 0 and sentence[m.start() - 1] == " "
                 and m.end() < len(sentence) and sentence[m.end()] == " "]
    else:  # daw and ciw want the word to have a space after it, or anything but a letter
        found = [m for m in found if m.end() < len(sentence)]
    return found


def _gaps(sentence: str) -> list[int]:
    """Where a new word can go: the start of every word but the first."""
    return [m.end() for m in re.finditer(r" (?=[A-Za-z])", sentence)]


def _ci_quote(rng: random.Random) -> dict:
    (key, right), (_, wrong) = rng.sample(meanings(), 2)
    start = f'{key}_means = "{wrong}"'
    return dict(goal=f'{key} stands for {right}: fix the string.', start=[start], cursor=(1, rng.randrange(len(start) - 1)),
                target=[f'{key}_means = "{right}"'], solution=f'ci"{right}<Esc>',
                hint='ci" changes what is inside the quotes, and finds them from anywhere before them.')


def _paren(rng: random.Random, around: bool) -> dict:
    name = rng.choice(("around", "parens") if around else ("inner", "inside"))
    args = ", ".join(means for _, means in rng.sample(meanings(), 3))
    start = f"{name}({args}) + 1"
    target, keys = (f"{name} + 1", "da(") if around else (f"{name}() + 1", "di(")
    what = "the call's parentheses and arguments" if around else "the arguments, keeping the parentheses"
    return dict(goal=f"Delete {what}.", start=[start], cursor=(1, len(name) + 1 + rng.randrange(len(args))), target=[target],
                solution=keys, hint=f"{keys} works from anywhere inside the parentheses.")


def _di_bracket(rng: random.Random) -> dict:
    name = rng.choice(("keys", "square", "bracket"))
    items = ", ".join(f'"{key}"' for key, _ in rng.sample(meanings(), 3))
    start = f"{name} = [{items}]"
    return dict(goal="Empty the list, keeping the square brackets.", start=[start], cursor=(1, len(name) + 4 + rng.randrange(len(items))),
                target=[f"{name} = []"], solution="di[", hint="[ names the square brackets: di[ empties them.")


def _dt_letter(rng: random.Random) -> dict:
    filler = " ".join(rng.sample(FILLER, 2)) + " "
    while True:
        sentence = rng.choice(sentences())
        gaps = [g for g in _gaps(sentence) if sentence[g] not in filler]
        if gaps:
            break
    gap = rng.choice(gaps)
    word = sentence[gap:].split(" ")[0].rstrip(".,:;")
    letter = word[0]
    return dict(goal=f'Delete everything up to "{word}".', start=[sentence[:gap] + filler + sentence[gap:]], cursor=(1, gap),
                target=[sentence], solution=f"dt{letter}", hint=f"dt{letter} deletes till the next {letter}, and stops just before it.")


def _d_rest(rng: random.Random) -> dict:
    sentence = rng.choice(sentences())
    return dict(goal="Delete the filler after the full stop.", start=[f"{sentence} {' '.join(rng.sample(FILLER, 3))}"],
                cursor=(1, len(sentence)), target=[sentence], solution="D", hint="D is a big d: it deletes to the end of the line.")


def _j_split(rng: random.Random) -> dict:
    sentence = rng.choice([s for s in sentences() if _gaps(s)])
    gap = rng.choice(_gaps(sentence))
    return dict(goal="Join the two lines.", start=[sentence[:gap - 1], sentence[gap:]], cursor=(1, 0), target=[sentence],
                solution="J", hint="J joins this line and the next, with one space.")


def _ddp_swap(rng: random.Random) -> dict:
    first, second = rng.sample(sentences(), 2)
    return dict(goal="Swap the two lines.", start=[first, second], cursor=(1, 0), target=[second, first],
                solution="ddp", hint="dd cuts the line, p puts it below the next one.")


def _count_dw(rng: random.Random) -> dict:
    n = rng.randint(2, 4)
    sentence = rng.choice([s for s in sentences() if _gaps(s)])
    gap = rng.choice(_gaps(sentence))
    filler = " ".join(rng.choice(FILLER) for _ in range(n)) + " "
    return dict(goal=f"Delete the {n} filler words.", start=[sentence[:gap] + filler + sentence[gap:]], cursor=(1, gap),
                target=[sentence], solution=f"{n}dw", hint=f"A count repeats the verb: {n}dw deletes {n} words.")


def _count_dd(rng: random.Random) -> dict:
    n = rng.randint(2, 4)
    first, last = rng.sample(sentences(), 2)
    return dict(goal=f"Delete the {n} filler lines.", start=[first, *[rng.choice(FILLER) for _ in range(n)], last], cursor=(2, 0),
                target=[first, last], solution=f"{n}dd", hint=f"A count works on dd: {n}dd deletes {n} lines.")


def _count_x(rng: random.Random) -> dict:
    n = rng.randint(2, 7)
    sentence = rng.choice([s for s in sentences() if _gaps(s)])
    gap = rng.choice(_gaps(sentence))
    return dict(goal=f"Delete the {n} x letters.", start=[sentence[:gap] + "x" * n + sentence[gap:]], cursor=(1, gap),
                target=[sentence], solution=f"{n}x", hint=f"x crosses out a character; {n}x crosses out {n}.")


def _lines(rng: random.Random, n: int = 3) -> list[str]:
    return rng.sample(sentences(), n)


def _marked(rng: random.Random, sentence: str) -> str:
    gap = rng.choice(_gaps(sentence))
    return sentence[:gap] + "#" + sentence[gap:]


def _nav(rng: random.Random, up: bool) -> dict:
    n = rng.randint(4, 11)
    lines = rng.choices([s for s in sentences() if _gaps(s)], k=n + 1)
    far, near = (0, n) if up else (n, 0)
    start = [*lines]
    start[far] = _marked(rng, lines[far])
    keys = f"{n}{'k' if up else 'j'}f#x"
    return dict(goal="Delete the #.", start=start, cursor=(near + 1, 0), target=lines, solution=keys,
                hint=f"The line numbers say how far: {n}{'k' if up else 'j'}, then f# and x.")


def _nav_find(rng: random.Random) -> dict:
    sentence = rng.choice([s for s in sentences() if _gaps(s)])
    return dict(goal="Delete the #.", start=[_marked(rng, sentence)], cursor=(1, 0), target=[sentence], solution="f#x",
                hint="f# lands on it, x crosses it out.")


def _each(rng: random.Random, change, keys: str, goal: str, hint: str, cursor: tuple[int, int] = (1, 0), n: int = 3) -> dict:
    lines = _lines(rng, n)
    return dict(goal=goal, start=lines, cursor=cursor, target=[change(line) for line in lines], solution=keys, hint=hint)


def _some(rng: random.Random, keys: str, goal: str, hint: str, target, cursor: tuple[int, int] = (1, 0), n: int = 3) -> dict:
    lines = _lines(rng, n)
    return dict(goal=goal, start=lines, cursor=cursor, target=target(lines), solution=keys, hint=hint)


def _comments(rng: random.Random) -> dict:
    first, second, third = _lines(rng)
    return dict(goal="Delete the comment lines.", start=[first, "# cut", second, "# cut", third], cursor=(1, 0),
                target=[first, second, third], solution=":g/#/d<CR>", hint=":g runs d on every line that matches #.")


def _sort(rng: random.Random) -> dict:
    lines = sorted(_lines(rng))
    return dict(goal="Sort the lines.", start=lines[::-1], cursor=(1, 0), target=lines, solution=":sort<CR>", hint=":sort sorts every line.")


def _sort_u(rng: random.Random) -> dict:
    first, second = _lines(rng, 2)
    return dict(goal="Sort the lines and drop the duplicate.", start=[first, second, first], cursor=(1, 0),
                target=sorted({first, second}), solution=":sort u<CR>", hint="u is unique: :sort u keeps one of each.")


def _trailing(rng: random.Random) -> dict:
    lines = _lines(rng)
    return dict(goal="Delete the trailing spaces.", start=[line + " " * rng.randint(1, 4) for line in lines], cursor=(1, 0),
                target=lines, solution=r":%s/\s\+$//<CR>", hint=r"\s\+$ is one or more spaces right before the end of the line.")


LINE_KINDS = {
    "dot-append": lambda r: _each(r, lambda s: s + ";", "A;<Esc>j.j.", "End every line with a semicolon.", "Do one, then j and . for the rest."),
    "dot-prefix": lambda r: _each(r, lambda s: "- " + s, "I- <Esc>j.j.", 'Start every line with "- ".', "Do one, then j and . for the rest."),
    "visual-delete": lambda r: _some(r, "Vjd", "Delete the first two lines.", "V selects whole lines, j grows it, d deletes.", lambda ls: ls[2:]),
    "visual-indent": lambda r: _each(r, lambda s: "    " + s, "Vjj>", "Indent all three lines.", "V, j j, then > pushes them right."),
    "visual-join": lambda r: _some(r, "VjjJ", "Join all three lines.", "V, j j, then J joins them.", lambda ls: [" ".join(ls)]),
    "macro-append": lambda r: _each(r, lambda s: s + ";", "qaA;<Esc>jq2@a", "End every line with a semicolon, with a macro.", "qa, the edit and j, q, then 2@a."),
    "macro-quote": lambda r: _each(r, lambda s: f'"{s}"', 'qaI"<Esc>A"<Esc>jq2@a', "Put every line in double quotes, with a macro.", "qa, the edit and j, q, then 2@a."),
    "block-prefix": lambda r: _each(r, lambda s: "# " + s, "<C-v>jjI# <Esc>", 'Start every line with "# ".', "Ctrl-v j j, then I types on every line."),
    "block-append": lambda r: _each(r, lambda s: s + ";", "<C-v>jj$A;<Esc>", "End every line with a semicolon.", "$ stretches the block to every line's end; A appends."),
    "move-top": lambda r: _some(r, ":m0<CR>", "Move the last line to the top.", ":m0 moves this line below line 0.", lambda ls: [ls[2], ls[0], ls[1]], (3, 0)),
    "copy-end": lambda r: _some(r, ":t$<CR>", "Copy the first line to the end.", ":t$ copies this line below the last one.", lambda ls: [*ls, ls[0]]),
    "range-delete": lambda r: _some(r, ":2,3d<CR>", "Delete lines 2 and 3 without moving.", "A range in front of d: :2,3d.", lambda ls: [ls[0], ls[3]], n=4),
    "reverse": lambda r: _some(r, ":g/^/m0<CR>", "Reverse the lines.", ":g/^/ visits every line; m0 moves each to the top.", lambda ls: ls[::-1]),
    "sort": lambda r: _sort(r),
    "norm-append": lambda r: _each(r, lambda s: s + ";", ":%norm A;<CR>", "End every line with a semicolon.", ":%norm runs A; on every line."),
    "sub-prefix": lambda r: _each(r, lambda s: "- " + s, ":%s/^/- /<CR>", "Make every line a list item.", "^ matches the start of each line."),
    "comments": _comments,
    "sort-u": _sort_u,
    "trailing": _trailing,
    "delete-to-end": lambda r: _some(r, "dG", "Delete everything but the first line.", "G goes to the last line, so dG takes it all from here.", lambda ls: ls[:1], (2, 0)),
}

MAKERS = {
    **LINE_KINDS,
    "nav-down": lambda rng: _nav(rng, up=False),
    "nav-up": lambda rng: _nav(rng, up=True),
    "nav-find": _nav_find,
    "ci-quote": _ci_quote,
    "di-paren": lambda rng: _paren(rng, around=False),
    "da-paren": lambda rng: _paren(rng, around=True),
    "di-bracket": _di_bracket,
    "dt-letter": _dt_letter,
    "D-rest": _d_rest,
    "J-split": _j_split,
    "ddp-swap": _ddp_swap,
    "count-dw": _count_dw,
    "count-dd": _count_dd,
    "count-x": _count_x,
}
KINDS = ("ciw-typo", "daw-double", "ciW-dotted", *MAKERS)


def generate(kind: str, seed: str, parent: Task) -> Task:
    """A `kind` task from `seed`, with the parent task's hint and place in its lesson."""
    rng = random.Random(f"{kind}:{seed}")
    if kind in MAKERS:
        return replace(parent, ft="", variants=[], generated=seed, **MAKERS[kind](rng))
    while True:
        sentence = rng.choice(sentences())
        words = _words(sentence, spaced=kind == "ciW-dotted")
        if kind == "daw-double":
            words = [m for m in words if sentence[m.end()] == " "]
        if kind == "ciw-typo":
            words = [m for m in words if len(set(m.group()[1:-1])) > 1]
        if words:
            break
    m = rng.choice(words)
    word, before, after = m.group(), sentence[: m.start()], sentence[m.end():]
    if kind == "ciw-typo":
        while True:
            i = rng.randrange(1, len(word) - 2)
            if word[i] != word[i + 1]:
                break
        shown = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        start, cursor = before + shown + after, len(before) + rng.randrange(len(shown))
        goal, solution = f'Fix "{shown}" to "{word}".', f"ciw{word}<Esc>"
    elif kind == "daw-double":
        start = before + word + " " + word + after
        cursor = len(before) + rng.choice([0, len(word) + 1]) + rng.randrange(len(word))
        goal, solution = f'Delete the doubled "{word}".', "daw"
    elif kind == "ciW-dotted":
        shown = ".".join(word)
        start, cursor = before + shown + after, len(before) + rng.randrange(len(shown))
        goal, solution = f'Write the dotted "{shown}" as "{word}".', f"ciW{word}<Esc>"
    else:
        raise ValueError(f"no generator called {kind}")
    return replace(parent, goal=goal, start=[start], cursor=(1, cursor), target=[sentence],
                   solution=solution, ft="", variants=[], generated=seed)
