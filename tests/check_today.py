"""Today's routine and what it rests on, without Neovim or the interface: SRS
scheduling and task grades, the daily time budget, card introductions, Vim
cards first, and when hardtime starts blocking.

    uv run python tests/check_today.py
"""

import os
import sys
import tempfile
from datetime import date, timedelta

data = tempfile.mkdtemp()
os.environ["VIMNISCIENT_DATA"] = data
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from vimniscient import progress as progress_module  # noqa: E402 (after VIMNISCIENT_DATA)
from vimniscient import srs, today  # noqa: E402
from vimniscient.cards import load_decks  # noqa: E402
from vimniscient.lessons import load_lessons  # noqa: E402
from vimniscient.progress import Progress  # noqa: E402

problems = []


def check(what: str, got, want) -> None:
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {what}: {got!r}" + ("" if ok else f", want {want!r}"))
    if not ok:
        problems.append(what)


# SRS: the SM-2 variant
day = date(2026, 10, 1)
item = srs.Item("x", "card")
check("first good: tomorrow", srs.review(item, srs.GOOD, day).due, day + timedelta(days=1))
check("second good: in 3 days", srs.review(item, srs.GOOD, day).interval, 3)
check("third good: interval × ease", srs.review(item, srs.GOOD, day).interval, 3 * 2.5)
again = srs.review(item, srs.AGAIN, day)
check("again: back to a day, one lapse, ease down", (again.interval, again.lapses, round(again.ease, 2)), (1, 1, 2.3))
low = srs.Item("y", "card", ease=1.35)
check("ease never below 1.3", srs.review(low, srs.AGAIN, day).ease, 1.3)
check("first easy: in 4 days", srs.review(srs.Item("z", "card"), srs.EASY, day).interval, 4)
check("task grades", [srs.task_grade(*args) for args in [
    ("unseen", 0, 3, 0), ("quit", 2, 3, 0), ("skipped", 0, 3, 0), ("solved", 5, 3, 1),
    ("solved", 3, 3, 0), ("solved", 5, 3, 0), ("solved", 9, 3, 0)]],
    [None, None, srs.AGAIN, srs.HARD, srs.EASY, srs.GOOD, srs.HARD])

# The daily budget
lessons, decks = load_lessons(), load_decks(live=False)
progress = Progress()
unlocked = progress.unlocked(decks, lessons)
yesterday = date.today() - timedelta(days=1)
for card in unlocked[:80]:  # eighty cards due
    progress._save(srs.Item(card.id, "card", interval=1, due=yesterday, reps=1, created=yesterday))
progress.db.commit()

work = today.todays_work(progress, lessons, decks, [], budget_minutes=15)
check("15 minutes: the lesson comes", work.lesson is not None, True)
check("15 minutes: some due cards, not all", 0 < len(work.cards) - work.new_cards < 80, True)
check("15 minutes: no new cards while due ones wait", work.new_cards, 0)
check("it fits the budget", sum(work.seconds.values()) <= work.budget + 1, True)
big = today.todays_work(progress, lessons, decks, [], budget_minutes=120)
check("120 minutes: every due card", len(big.cards) - big.new_cards, 80)
check("120 minutes: new cards too", big.new_cards > 0, True)
tiny = today.todays_work(progress, lessons, decks, [], budget_minutes=1)
check("1 minute: still a few due cards", len(tiny.cards), today.MIN_DUE_CARDS)
for card in unlocked[:40]:  # forty answers today: about eight minutes gone
    progress.log_card(card, True, "x")
after = today.todays_work(progress, lessons, decks, [], budget_minutes=15)
check("practice today comes off the budget", round(work.budget - after.budget), 40 * today.CARD_SECONDS)
steps = {s.id: s for s in today.plan(progress, lessons, decks, [], work)}
check("Today says what waits", steps["cards"].detail, f"{len(work.cards)} of 80 due · 0 new")

# Card introductions: practice for the streak, not an answer
fresh = Progress()
fresh.db.execute("DELETE FROM card_log")
card = unlocked[0]
fresh.log_card(card, True, card.answers[0], intro=True)
check("an introduction counts for the streak", fresh.streak(), 1)
check("but isn't answering it from memory", fresh.ever_right(card.id), False)
check("nor card accuracy", fresh.card_accuracy(), [])

# New cards: Vim first in the first weeks, once their lessons are done
p = Progress()
for lesson in lessons[:2]:
    p.db.execute("INSERT INTO placed (lesson, ts) VALUES (?, ?)", (lesson.id, "2026-10-01"))
p.db.commit()
p.db.execute("DELETE FROM items WHERE created = ?", (date.today().isoformat(),))
p.db.commit()
check("week 1: new cards are Vim ones", {c.deck for c in p.new_cards(decks, lessons)}, {"vim"})

# hardtime: after week 2 and four weeks, not before
p = Progress()
progress_module.STARTED_FILE.write_text((date.today() - timedelta(days=40)).isoformat() + "\n")
check("40 days in, week 2 not done: hints", p.sync_hardtime(lessons), False)
for lesson in lessons:
    if (lesson.week, lesson.day) <= (2, 7):
        p.db.execute("INSERT OR REPLACE INTO placed (lesson, ts) VALUES (?, ?)", (lesson.id, "2026-10-01"))
p.db.commit()
check("week 2 done: blocks", p.sync_hardtime(lessons), True)
check("the Neovim config reads it", progress_module.HARDTIME_FILE.read_text().strip(), "block")
progress_module.STARTED_FILE.write_text(date.today().isoformat() + "\n")
check("week 2 done on day one: still hints", p.sync_hardtime(lessons), False)

# Endless: practice for the streak, never a grade
from vimniscient.session import TaskResult  # noqa: E402

p = Progress()
task = lessons[3].tasks[0]
before = p.db.execute("SELECT * FROM items ORDER BY id").fetchall(), p.is_done(lessons[3]), p.best(lessons[3])
p.record_endless([TaskResult(task.as_phase("climb"), "solved", task.solution, task.ref, 0, seconds=2.0, first=1.0)],
                 {"start": 1, "level": 2, "climbed": 1, "missed": 0, "fixed": 0})
after = p.db.execute("SELECT * FROM items ORDER BY id").fetchall(), p.is_done(lessons[3]), p.best(lessons[3])
check("Endless grades nothing", after == before, True)
check("but counts for the streak", p.streak() >= 1, True)

print(f"{len(problems)} problems")
sys.exit(1 if problems else 0)
