"""Progress, kept in ~/.local/share/vimniscient/progress.db."""

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from vimniscient.lessons import Lesson
from vimniscient.session import TaskResult

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "vimniscient"
# Read by ~/.config/nvim/lua/plugins/vimniscient.lua to time hardtime's switch to blocking.
STARTED_FILE = DATA_DIR / "started"
HARDTIME_HINT_DAYS = 14

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
"""


class Progress:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not STARTED_FILE.exists():
            STARTED_FILE.write_text(date.today().isoformat() + "\n")
        self.db = sqlite3.connect(DATA_DIR / "progress.db")
        self.db.executescript(SCHEMA)

    def record(self, lesson: Lesson, results: list[TaskResult]) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        self.db.executemany(
            "INSERT INTO attempts (ts, lesson, task, status, count, ref, keys, hints) VALUES (?,?,?,?,?,?,?,?)",
            [
                (ts, lesson.id, i, r.status, r.count, r.task.ref, r.keys, r.hints)
                for i, r in enumerate(results)
                if r.status != "unseen"
            ],
        )
        self.db.commit()

    def best(self, lesson: Lesson) -> dict[int, int]:
        """Fewest keys per solved task index."""
        rows = self.db.execute(
            "SELECT task, MIN(count) FROM attempts WHERE lesson = ? AND status = 'solved' GROUP BY task",
            (lesson.id,),
        )
        return dict(rows.fetchall())

    def is_done(self, lesson: Lesson) -> bool:
        return len(self.best(lesson)) == len(lesson.tasks)

    def next_lesson(self, lessons: list[Lesson]) -> Lesson | None:
        return next((lesson for lesson in lessons if not self.is_done(lesson)), None)

    def streak(self) -> int:
        days = {date.fromisoformat(d) for (d,) in self.db.execute("SELECT DISTINCT substr(ts, 1, 10) FROM attempts")}
        day = date.today() if date.today() in days else date.today() - timedelta(days=1)
        n = 0
        while day in days:
            n += 1
            day -= timedelta(days=1)
        return n

    def hardtime_block_date(self) -> date:
        started = date.fromisoformat(STARTED_FILE.read_text().strip())
        return started + timedelta(days=HARDTIME_HINT_DAYS + 1)
