"""Challenges from vimgolf.com, played in the user's own Neovim.

The challenge list and each challenge (start file, end file, best score on
the leaderboard) are cached in ~/.cache/vimniscient/vimgolf/.
"""

import json
import re
import time
import urllib.request
from dataclasses import dataclass

from vimniscient.cards import CACHE_DIR

BASE = "https://www.vimgolf.com"
CACHE = CACHE_DIR / "vimgolf"
INDEX_MAX_AGE = 7 * 86400
# A challenge has to fit the goal + practice split.
MAX_LINES = 40
MAX_WIDTH = 100
# VimGolf scores include saving and quitting (ZZ); lessons finish by themselves.
SAVE_KEYS = 2

_ID = re.compile(r"[0-9a-z]{24}")


@dataclass
class Challenge:
    id: str
    title: str
    entries: int
    start: list[str]
    target: list[str]
    best: int | None  # lowest score on the leaderboard, ZZ included

    @property
    def url(self) -> str:
        return f"{BASE}/challenges/{self.id}"

    @property
    def fits(self) -> bool:
        lines = self.start + self.target
        return len(self.start) <= MAX_LINES and len(self.target) <= MAX_LINES and max(map(len, lines), default=0) <= MAX_WIDTH


def _get(url: str, accept: str) -> str:
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "vimniscient"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", "replace")


def index() -> list[dict]:
    """[{id, title, entries}], most played first."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "index.json"
    if path.exists() and time.time() - path.stat().st_mtime < INDEX_MAX_AGE:
        return json.loads(path.read_text())
    found: dict[str, dict] = {}
    for page in range(1, 40):
        html = _get(f"{BASE}/?page={page}", "text/html")
        rows = re.findall(r'href="/challenges/([0-9a-z]{24})">([^<]*)</a> - (\d+) entries', html)
        if not rows:
            break
        for cid, title, entries in rows:
            found.setdefault(cid, {"id": cid, "title": _unescape(title), "entries": int(entries)})
    challenges = sorted(found.values(), key=lambda c: -c["entries"])
    if challenges:
        path.write_text(json.dumps(challenges))
    return challenges


def _unescape(text: str) -> str:
    return (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    )


def _lines(data: str) -> list[str]:
    data = data.replace("\r\n", "\n")
    return data.removesuffix("\n").split("\n")


def challenge(entry: dict) -> Challenge:
    cid = entry["id"]
    if not _ID.fullmatch(cid):
        raise ValueError(f"not a VimGolf challenge id: {cid!r}")
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{cid}.json"
    if path.exists():
        data = json.loads(path.read_text())
    else:
        raw = json.loads(_get(f"{BASE}/challenges/{cid}.json", "application/json"))
        html = _get(f"{BASE}/challenges/{cid}", "text/html")
        scores = re.findall(r'href="/challenges/[0-9a-z]+/user/[^"]+">(\d+)</a>', html)
        data = {"in": raw["in"]["data"], "out": raw["out"]["data"], "best": int(scores[0]) if scores else None}
        path.write_text(json.dumps(data))
    return Challenge(cid, entry["title"], entry["entries"], _lines(data["in"]), _lines(data["out"]), data["best"])
