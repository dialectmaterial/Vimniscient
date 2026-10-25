"""`vimniscient` opens the menu; `vimniscient list` / `vimniscient run <id>` skip it."""

import argparse

from vimniscient.lessons import load_lessons


def main() -> None:
    parser = argparse.ArgumentParser(prog="vimniscient", description="Absolute vim: a daily trainer.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list", help="list the lessons")
    endless_cmd = sub.add_parser("endless", help="endless mode without the menu")
    endless_cmd.add_argument("--seed", help="the same tasks every time (for testing)")
    run = sub.add_parser("run", help="run one lesson without the menu")
    run.add_argument("lesson", help="lesson id, e.g. w1d1-words (see `list`)")
    remind = sub.add_parser("remind", help="notify about today's practice if any is left (for timers and hooks)")
    remind.add_argument("--login", action="store_true", help="you just started using the computer")
    remind.add_argument("--check", action="store_true", help="a follow-up reminder firing")
    setup = sub.add_parser("reminders", help="daily practice reminders through Omarchy")
    setup.add_argument("action", choices=["install", "uninstall", "status"], nargs="?", default="status")
    args = parser.parse_args()

    if args.command is None:
        from vimniscient.app import VimniscientApp

        VimniscientApp().run(mouse=False)  # keyboard only: nothing in it reacts to clicks
        return

    if args.command == "remind":
        from vimniscient import reminders

        print(reminders.remind("check" if args.check else "login"))
        return
    if args.command == "reminders":
        from vimniscient import reminders

        if args.action == "install":
            for path in reminders.install():
                print(f"wrote {path}")
            print(f"Reminders on: at {reminders.MORNING} or when you start using the computer, then every "
                  f"{reminders.EVERY // 60} hours until {reminders.DAY_END:%H:%M} while practice is left.")
        elif args.action == "uninstall":
            reminders.uninstall()
            print("Reminders off.")
        print(reminders.status())
        return

    lessons = load_lessons()
    if args.command == "list":
        for lesson in lessons:
            print(f"{lesson.id:28} {lesson.label}: {lesson.title} ({len(lesson.tasks)} tasks)")
        return

    from vimniscient.progress import Progress
    from vimniscient.session import run_endless, run_lesson

    if args.command == "endless":
        from vimniscient import endless
        from vimniscient.cards import has_lazyvim

        progress = Progress()
        start = progress.endless_start(endless.RESTART_BELOW)
        rungs = endless.ladder([lesson for lesson in lessons if not lesson.lazyvim or has_lazyvim()], start, seed=args.seed)
        results = run_endless({t.item_id: t for t, _ in rungs}, [(t.item_id, v) for t, v in rungs],
                              start, endless.RAMP, endless.GAP)
        run = endless.summary(results, start)
        progress.record_endless(results, run)
        for r in results:
            print(f"{r.task.phase:6} {r.level:4} {r.status:8} {r.count:>3}/{r.budget or '-'} keys  {r.task.goal}")
        print(f"Level {run['start']} -> {run['level']}: {run['missed']} missed, {run['fixed']} recalled afterwards")
        return

    lesson = next((lesson for lesson in lessons if lesson.id == args.lesson), None)
    if lesson is None:
        parser.error(f"no lesson {args.lesson!r}; try `vimniscient list`")
    from dataclasses import replace

    from vimniscient.lessons import two_rounds

    results = run_lesson(replace(lesson, tasks=two_rounds(lesson)), retry=True)
    Progress().record(results)
    for i, r in enumerate(results, 1):
        print(f"{i:2}. {r.task.phase:6} {r.status:8} {r.count if r.status == 'solved' else '-':>3} keys (ref {r.task.ref})  {r.task.goal}")
