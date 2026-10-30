"""Checking typed answers to cards.

Two styles: `keys` for key sequences (`ciw`, `<C-a>`, `<leader>ff`) and
`combo` for chords (`SUPER SHIFT + B`). Both accept the usual ways of
writing the same thing: `ctrl-a`, `^a` and `<C-a>`; `space ff` and
`<leader>ff`; `super+shift+b` and `SUPER SHIFT + B`.
"""

import re

LEADER = "\x00"

_TOKEN_NAMES = {
    "esc": "<Esc>", "escape": "<Esc>",
    "cr": "<CR>", "enter": "<CR>", "return": "<CR>",
    "tab": "<Tab>", "bs": "<BS>", "backspace": "<BS>",
    "space": "<Space>", "lt": "<", "bar": "|", "bslash": "\\",
    "home": "<Home>", "end": "<End>", "del": "<Del>", "delete": "<Del>",
    "up": "<Up>", "down": "<Down>", "left": "<Left>", "right": "<Right>",
}


def _norm_token(match: re.Match) -> str:
    inner = match.group(1)
    low = inner.lower()
    if low in ("leader", "space") and match.start() == 0:
        return LEADER
    if low in _TOKEN_NAMES:
        return _TOKEN_NAMES[low]
    m = re.fullmatch(r"([csma])-(.+)", inner, re.I)
    if m:
        mod = {"c": "C", "s": "S", "m": "M", "a": "M"}[m.group(1).lower()]
        key = m.group(2)
        key = key.lower() if mod == "C" and len(key) == 1 else key
        return f"<{mod}-{key}>"
    if re.fullmatch(r"f\d+", low):
        return f"<F{low[1:]}>"
    return f"<{inner}>"


def norm_keys(text: str, case_sensitive: bool = True) -> str:
    s = text.strip()
    s = re.sub(r"(?i)^(leader|space|spc)(\s*\+\s*|\s+|$)", "<leader>", s)
    s = re.sub(r"(?i)(?<![<\w])space(?![>\w])", "<Space>", s)
    s = re.sub(r"(?i)\b(?:ctrl|control)[-+ ]+(\S)", lambda m: f"<C-{m.group(1)}>", s)
    s = re.sub(r"(?i)\b(?:alt|meta)[-+ ]+(\S)", lambda m: f"<M-{m.group(1)}>", s)
    s = re.sub(r"\^([A-Za-z_\[\]])", lambda m: f"<C-{m.group(1)}>", s)
    s = re.sub(r"<([^<>\s]+)>", _norm_token, s)
    s = re.sub(r"\s+", "", s)
    s = s.removesuffix("<CR>") if s.startswith(":") else s
    return s if case_sensitive else s.lower()


_MOD_ALIASES = {
    "SUPER": "SUPER", "WIN": "SUPER", "CMD": "SUPER", "MOD": "SUPER", "LOGO": "SUPER",
    "CTRL": "CTRL", "CONTROL": "CTRL", "CTL": "CTRL",
    "ALT": "ALT", "OPT": "ALT", "OPTION": "ALT", "MOD1": "ALT", "META": "ALT",
    "SHIFT": "SHIFT", "PREFIX": "PREFIX", "LEADER": "PREFIX", "COPYMODE": "COPYMODE",
}
_KEY_ALIASES = {
    "ENTER": "RETURN", "CR": "RETURN", "ESC": "ESCAPE", "DEL": "DELETE", "INS": "INSERT",
    "PGUP": "PAGE_UP", "PAGEUP": "PAGE_UP", "PRIOR": "PAGE_UP",
    "PGDN": "PAGE_DOWN", "PAGEDOWN": "PAGE_DOWN", "NEXT": "PAGE_DOWN",
    "=": "EQUAL", "-": "MINUS", "+": "PLUS", "SPACEBAR": "SPACE",
    "PRTSC": "PRINT", "PRINTSCREEN": "PRINT",
}


def norm_combo(text: str, case_sensitive: bool = False) -> tuple[frozenset[str], tuple[str, ...]]:
    s = re.sub(r"(?i)copy\s+mode", "COPYMODE", text.strip())
    s = re.sub(r"(?i)page\s+(up|down)", lambda m: f"PAGE_{m.group(1)}", s)
    plus_key = bool(re.search(r"[\s+]\+\s*$", s))  # "CTRL + +" or "CTRL +"
    if plus_key:
        s = re.sub(r"\+\s*$", "", s)
    parts: list[str] = []
    for part in re.split(r"[\s+]+", s):
        if len(part) > 1 and "-" in part:
            parts.extend(p for p in part.split("-") if p)
        elif part:
            parts.append(part)
    if plus_key:
        parts.append("+")
    mods: set[str] = set()
    keys: list[str] = []
    for part in parts:
        mod = _MOD_ALIASES.get(part.upper())
        if mod:
            mods.add(mod)
            continue
        key = _KEY_ALIASES.get(part.upper(), part)
        if not (case_sensitive and len(key) == 1):
            key = key.upper()
        keys.append(key)
    # SHIFT + c is C when case matters (tmux)
    if case_sensitive and "SHIFT" in mods and len(keys) == 1 and keys[0].isalpha() and len(keys[0]) == 1:
        mods.discard("SHIFT")
        keys = [keys[0].upper()]
    return frozenset(mods), tuple(keys)


def is_correct(answer: str, expected: list[str], style: str, case_sensitive: bool) -> bool:
    if not answer.strip():
        return False
    if style == "combo":
        got = norm_combo(answer, case_sensitive)
        return any(got == norm_combo(e, case_sensitive) for e in expected)
    got = norm_keys(answer, case_sensitive)
    return any(got == norm_keys(e, case_sensitive) for e in expected)


def pretty_keys(keys: str) -> str:
    """`<Space>ff` reads better as `<leader>ff`."""
    return re.sub(r"^<Space>", "<leader>", keys)
