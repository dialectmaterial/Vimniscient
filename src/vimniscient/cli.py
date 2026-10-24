"""`vimniscient` opens the menu; `vimniscient list` / `vimniscient run <id>` skip it."""

import argparse

from vimniscient.lessons import load_lessons


def main() -> None:
    parser = argparse.ArgumentParser(prog="vimniscient", description="Absolute vim: a daily trainer.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list", help="list the lessons")
    run = sub.add_parser("run", help="run one lesson without the menu")
    run.add_argument("lesson", help="lesson id, e.g. w1d1-words (see `list`)")
    args = parser.parse_args()

    if args.command is None:
        from vimniscient.app import VimniscientApp

        VimniscientApp().run()
        return

    lessons = load_lessons()
    if args.command == "list":
        for lesson in lessons:
            print(f"{lesson.id:28} {lesson.label}: {lesson.title} ({len(lesson.tasks)} tasks)")
        return

    from vimniscient.progress import Progress
    from vimniscient.session import run_lesson

    lesson = next((lesson for lesson in lessons if lesson.id == args.lesson), None)
    if lesson is None:
        parser.error(f"no lesson {args.lesson!r}; try `vimniscient list`")
    results = run_lesson(lesson)
    Progress().record(lesson, results)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r.status:8} {r.count if r.status == 'solved' else '-':>3} keys (ref {r.task.ref})  {r.task.goal}")
