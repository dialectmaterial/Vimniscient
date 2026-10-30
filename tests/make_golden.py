"""What this app does, written down for the Rust port to match (tests/golden/):
the parsed lessons, cards, answer checks, hooks, SRS steps, strategy feedback,
placement outcomes, today's plan from a fixed database, and the schema.

    uv run python tests/make_golden.py          # write them
    uv run python tests/make_golden.py --check  # fail if they've gone stale

Generated texts aren't here: Rust's random numbers differ, and any text will
do as long as it solves (check_generate.py, ported, covers that).
"""

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ["VIMNISCIENT_DATA"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()  # no hardtime log: it would change from day to day

from check_answers import CASES  # noqa: E402

from vimniscient import diagnose, placement, srs, today  # noqa: E402
from vimniscient.answer import is_correct, norm_keys  # noqa: E402
from vimniscient.card_session import CardSession  # noqa: E402
from vimniscient.cards import load_decks  # noqa: E402
from vimniscient.keys import count_keys  # noqa: E402
from vimniscient.lessons import load_lessons  # noqa: E402
from vimniscient.mnemonics import hooks  # noqa: E402
from vimniscient.progress import Progress  # noqa: E402
from vimniscient.session import TaskResult  # noqa: E402

GOLDEN = Path(__file__).with_name("golden")
lessons = load_lessons()
decks = load_decks(live=False)
day = date(2026, 10, 1)


def version(t) -> dict:
    return {"goal": t.goal, "start": t.start, "cursor": list(t.cursor), "target": t.target, "solution": t.solution,
            "hint": t.hint, "ft": t.ft, "ref": t.ref}


def lessons_data() -> list:
    return [{"id": lesson.id, "week": lesson.week, "day": lesson.day, "title": lesson.title, "skill": lesson.skill,
             "review": lesson.review, "lazyvim": lesson.lazyvim, "keys": lesson.keys, "intro": lesson.intro,
             "tasks": [{"generator": t.generator, "versions": [version(v) for v in (t, *t.variants)]} for t in lesson.tasks]}
            for lesson in lessons]


def cards_data() -> list:
    return [{"id": c.id, "deck": c.deck, "prompt": c.prompt, "answers": c.answers, "style": c.style, "case_sensitive": c.case_sensitive,
             "week": c.week, "day": c.day, "note": c.note, "shown": c.shown} for deck in decks.values() for c in deck.cards]


def answers_data() -> list:
    return [{"typed": typed, "expected": expected, "style": style, "case_sensitive": case, "correct": is_correct(typed, expected, style, case)}
            for typed, expected, style, case, _ in CASES]


def keys_data() -> dict:
    solutions = sorted({v.solution for lesson in lessons for t in lesson.tasks for v in (t, *t.variants)})
    return {keys: {"count": count_keys(keys), "hooks": hooks(keys), "norm": norm_keys(keys)} for keys in solutions}


def srs_data() -> list:
    steps = []
    for grades in ([srs.GOOD] * 4, [srs.EASY, srs.GOOD], [srs.GOOD, srs.AGAIN, srs.GOOD], [srs.HARD, srs.HARD], [srs.AGAIN] * 8):
        item, trail = srs.Item("x", "card"), []
        for grade in grades:
            srs.review(item, grade, day)
            trail.append({"grade": grade, "interval": item.interval, "ease": round(item.ease, 6), "reps": item.reps, "lapses": item.lapses, "due": item.due.isoformat()})
        steps.append(trail)
    grades = [{"args": list(args), "grade": srs.task_grade(*args)} for args in
              [("unseen", 0, 3, 0), ("quit", 2, 3, 0), ("skipped", 0, 3, 0), ("solved", 5, 3, 1), ("solved", 3, 3, 0), ("solved", 5, 3, 0), ("solved", 9, 3, 0)]]
    return [steps, grades]


def diagnose_data() -> list:
    typed = ["jjjjdd", "llllldw", "xxxx", "A;<Esc>jA;<Esc>jA;<Esc>j", "ciwhellllllo<Esc>", "llrxllrxll", "/jjjjjj<CR>dd", "qaxqjjj", "vjjjcjjjjjj<Esc>"]
    return [{"keys": keys, "normal": diagnose.normal_keys(keys), "says": diagnose.diagnose(keys, count_keys(keys), 2)} for keys in typed]


def placement_data() -> dict:
    profiles = {"expert": lambda lesson: True, "beginner": lambda lesson: False, "macros": lambda lesson: lesson.skill == "macros",
                "ex-week-3": lambda lesson: lesson.skill == "ex" and lesson.week == 3}
    found = {}
    by_id = {lesson.id: lesson for lesson in lessons}
    for name, knows in profiles.items():
        search, rounds = placement.Search(lessons, lazyvim=True), []
        while not search.finished:
            tasks = search.round()
            rounds.append([t.item_id for t in tasks])
            search.update([TaskResult(t, "solved" if knows(by_id[t.lesson_id]) else "skipped", t.solution, t.ref, 0) for t in tasks])
        found[name] = {"rounds": rounds, "known": [lesson.id for lesson in search.known()]}
    return found


def today_data() -> dict:
    """The fixture is relative to today, so the port builds the same one: every
    `due` a number of days from now. Forty unlocked cards are due."""
    progress = Progress()
    for lesson in lessons[:3]:
        progress.db.execute("INSERT INTO placed (lesson, ts) VALUES (?, ?)", (lesson.id, "2026-10-01"))
    unlocked = progress.unlocked(decks, lessons)
    fixture = [{"id": c.id, "interval": 1, "due_days": -1 - (i % 3), "reps": 1} for i, c in enumerate(unlocked[:40])]
    for row in fixture:
        progress._save(srs.Item(row["id"], "card", interval=1, due=date.today() + timedelta(days=row["due_days"]), reps=1, created=date.today() - timedelta(days=5)))
    progress.db.commit()
    plans = {}
    for minutes in (1, 15, 120):
        work = today.todays_work(progress, lessons, decks, [], budget_minutes=minutes)
        plans[minutes] = {"cards": [c.id for c in work.cards], "new_cards": work.new_cards, "lesson": work.lesson.id if work.lesson else None,
                          "review": [t.item_id for t in work.review], "seconds": work.seconds, "budget": work.budget,
                          "steps": [{"id": s.id, "detail": s.detail, "todo": s.todo, "minutes": s.minutes} for s in today.plan(progress, lessons, decks, [], work)]}
    session = CardSession(progress, unlocked[40:42] + unlocked[:1])
    trail = []
    while session.begin():
        card = session.card
        typed = "wrong" if len(trail) == 2 else card.answers[0]
        trail.append({"card": card.id, "intro": session.intro, "typed": typed, "taken": session.submit(typed)})
        session.settle()
    return {"placed": [lesson.id for lesson in lessons[:3]], "items": fixture, "plans": plans, "card_run": trail,
            "card_score": [session.correct, session.answered]}


def schema() -> str:
    rows = Progress().db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name").fetchall()
    return ";\n".join(row[0] for row in rows) + ";\n"


FILES = {"lessons.json": lessons_data, "cards.json": cards_data, "answers.json": answers_data, "keys.json": keys_data, "srs.json": srs_data,
         "diagnose.json": diagnose_data, "placement.json": placement_data, "today.json": today_data}

made = {name: json.dumps(make(), ensure_ascii=False, indent=1, sort_keys=True) + "\n" for name, make in FILES.items()}
made["schema.sql"] = schema()
if "--check" in sys.argv:
    stale = [name for name, text in made.items() if not (GOLDEN / name).exists() or (GOLDEN / name).read_text(encoding="utf-8") != text]
    print(f"{len(made)} files, stale: {stale or 'none'}")
    sys.exit(1 if stale else 0)
GOLDEN.mkdir(exist_ok=True)
for name, text in made.items():
    (GOLDEN / name).write_text(text, encoding="utf-8")
print(f"wrote {len(made)} files to {GOLDEN}")
