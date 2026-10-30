"""The Textual interface.

Laid out like lazygit: everything on one screen in titled panes, Tab moves
focus, one key bar at the bottom, nothing animates. Cards and drills get a
centred focus screen, as in terminal typing trainers. Colours come from the
Omarchy theme in use (Catppuccin Mocha's own palette by default).
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from textual.app import App
from textual.color import Color
from textual.content import Content

from vimniscient import drills, endless, quick, reminders, today, transfer, vimgolf
from vimniscient.cards import has_lazyvim, load_decks
from vimniscient.lessons import Lesson, load_lessons, two_rounds
from vimniscient.progress import Progress
from vimniscient.session import COLORS, TaskResult, mouse_wheel, run_endless, run_lesson
from vimniscient.ui.builtin_lessons import endless_lesson, placement_lesson, quick_lesson, review_lesson, transfer_lesson, vimgolf_lesson
from vimniscient.ui.cards import CardScreen
from vimniscient.ui.common import CATPPUCCIN, DEFAULT_THEME, omarchy_theme, plural
from vimniscient.ui.drills import DrillScreen
from vimniscient.ui.lesson import LessonScreen, ResultsScreen
from vimniscient.ui.main import MainScreen
from vimniscient.ui.quick import QuickScreen
from vimniscient.ui.stats import StatsScreen


class VimniscientApp(App):
    TITLE = "Vimniscient"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: $background; }

    /* panes: rounded, titled in the border, mauve when focused (lazygit) */
    .pane { border: round $panel; border-title-color: $text-muted; border-subtitle-color: $text-muted;
            background: $background; padding: 0 1; }
    .pane:focus, .pane:focus-within { border: round $primary; border-title-color: $primary; }
    OptionList.pane { padding: 0 1; text-wrap: nowrap; text-overflow: ellipsis; }
    OptionList.pane:focus { border: round $primary; }
    OptionList > .option-list--option-highlighted { background: $surface; color: $foreground; text-style: none; }
    OptionList:focus > .option-list--option-highlighted { background: $primary 25%; color: $foreground; text-style: bold; }
    .keybar { height: 1; padding: 0 1; color: $text-muted; background: $background; }

    #main { height: 1fr; }
    #left { width: 46; max-width: 45%; }
    #plan { height: 10; }
    #lesson-list { height: 1fr; }
    #right { width: 1fr; }
    #detail-pane { height: 1fr; }
    #progress-pane { height: auto; max-height: 10; }
    #progress-text { height: auto; }
    #spark { height: 2; margin-top: 1; }
    Sparkline > .sparkline--max-color { color: $primary; }
    Sparkline > .sparkline--min-color { color: $secondary; }
    Markdown { padding: 0 1; margin: 0; background: $background; }
    MarkdownBlock > .code_inline { background: $surface; color: $primary; }

    /* focus screens: one centred column, like terminal typing trainers */
    CardScreen, DrillScreen, LessonScreen { align: center middle; }
    .column, .column:focus-within { width: 76; max-width: 100%; height: auto; max-height: 90%; padding: 1 2;
                                    border: round $primary; border-title-color: $primary; }
    .prompt { color: $primary; text-style: bold; height: auto; padding: 1 0; }
    #card-bar, #drill-bar { height: 1; }
    #card-input { border: round $panel; background: $background; padding: 0 1; }
    #card-input:focus { border: round $primary; background: $background; }
    #card-feedback { padding: 1 0 0 0; height: auto; min-height: 3; }
    #drill-steps { height: auto; }
    #drill-status { height: auto; padding-top: 1; }
    CardScreen > .keybar, DrillScreen > .keybar, LessonScreen > .keybar, ResultsScreen > .keybar { dock: bottom; }

    ResultsScreen { align: center middle; }
    #results-panel { width: 96; }
    #results-bar { height: 1; }
    #note { padding: 0 0 1 0; color: $success; height: auto; }
    #results-list { height: auto; padding-right: 1; }
    #results-why, #results-advice { height: auto; padding: 1 0 0 0; }

    #stats-view { height: 1fr; padding: 0 2; }
    .section-label { color: $text-muted; text-style: bold; height: 1; margin-top: 1; }
    DataTable { background: $background; height: auto; max-height: 14; margin-top: 1; }
    DataTable > .datatable--header { background: $surface; color: $text-muted; text-style: bold; }
    #overview { height: auto; margin-top: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.animation_level = "none"  # tabs, scrolling and the rest switch instantly
        # Week 5 teaches LazyVim's own text objects; without LazyVim it's left out.
        self.lessons = [lesson for lesson in load_lessons() if not lesson.lazyvim or has_lazyvim()]
        self.progress = Progress()
        self.decks = load_decks()
        self.drills = drills.load_drills()

    def lesson(self, lesson_id: str) -> Lesson:
        return next(lesson for lesson in self.lessons if lesson.id == lesson_id)

    def on_mount(self) -> None:
        for theme in CATPPUCCIN:
            self.register_theme(theme)
        theme = omarchy_theme()
        self.theme = theme if theme in self.available_themes else DEFAULT_THEME
        mouse_wheel(False)
        COLORS.update(self.lesson_colors())
        self.push_screen(MainScreen())

    def lesson_colors(self) -> dict[str, str]:
        """The theme's colours as hex, for lessons in Neovim to draw with."""
        theme = self.current_theme
        background = Color.parse(theme.background or "#000000")
        foreground = Color.parse(theme.foreground or "#ffffff")
        named = {"primary": theme.primary, "accent": theme.accent or theme.primary,
                 "success": theme.success or theme.primary, "error": theme.error or theme.primary,
                 "panel": theme.panel or theme.surface or theme.primary}
        return {"background": background.hex, "foreground": foreground.hex,
                "muted": (background + background.get_contrast_text(0.6)).hex,  # $text-muted is "auto 60%"
                **{name: Color.parse(value).hex for name, value in named.items()}}

    # running things

    def start_lesson(
        self,
        lesson: Lesson,
        on_results: Callable[[list[TaskResult]], str | Content] | None = None,
        done: Callable[[], None] = lambda: None,
    ) -> None:
        """Run a lesson in Neovim, then show the results; `done` runs when the user moves on.
        Real lessons (not review, placement or VimGolf) run in two rounds: Learn, then Recall.
        In lessons and reviews, a skipped task is shown, typed, and asked again at the end."""
        session = replace(lesson, tasks=two_rounds(lesson)) if lesson.week else lesson
        with self.suspend():
            results = run_lesson(session, retry=bool(lesson.week) or lesson.id == "review")
        mouse_wheel(False)  # coming back from Neovim
        if on_results:
            note = on_results(results)
        else:
            self.progress.record(results)
            note = ""

        def after(again: bool) -> None:
            if again:
                self.start_lesson(lesson, on_results, done)
            else:
                done()

        self.push_screen(ResultsScreen(session, results, note), after)

    def run_steps(self, steps: list[Callable[[Callable[[], None]], None]]) -> None:
        """Run screens one after another; each step calls `done` when finished."""
        if steps:
            steps[0](lambda: self.run_steps(steps[1:]))

    def work(self) -> today.Work:
        """Today's cards, drills and review, as much as fits the daily budget."""
        return today.todays_work(self.progress, self.lessons, self.decks, self.drills)

    def plan(self) -> list[today.Step]:
        return today.plan(self.progress, self.lessons, self.decks, self.drills, self.work())

    def todays_drills(self) -> list[drills.Drill]:
        return today.todays_drills(self.progress, self.drills)

    def step(self, step_id: str, direct: bool = False) -> Callable[[Callable[[], None]], None] | None:
        """One step of today's routine, or None when there's nothing to do for it.

        `direct` starts lessons without their intro screen (the main screen shows it already)."""
        progress = self.progress
        if step_id == "cards":
            cards = self.work().cards
            if cards:
                return lambda done: self.push_screen(CardScreen(cards, self.decks, "Today's cards"), lambda _: done())
        elif step_id == "drills":
            todays = self.work().drills
            if todays:
                return lambda done: self.push_screen(DrillScreen(todays, "Omarchy drills"), lambda _: done())
        elif step_id == "review":
            review = self.work().review
            if review and direct:
                return lambda done: self.start_lesson(review_lesson(review), done=done)
            if review:
                return lambda done: self.push_screen(LessonScreen(review_lesson(review)), lambda _: done())
        elif step_id == "lesson":
            nxt = progress.next_lesson(self.lessons)
            if nxt and direct:
                return lambda done: self.start_lesson(nxt, done=done)
            if nxt:
                return lambda done: self.push_screen(LessonScreen(nxt), lambda _: done())
        elif step_id == "vimgolf":
            if not progress.vimgolf_done_today():
                return self.start_vimgolf
        elif step_id == "quick":
            return self.start_quick
        elif step_id == "transfer":
            picks = transfer.pick(self.lessons, progress)
            if picks:
                return lambda done: self.start_transfer(picks, done)
        elif step_id == "endless":
            start = progress.endless_start(endless.RESTART_BELOW)
            if direct:
                return lambda done: self.start_endless(start, done)
            return lambda done: self.push_screen(
                LessonScreen(endless_lesson(start, progress.endless_best()), start=lambda d: self.start_endless(start, d)),
                lambda _: done(),
            )
        return None

    def run_step(self, step_id: str, done: Callable[[], None], direct: bool = False) -> None:
        step = self.step(step_id, direct)
        if step:
            step(done)
        else:
            self.notify("Nothing left for this one today.")

    def action_today(self) -> None:
        """Cards, drills, review (plus habit drills), then the next lesson:
        whichever are still left today. One lesson a day; the Lessons list has the rest."""
        left = {step.id for step in today.left(self.plan())}
        steps = [s for s in (self.step(i) for i in today.ROUTINE if i in left) if s]
        if not steps:
            self.notify("That's everything for today. Endless (e) or any lesson if you want more.")
            return

        def finished(done: Callable[[], None]) -> None:
            if not today.left(self.plan()):
                self.notify("That's today's practice done. See you tomorrow.", title="Vimniscient")
            done()

        self.run_steps([*steps, finished])

    def on_unmount(self) -> None:
        """Done for the day? Then the reminders still waiting can go."""
        try:
            reminders.sync(self.plan())
        except Exception:  # never let a reminder problem lose the session
            pass

    def action_drills(self) -> None:
        todays = self.todays_drills() or self.drills
        self.push_screen(DrillScreen(todays, "Omarchy drills"))

    def action_cards(self) -> None:
        cards = self.progress.due_cards(self.decks, self.lessons) + self.progress.new_cards(self.decks, self.lessons)
        if cards:
            self.push_screen(CardScreen(cards, self.decks, "Cards"))
        else:
            self.notify("No cards due. Come back tomorrow.")

    def action_placement(self) -> None:
        def on_results(results: list[TaskResult]) -> str:
            self.progress.record(results)
            placed = self.progress.place(self.lessons, results)
            if not placed:
                return "No lessons skipped. Start from Week 1 · Day 1."
            return "Known already: " + ", ".join(f"{p.label} ({p.title})" for p in placed)

        self.push_screen(LessonScreen(placement_lesson(self.lessons), on_results))

    def action_endless(self) -> None:
        self.run_step("endless", lambda: None)

    def action_quick(self) -> None:
        self.run_step("quick", lambda: None)

    def start_quick(self, done: Callable[[], None]) -> None:
        finished = {lesson.id for lesson in self.lessons if self.progress.is_done(lesson)}
        pools = quick.pools(self.lessons, finished)

        def chosen(choice: tuple[str, int] | None) -> None:
            if choice is None:
                done()
                return
            skill, minutes = choice
            count, seed = quick.how_many(minutes, self.progress.typical_task_seconds()), datetime.now().isoformat()
            tasks = (quick.navigation(count, self.lessons[0].tasks[0], seed) if skill == quick.NAVIGATION
                     else quick.tasks(pools[skill], count, seed))

            def on_results(results: list[TaskResult]) -> str:
                self.progress.record_ungraded(results, "quick")
                return ""

            self.start_lesson(quick_lesson(quick.title(skill), tasks), on_results, done)

        self.push_screen(QuickScreen({skill: len(tasks) for skill, tasks in pools.items()}), chosen)

    def action_transfer(self) -> None:
        self.run_step("transfer", lambda: None)

    def start_transfer(self, picks: list[transfer.Challenge], done: Callable[[], None]) -> None:
        def on_results(results: list[TaskResult]) -> Content:
            self.progress.record_ungraded(results, "transfer")
            by_goal = {c.task.goal: c for c in picks}
            lines = [f"{r.task.goal}  {'  or  '.join(ways)}" for r in results
                     if (ways := transfer.another_way(by_goal[r.task.goal], r.keys, r.status == "solved"))]
            return Content("Another way\n" + "\n".join(lines)) if lines else Content("")

        self.start_lesson(transfer_lesson([c.task for c in picks]), on_results, done)

    def start_endless(self, start: int, done: Callable[[], None]) -> None:
        """Climb from `start` until the user quits, then show how it went."""
        best = self.progress.endless_best()
        rungs = endless.ladder(self.lessons, start)
        pool = {t.item_id: t for t, _ in rungs}
        with self.suspend():
            results = run_endless(pool, [(t.item_id, v) for t, v in rungs], start, endless.RAMP, endless.GAP)
        mouse_wheel(False)
        run = endless.summary(results, start)
        self.progress.record_endless(results, run)
        note = (f"Level {run['start']} → {run['level']} · {plural(run['missed'], 'miss', 'misses')}, "
                f"{run['fixed']} recalled afterwards")
        if run["level"] > best and run["climbed"]:
            note += " · a new best!"

        def after(again: bool) -> None:
            if again:
                self.start_endless(self.progress.endless_start(endless.RESTART_BELOW), done)
            else:
                done()

        self.push_screen(ResultsScreen(endless_lesson(start, best), results, note, f"level {run['level']}"), after)

    def action_vimgolf(self) -> None:
        self.start_vimgolf(lambda: None)

    def start_vimgolf(self, done: Callable[[], None]) -> None:
        self.notify("Fetching today's VimGolf challenge…")
        self.run_worker(lambda: self._fetch_vimgolf(done), thread=True, exclusive=True, group="vimgolf")

    def _fetch_vimgolf(self, done: Callable[[], None]) -> None:
        # A thread of its own: sqlite connections can't cross threads, so it opens one.
        try:
            challenge = Progress().vimgolf_today(vimgolf.index(), vimgolf.challenge)
        except Exception as error:  # offline, or the site changed: never take the app down
            self.call_from_thread(self.notify, f"Couldn't get a VimGolf challenge ({error}). Skipping it.", severity="warning")
            self.call_from_thread(done)
            return
        if challenge is None:
            self.call_from_thread(self.notify, "No VimGolf challenges left to try.")
            self.call_from_thread(done)
            return

        def on_results(results: list[TaskResult]) -> str:
            score = self.progress.record_vimgolf(challenge.id, results[0], vimgolf.SAVE_KEYS)
            if score is None:
                return f"Not solved. It stays today's challenge. ({challenge.url})"
            best = f", best on vimgolf.com {challenge.best}" if challenge.best else ""
            return f"Your VimGolf score: {score} (keys + ZZ){best}. Solutions: {challenge.url}"

        self.call_from_thread(
            self.push_screen, LessonScreen(vimgolf_lesson(challenge), on_results), lambda _: done()
        )

    def action_stats(self) -> None:
        self.push_screen(StatsScreen())
