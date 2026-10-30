"""Practice texts made from a seed, for skills where any sentence will do.

A lesson task can name a `generate` kind. Its Learn round keeps the authored
text; Recall and reviews can get a generated one instead, so a skill gets
practised on sentences you haven't seen. The same seed always gives the same
task, so a run can be replayed and every kind can be checked in Neovim
(tests/check_generate.py).

The sentences stay mnemonic: they're the hooks from mnemonics.yaml, what keys
stand for.

Kinds, all word text objects (w1d1):
  ciw-typo    two letters of a word swapped; ciw and type it right
  daw-double  a word doubled; daw deletes one copy and its space
  ciW-dotted  a word written with dots between its letters; ciW rewrites it
"""

import random
import re
from dataclasses import replace
from functools import cache

from vimniscient.lessons import Task
from vimniscient.mnemonics import _tables

KINDS = ("ciw-typo", "daw-double", "ciW-dotted")

@cache
def sentences() -> list[str]:
    hooks = list(dict.fromkeys(hook for table in _tables()[:2] for hook in table.values()))
    # as written: a capital would change the key ("u is down" is not "U is down")
    return [h + ("" if h.endswith(".") else ".") for h in hooks]


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


def generate(kind: str, seed: str, parent: Task) -> Task:
    """A `kind` task from `seed`, with the parent task's hint and place in its lesson."""
    rng = random.Random(f"{kind}:{seed}")
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
