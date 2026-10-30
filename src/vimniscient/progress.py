"""Progress, kept in ~/.local/share/vimniscient/progress.db."""

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from vimniscient import srs
from vimniscient.cards import DECK_ORDER, Card, Deck
from vimniscient.lessons import Lesson, Task
from vimniscient.session import TaskResult
from vimniscient.vimgolf import Challenge

# VIMNISCIENT_DATA points somewhere else, e.g. for testing without touching real progress.
DATA_DIR = Path(
    os.environ.get("VIMNISCIENT_DATA") or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "vimniscient"
)
STARTED_FILE = DATA_DIR / "started"
# hardtime hints until you've learnt the alternatives it points to (week 2: counts,
# find, search, the dot) and at least four weeks have passed, then it blocks.
# The phase goes in HARDTIME_FILE, read by ~/.config/nvim/lua/plugins/vimniscient.lua.
HARDTIME_FILE = DATA_DIR / "hardtime"
HARDTIME_MIN_DAYS = 28
HARDTIME_AFTER = "w2d7-review"

NEW_CARDS_PER_DAY = 10
VIM_FIRST_WEEKS = 2  # new cards are Vim ones first until the lessons pass this week
NEW_DRILLS_PER_DAY = 2
MAX_DUE_CARDS = 30
MAX_REVIEW_TASKS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    lesson TEXT NOT NULL,
    task INTEGER NOT NULL,
    status TEXT NOT NULL,
    count INTEGER NOT NULL,
    ref INTEGER NOT NULL,
    keys TEXT NOT NULL,
    hints INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ease REAL NOT NULL,
    interval REAL NOT NULL,
    due TEXT NOT NULL,
    reps INTEGER NOT NULL,
    lapses INTEGER NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS card_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    card TEXT NOT NULL,
    correct INTEGER NOT NULL,
    answer TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS placed (
    lesson TEXT PRIMARY KEY,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drill_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    drill TEXT NOT NULL,
    seconds REAL NOT NULL,
    hinted INTEGER NOT NULL,
    skipped INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS endless_runs (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    start INTEGER NOT NULL,
    level INTEGER NOT NULL,
    climbed INTEGER NOT NULL,
    missed INTEGER NOT NULL,
    fixed INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS vimgolf (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    assigned TEXT NOT NULL,
    best INTEGER,
    score INTEGER,
    solved TEXT
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Progress:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not STARTED_FILE.exists():
            STARTED_FILE.write_text(date.today().isoformat() + "\n")
        self.db = sqlite3.connect(DATA_DIR / "progress.db")
        self.db.executescript(SCHEMA)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(attempts)")}
        if "phase" not in columns:  # databases from before the Learn/Recall rounds
            self.db.execute("ALTER TABLE attempts ADD COLUMN phase TEXT NOT NULL DEFAULT 'recall'")
        # from before tasks were timed: those attempts keep NULL, unknown
        for column in ("seconds", "first"):
            if column not in columns:
                self.db.execute(f"ALTER TABLE attempts ADD COLUMN {column} REAL")
        # cards typed with the answer shown (introductions): they count as practice, not as answers
        if "intro" not in {row[1] for row in self.db.execute("PRAGMA table_info(card_log)")}:
            self.db.execute("ALTER TABLE card_log ADD COLUMN intro INTEGER NOT NULL DEFAULT 0")
        self.db.commit()

    # spaced repetition items

    def item(self, item_id: str) -> srs.Item | None:
        row = self.db.execute(
            "SELECT id, kind, ease, interval, due, reps, lapses, created FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return None
        return srs.Item(row[0], row[1], row[2], row[3], date.fromisoformat(row[4]), row[5], row[6], date.fromisoformat(row[7]))

    def items(self, kind: str) -> dict[str, srs.Item]:
        rows = self.db.execute(
            "SELECT id, kind, ease, interval, due, reps, lapses, created FROM items WHERE kind = ?", (kind,)
        )
        return {
            r[0]: srs.Item(r[0], r[1], r[2], r[3], date.fromisoformat(r[4]), r[5], r[6], date.fromisoformat(r[7]))
            for r in rows
        }

    def _save(self, item: srs.Item) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO items (id, kind, ease, interval, due, reps, lapses, created) VALUES (?,?,?,?,?,?,?,?)",
            (item.id, item.kind, item.ease, item.interval, item.due.isoformat(), item.reps, item.lapses, item.created.isoformat()),
        )

    def grade(self, item_id: str, kind: str, grade: int) -> srs.Item:
        item = self.item(item_id) or srs.Item(item_id, kind)
        srs.review(item, grade, date.today())
        self._save(item)
        self.db.commit()
        return item

    # vim tasks

    def record(self, results: list[TaskResult]) -> None:
        ts = _now()
        for r in results:
            if r.status == "unseen" or (r.status == "quit" and not r.keys):
                continue  # not tried: opening a lesson and leaving isn't an attempt
            self.db.execute(
                "INSERT INTO attempts (ts, lesson, task, status, count, ref, keys, hints, phase, seconds, first) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ts, r.task.lesson_id, r.task.index, r.status, r.count, r.task.ref, r.keys, r.hints, r.task.phase,
                 r.seconds, r.first),
            )
            # Only recall says whether you know it; the Learn round shows the keys.
            grade = srs.task_grade(r.status, r.count, r.task.ref, r.hints)
            if grade is None or r.task.phase != "recall":
                continue
            item = self.item(r.task.item_id) or srs.Item(r.task.item_id, "task")
            srs.review(item, grade, date.today())
            self._save(item)
        self.db.commit()

    def best(self, lesson: Lesson) -> dict[int, int]:
        """Fewest keys per solved task index."""
        rows = self.db.execute(
            "SELECT task, MIN(count) FROM attempts WHERE lesson = ? AND status = 'solved' AND phase = 'recall' GROUP BY task",
            (lesson.id,),
        )
        return dict(rows.fetchall())

    def is_placed(self, lesson: Lesson) -> bool:
        return self.db.execute("SELECT 1 FROM placed WHERE lesson = ?", (lesson.id,)).fetchone() is not None

    def is_done(self, lesson: Lesson) -> bool:
        return self.is_placed(lesson) or len(self.best(lesson)) == len(lesson.tasks)

    def next_lesson(self, lessons: list[Lesson]) -> Lesson | None:
        return next((lesson for lesson in lessons if not self.is_done(lesson)), None)

    def lesson_today(self) -> bool:
        """Whether a lesson ran today. Only lessons have a Learn round, so a review
        (whose tasks are stored under their own lesson) doesn't count."""
        today = date.today().isoformat()
        row = self.db.execute("SELECT 1 FROM attempts WHERE phase = 'learn' AND ts >= ? LIMIT 1", (today,)).fetchone()
        return row is not None

    def practised_today(self) -> set[str]:
        """Item ids of the tasks tried today, in any session."""
        today = date.today().isoformat()
        rows = self.db.execute("SELECT lesson, task FROM attempts WHERE ts >= ? AND status != 'quit'", (today,))
        return {f"task:{lesson}#{task}" for lesson, task in rows}

    def current_week(self, lessons: list[Lesson]) -> int:
        nxt = self.next_lesson(lessons)
        return nxt.week if nxt else max(lesson.week for lesson in lessons) + 1

    def version_for(self, task: Task) -> Task:
        """The next version of a task to practise: each recall moves on to another text."""
        (n,) = self.db.execute(
            "SELECT COUNT(*) FROM attempts WHERE lesson = ? AND task = ? AND phase = 'recall' AND status != 'quit'",
            (task.lesson_id, task.index),
        ).fetchone()
        return task.choice(n + 1, f"{task.item_id}:{n}")

    def due_tasks(self, lessons: list[Lesson], limit: int | None = MAX_REVIEW_TASKS) -> list[Task]:
        """Tasks from earlier days that are due for review, most overdue first."""
        today = date.today()
        tasks = {t.item_id: t for lesson in lessons for t in lesson.tasks}
        due = sorted(
            (item for item in self.items("task").values() if item.due <= today and item.id in tasks),
            key=lambda item: (item.due, -item.lapses),
        )
        return [self.version_for(tasks[item.id]) for item in due[:limit]]

    def place(self, lessons: list[Lesson], results: list[TaskResult]) -> list[Lesson]:
        """Mark lessons as known from a placement run; returns the lessons placed."""
        passed: dict[str, list[bool]] = {}
        for r in results:
            ok = srs.task_grade(r.status, r.count, r.task.ref, r.hints) in (srs.GOOD, srs.EASY)
            passed.setdefault(r.task.lesson_id, []).append(ok)
        placed = [lesson for lesson in lessons if passed.get(lesson.id) and all(passed[lesson.id])]
        # A week's review day counts as placed when every lesson of that week is.
        for week in {lesson.week for lesson in lessons}:
            days = [lesson for lesson in lessons if lesson.week == week]
            tested = [lesson for lesson in days if lesson.id in passed]
            if tested and all(lesson in placed for lesson in tested):
                placed += [lesson for lesson in days if lesson.id not in passed and lesson not in placed]
        tested_ids = {r.task.item_id for r in results}
        for lesson in placed:
            self.db.execute("INSERT OR IGNORE INTO placed (lesson, ts) VALUES (?, ?)", (lesson.id, _now()))
            # The tasks that weren't tested come up in review within a week.
            for t in lesson.tasks:
                if t.item_id not in tested_ids and not self.item(t.item_id):
                    self._save(srs.Item(t.item_id, "task", interval=7, due=date.today() + timedelta(days=7),
                                        created=date.today()))
        self.db.commit()
        return placed

    # cards

    def log_card(self, card: Card, correct: bool, answer: str, intro: bool = False) -> None:
        self.db.execute(
            "INSERT INTO card_log (ts, card, correct, answer, intro) VALUES (?,?,?,?,?)",
            (_now(), card.id, int(correct), answer, int(intro)),
        )
        self.db.commit()

    def ever_right(self, card_id: str) -> bool:
        """Whether this card was ever answered from memory (not just typed when introduced)."""
        return self.db.execute("SELECT 1 FROM card_log WHERE card = ? AND correct = 1 AND intro = 0 LIMIT 1", (card_id,)).fetchone() is not None

    def unlocked(self, decks: dict[str, Deck], lessons: list[Lesson]) -> list[Card]:
        """Cards for lessons you've done: a card with a `day` waits for that day's lesson,
        one with only a `week` comes in when that week starts."""
        nxt = self.next_lesson(lessons)
        reached = (nxt.week, nxt.day) if nxt else (max(lesson.week for lesson in lessons) + 1, 0)
        return [card for deck in decks.values() for card in deck.cards
                if (card.week, card.day) < reached or card.week == reached[0] and not card.day]

    def due_cards(self, decks: dict[str, Deck], lessons: list[Lesson], limit: int | None = MAX_DUE_CARDS) -> list[Card]:
        today = date.today()
        items = self.items("card")
        due = [c for c in self.unlocked(decks, lessons) if c.id in items and items[c.id].due <= today]
        due.sort(key=lambda c: items[c.id].due)
        return due[:limit]

    def new_cards(self, decks: dict[str, Deck], lessons: list[Lesson]) -> list[Card]:
        """Today's unseen cards, taking turns between decks."""
        items = self.items("card")
        today = date.today()
        left = NEW_CARDS_PER_DAY - sum(1 for item in items.values() if item.created == today)
        unseen: dict[str, list[Card]] = {}
        for card in self.unlocked(decks, lessons):
            if card.id not in items:
                unseen.setdefault(card.deck, []).append(card)
        for cards in unseen.values():
            cards.sort(key=lambda c: c.order)
        picked: list[Card] = []
        order = [d for d in DECK_ORDER if d in unseen] + [d for d in unseen if d not in DECK_ORDER]
        # In the first weeks, Vim (and your own habits) before the other decks.
        if self.current_week(lessons) <= VIM_FIRST_WEEKS:
            for deck in ("habits", "vim"):
                while left > 0 and unseen.get(deck):
                    picked.append(unseen[deck].pop(0))
                    left -= 1
        while left > 0 and any(unseen.get(d) for d in order):
            for deck in order:
                if left > 0 and unseen.get(deck):
                    picked.append(unseen[deck].pop(0))
                    left -= 1
        return picked

    # endless mode

    def record_ungraded(self, results: list[TaskResult], phase: str) -> None:
        """Choose and quick practice: like Endless, for the streak and not for grades."""
        ts = _now()
        for r in results:
            if r.status != "unseen" and not (r.status == "quit" and not r.keys):
                self.db.execute(
                    "INSERT INTO attempts (ts, lesson, task, status, count, ref, keys, hints, phase, seconds, first) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ts, r.task.lesson_id, r.task.index, r.status, r.count, r.task.ref, r.keys, r.hints, phase,
                     r.seconds, r.first),
                )
        self.db.commit()

    def transfer_last(self) -> dict[int, str]:
        """When each Choose task was last tried."""
        return dict(self.db.execute("SELECT task, MAX(ts) FROM attempts WHERE phase = 'transfer' GROUP BY task"))

    def record_endless(self, results: list[TaskResult], run: dict[str, int]) -> None:
        """Attempts go in as phase 'endless': they count for the streak, not for lessons or reviews."""
        ts = _now()
        results = [r for r in results if not (r.status == "quit" and not r.keys)]
        for r in results:
            self.db.execute(
                "INSERT INTO attempts (ts, lesson, task, status, count, ref, keys, hints, phase, seconds, first) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ts, r.task.lesson_id, r.task.index, r.status, r.count, r.task.ref, r.keys, r.hints, "endless",
                 r.seconds, r.first),
            )
        if results:
            self.db.execute(
                "INSERT INTO endless_runs (ts, start, level, climbed, missed, fixed) VALUES (?,?,?,?,?,?)",
                (ts, run["start"], run["level"], run["climbed"], run["missed"], run["fixed"]),
            )
        self.db.commit()

    def endless_best(self) -> int:
        (best,) = self.db.execute("SELECT MAX(level) FROM endless_runs").fetchone()
        return best or 0

    def endless_start(self, below: int) -> int:
        """Where a new run starts: a little below where the last one ended."""
        row = self.db.execute("SELECT level FROM endless_runs ORDER BY id DESC LIMIT 1").fetchone()
        return max(1, row[0] - below) if row else 1

    # omarchy drills

    def log_drill(self, drill_id: str, seconds: float, hinted: bool, skipped: bool) -> None:
        self.db.execute(
            "INSERT INTO drill_log (ts, drill, seconds, hinted, skipped) VALUES (?,?,?,?,?)",
            (_now(), drill_id, seconds, int(hinted), int(skipped)),
        )
        self.db.commit()

    def due_drills(self, drills: list) -> list:
        today = date.today()
        items = self.items("drill")
        return [d for d in drills if d.item_id in items and items[d.item_id].due <= today]

    def new_drills(self, drills: list) -> list:
        items = self.items("drill")
        left = NEW_DRILLS_PER_DAY - sum(1 for item in items.values() if item.created == date.today())
        return [d for d in drills if d.item_id not in items][: max(0, left)]

    # vimgolf

    def vimgolf_today(self, index: list[dict], fetch) -> "Challenge | None":
        """Today's challenge: the one given out today, else the most played one not tried yet that fits."""
        today = date.today().isoformat()
        row = self.db.execute("SELECT id FROM vimgolf WHERE assigned = ? ORDER BY rowid DESC LIMIT 1", (today,)).fetchone()
        entries = {e["id"]: e for e in index}
        if row and row[0] in entries:
            return fetch(entries[row[0]])
        tried = {cid for (cid,) in self.db.execute("SELECT id FROM vimgolf")}
        for entry in index:
            if entry["id"] in tried:
                continue
            challenge = fetch(entry)
            if not challenge.fits:
                # Remember it so it isn't fetched again tomorrow.
                self.db.execute("INSERT OR IGNORE INTO vimgolf (id, title, assigned) VALUES (?, ?, '')", (entry["id"], entry["title"]))
                self.db.commit()
                continue
            self.db.execute(
                "INSERT INTO vimgolf (id, title, assigned, best) VALUES (?, ?, ?, ?)",
                (challenge.id, challenge.title, today, challenge.best),
            )
            self.db.commit()
            return challenge
        return None

    def record_vimgolf(self, challenge_id: str, result: TaskResult, save_keys: int) -> int | None:
        """Store a solved run; returns the VimGolf-style score (keys + saving)."""
        if result.status != "solved":
            return None
        score = result.count + save_keys
        self.db.execute(
            "UPDATE vimgolf SET score = MIN(COALESCE(score, ?), ?), solved = COALESCE(solved, ?) WHERE id = ?",
            (score, score, _now(), challenge_id),
        )
        self.db.commit()
        return score

    def vimgolf_done_today(self) -> bool:
        today = date.today().isoformat()
        return self.db.execute("SELECT 1 FROM vimgolf WHERE assigned = ? AND solved IS NOT NULL", (today,)).fetchone() is not None

    def vimgolf_history(self, limit: int = 10) -> list[tuple[str, str, int | None, int | None]]:
        """(day, title, your score, best) for challenges given out, newest first."""
        rows = self.db.execute(
            "SELECT assigned, title, score, best FROM vimgolf WHERE assigned != '' ORDER BY assigned DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return list(rows)

    # overview

    def days_trained(self) -> set[date]:
        rows = self.db.execute(
            "SELECT DISTINCT substr(ts, 1, 10) FROM attempts UNION SELECT DISTINCT substr(ts, 1, 10) FROM card_log "
            "UNION SELECT DISTINCT substr(ts, 1, 10) FROM drill_log"
        )
        return {date.fromisoformat(d) for (d,) in rows}

    def streak(self) -> int:
        days = self.days_trained()
        day = date.today() if date.today() in days else date.today() - timedelta(days=1)
        n = 0
        while day in days:
            n += 1
            day -= timedelta(days=1)
        return n

    def typical_task_seconds(self) -> float | None:
        """The median time of a timed task, once there are enough of them to go by."""
        rows = [s for (s,) in self.db.execute(
            "SELECT seconds FROM attempts WHERE seconds IS NOT NULL ORDER BY id DESC LIMIT 200")]
        return sorted(rows)[len(rows) // 2] if len(rows) >= 10 else None

    def seconds_today(self, card_seconds: float, task_seconds: float) -> float:
        """About how long you've practised today: timed tasks as timed, the rest estimated."""
        today = date.today().isoformat()
        timed, untimed = self.db.execute(
            "SELECT COALESCE(SUM(seconds), 0), SUM(seconds IS NULL) FROM attempts WHERE ts >= ? AND status != 'quit'",
            (today,)).fetchone()
        (cards,) = self.db.execute("SELECT COUNT(*) FROM card_log WHERE ts >= ?", (today,)).fetchone()
        (drills,) = self.db.execute("SELECT COALESCE(SUM(seconds), 0) FROM drill_log WHERE ts >= ?", (today,)).fetchone()
        return timed + (untimed or 0) * task_seconds + cards * card_seconds + drills

    def speed_by_lesson(self, recent: int = 3) -> dict[str, tuple[int, float, float, float | None]]:
        """Per lesson, from tasks solved from memory (Recall, reviews, Endless) that were timed:
        how many, the median time of the first `recent` and of the latest `recent`, and the
        median time before the first key lately. Lessons with fewer than two are left out."""
        rows = self.db.execute(
            "SELECT lesson, seconds, first FROM attempts WHERE status = 'solved' AND phase != 'learn' "
            "AND seconds IS NOT NULL ORDER BY id"
        ).fetchall()
        by_lesson: dict[str, list[tuple[float, float | None]]] = {}
        for lesson, seconds, first in rows:
            by_lesson.setdefault(lesson, []).append((seconds, first))

        def median(values: list[float]) -> float:
            values = sorted(values)
            mid = len(values) // 2
            return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

        out = {}
        for lesson, timed in by_lesson.items():
            if len(timed) < 2:
                continue
            latest = timed[-recent:]
            firsts = [f for _, f in latest if f is not None]
            out[lesson] = (len(timed), median([s for s, _ in timed[:recent]]), median([s for s, _ in latest]),
                           median(firsts) if firsts else None)
        return out

    def efficiency_by_day(self, limit: int = 7) -> list[tuple[str, int, int, int]]:
        """(day, solved tasks, keys typed, reference keys) for recent training days."""
        rows = self.db.execute(
            "SELECT substr(ts, 1, 10) AS d, COUNT(*), SUM(count), SUM(ref) FROM attempts "
            "WHERE status = 'solved' AND phase = 'recall' GROUP BY d ORDER BY d DESC LIMIT ?",
            (limit,),
        )
        return list(rows)

    def card_accuracy(self, limit: int = 7) -> list[tuple[str, int, int]]:
        """(day, answered, correct) for recent card days."""
        rows = self.db.execute(
            "SELECT substr(ts, 1, 10) AS d, COUNT(*), SUM(correct) FROM card_log WHERE intro = 0 GROUP BY d ORDER BY d DESC LIMIT ?",
            (limit,),
        )
        return list(rows)

    def hardest(self, limit: int = 6) -> list[srs.Item]:
        rows = self.db.execute("SELECT id FROM items WHERE lapses > 0 ORDER BY lapses DESC, ease ASC LIMIT ?", (limit,))
        return [self.item(item_id) for (item_id,) in rows]

    def hardtime_earliest(self) -> date:
        """The first day hardtime may block, lessons allowing."""
        started = date.fromisoformat(STARTED_FILE.read_text().strip())
        return started + timedelta(days=HARDTIME_MIN_DAYS)

    def hardtime_blocks(self, lessons: list[Lesson]) -> bool:
        after = next((lesson for lesson in lessons if lesson.id == HARDTIME_AFTER), None)
        return date.today() >= self.hardtime_earliest() and (after is None or self.is_done(after))

    def sync_hardtime(self, lessons: list[Lesson]) -> bool:
        """Write hardtime's phase for the Neovim config; True when it blocks."""
        blocks = self.hardtime_blocks(lessons)
        phase = "block" if blocks else "hint"
        if not HARDTIME_FILE.exists() or HARDTIME_FILE.read_text().strip() != phase:
            HARDTIME_FILE.write_text(phase + "\n")
        return blocks
