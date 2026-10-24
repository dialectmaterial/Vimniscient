"""Counting keystrokes written in Vim key notation (`ciwfoo<Esc>`)."""

import re

_TOKEN = re.compile(r"<[^<>\s]+>|.", re.S)


def split_keys(keys: str) -> list[str]:
    """Split `ci"x<Esc>` into ['c', 'i', '"', 'x', '<Esc>']."""
    return _TOKEN.findall(keys)


def count_keys(keys: str) -> int:
    return len(split_keys(keys))
