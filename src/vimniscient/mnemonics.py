"""What keys stand for: `mnemonics.yaml` read as tables, and `hooks()`, which
splits a key sequence like `ciw` or `:%s//x/g` into its parts and returns the
hook for each one. Shown after an answer, never before (it names the keys)."""

import re
from functools import cache
from importlib import resources

import yaml

OPERATORS = {"c", "d", "y", "gU", "gu", "g~", ">", "<", "gc"}
# keys that take one character after them: f{char}, ma, "a, @a, r{char} ...
TAKES_CHAR = {"f", "t", "F", "T", "m", "'", "`", "q", "@", "r", "<C-r>"}
# keys that leave you typing text until <Esc>
INSERTS = {"i", "a", "A", "I", "o", "O", "R", "C", "s", "S", "cc"}
PAIRS = "()[]{}<>\"'`"
MAX_HOOKS = 4


@cache
def _tables() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """(normal-mode keys, text objects, ex commands), each key → hook."""
    data = yaml.safe_load((resources.files("vimniscient") / "mnemonics.yaml").read_text(encoding="utf-8"))
    normal: dict[str, str] = {}
    objects: dict[str, str] = {}
    ex: dict[str, str] = {}
    for key, entry in data.items():
        hook = entry["hook"]
        name, _, kind = key.partition(" (")
        kind = kind.rstrip(")")
        if kind == "object":
            objects[name] = hook
        elif kind == "range":
            ex["%"] = hook
        elif kind == "insert":
            normal["a (insert)"] = hook
        elif kind == "motion" or not kind:
            if not kind and name in ("w", "W", "s"):  # the nouns; w's motion has its own entry
                objects[name] = hook
            # "h j k l", "n N", "( b": several keys sharing one hook
            for part in name.split(" ") if " " in name and not name.startswith(":") else [name]:
                (ex if part.startswith(":") else normal)[part] = hook
    for char in PAIRS:  # every bracket and quote names its pair
        objects.setdefault(char, objects["("])
    return normal, objects, ex


def hooks(keys: str) -> list[str]:
    """The hooks for the parts of `keys`, in order, without repeats."""
    found = _ex_hooks(keys) if keys.startswith(":") else _normal_hooks(keys)
    seen: list[str] = []
    for hook in found:
        if hook and hook not in seen:
            seen.append(hook)
    return seen[:MAX_HOOKS]


def _normal_hooks(keys: str) -> list[str]:
    normal, objects, _ = _tables()
    by_length = sorted(normal, key=len, reverse=True)
    out: list[str] = []
    i = 0
    operator = ""
    while i < len(keys):
        rest = keys[i:]
        if rest.startswith(":"):  # a command inside a sequence, like *:%s//x/g
            end = rest.find("<CR>")
            out += _ex_hooks(rest if end < 0 else rest[:end])
            i += len(rest) if end < 0 else end + 4
            continue
        if rest[0].isdigit() and not (rest[0] == "0" and not (i and keys[i - 1].isdigit())):
            i += 1  # a count
            continue
        if rest[0] == '"' and len(rest) > 1:  # a register
            out.append(normal.get(rest[:2]) or normal.get(rest[:2].lower()) or normal['"'])
            i += 2
            continue
        if operator and rest[0] in "ia" and len(rest) > 1:  # a text object
            out += [normal[rest[0]], objects.get(rest[1], "")]
            i += 2
            i = _skip_insert(keys, i) if operator == "c" else i
            operator = ""
            continue
        token = next((k for k in by_length if " " not in k and rest.startswith(k)), "")
        if not token:
            i += 1
            continue
        if token == "a" and not operator:
            out.append(normal.get("a (insert)", ""))
        elif token != "i" or operator:
            out.append(normal[token])
        i += len(token)
        if token in TAKES_CHAR and i < len(keys):
            i += 4 if keys.startswith("<CR>", i) else 1
        if token in ("/", "?", "*"):
            end = keys.find("<CR>", i)
            i = i if token == "*" else (len(keys) if end < 0 else end + 4)
        if operator == "c" or token in INSERTS:
            i = _skip_insert(keys, i)
            operator = ""
        elif token in OPERATORS and not operator:
            operator = token
            double = token if keys.startswith(token, i) else token[-1]
            if keys.startswith(double, i):  # dd, >>, guu, gcc: the whole line
                out.append(normal.get("dd", ""))
                i += len(double)
                operator = ""
        else:
            operator = ""
    return out


def _skip_insert(keys: str, i: int) -> int:
    """Past the text typed in insert mode, up to and including <Esc>."""
    end = keys.find("<Esc>", i)
    return len(keys) if end < 0 else end + len("<Esc>")


def _ex_hooks(command: str) -> list[str]:
    _, _, ex = _tables()
    out: list[str] = []
    body = command.lstrip(":")
    match = re.match(r"([%.$,\d'<>+-]*)\s*([a-zA-Z]+|!)", body)
    if not match:
        return out
    span, name = match.groups()
    if "%" in span:
        out.append(ex.get("%", ""))
    names = [n for n in ex if n.startswith(":")]
    # the longest command name that this abbreviation starts (:s, :sort, :norm, :g)
    candidates = [n for n in names if n[1:] == name or (n[1:].startswith(name) and len(name) > 1)]
    if candidates:
        out.append(ex[min(candidates, key=len)])
    elif name == "!" or body.lstrip("%").startswith("!"):
        out.append(ex.get(":!", ""))
    if "norm" in body[match.end():]:
        out.append(ex.get(":norm", ""))
    for token in ("\\v", "&", "\\1"):
        if token in body:
            out.append(ex.get(token, ""))
    return out
