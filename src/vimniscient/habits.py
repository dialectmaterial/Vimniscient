"""Bad habits, read from hardtime.nvim's log (~/.local/state/nvim/hardtime.nvim.log).

hardtime writes three kinds of message:
  Use dj instead of 2dd                          -> a card: what's shorter than 2dd?
  You pressed the j key too soon! Use [count]j…  -> drill the motion lessons
  The <Up> key is disabled!                      -> same, for arrow keys
"""

import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from vimniscient.cards import Card, Deck

LOG = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "nvim" / "hardtime.nvim.log"

_LINE = re.compile(r"^\[\w+\s+\w{3} (\d{2} \w{3} \d{4}) [^\]]*\] (.+)$")
_USE = re.compile(r"^Use (.+) instead of (.+)$")
_TOO_SOON = re.compile(r"^You pressed the (\S+) key too soon!")
_DISABLED = re.compile(r"^The (\S+) key is disabled!")

# Keys pressed over and over -> lessons that teach the better motions.
DRILL_LESSONS = {
    "j": ["w1d6-counts", "w2d2-search", "w1d3-sentences"],
    "k": ["w1d6-counts", "w2d2-search", "w1d3-sentences"],
    "h": ["w1d4-find", "w1d1-words"],
    "l": ["w1d4-find", "w1d1-words"],
}
_ARROWS = {"<Down>": "j", "<Up>": "k", "<Left>": "h", "<Right>": "l"}


@dataclass
class Habit:
    message: str
    total: int
    recent: int  # in the last two weeks
    last: date


def read_log() -> list[tuple[date, str]]:
    if not LOG.exists():
        return []
    entries = []
    for line in LOG.read_text(errors="replace").splitlines():
        m = _LINE.match(line.strip())
        if not m:
            continue
        try:
            day = datetime.strptime(m.group(1), "%d %b %Y").date()
        except ValueError:
            continue
        entries.append((day, m.group(2).strip()))
    return entries


def habits(days: int = 14) -> list[Habit]:
    """Every distinct message, most frequent recently first."""
    since = date.today() - timedelta(days=days)
    total: Counter[str] = Counter()
    recent: Counter[str] = Counter()
    last: dict[str, date] = {}
    for day, message in read_log():
        total[message] += 1
        if day >= since:
            recent[message] += 1
        last[message] = max(day, last.get(message, day))
    return sorted(
        (Habit(m, total[m], recent[m], last[m]) for m in total),
        key=lambda h: (-h.recent, -h.total, h.message),
    )


def habit_deck() -> Deck:
    """One card per "Use X instead of Y" hint, most frequent first."""
    deck = Deck("habits", "Your habits")
    for i, habit in enumerate(habits()):
        m = _USE.match(habit.message)
        if not m:
            continue
        better, worse = m.group(1), m.group(2)
        deck.cards.append(
            Card(
                deck="habits",
                id=f"habits:{habit.message}",
                prompt=f"hardtime caught you typing {worse}. What's the better way?",
                answers=[better],
                style="keys",
                case_sensitive=True,
                note=f"hardtime caught this {habit.total}×.",
                order=i,
            )
        )
    return deck


def drill_lessons(days: int = 7) -> list[str]:
    """Lessons worth repeating because of keys pressed over and over lately."""
    since = date.today() - timedelta(days=days)
    keys: Counter[str] = Counter()
    for day, message in read_log():
        if day < since:
            continue
        m = _TOO_SOON.match(message) or _DISABLED.match(message)
        if m:
            key = _ARROWS.get(m.group(1), m.group(1))
            if key in DRILL_LESSONS:
                keys[key] += 1
    lessons: list[str] = []
    for key, _ in keys.most_common():
        lessons += [lesson for lesson in DRILL_LESSONS[key] if lesson not in lessons]
    return lessons
