"""The main screen, lazygit-style: Today and Lessons on the left, details and progress on the right."""

from datetime import date
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Markdown, OptionList, Sparkline, Static
from textual.widgets.option_list import Option

from vimniscient import endless, habits, settings, today
from vimniscient.cards import has_plugin
from vimniscient.ui.builtin_lessons import ENDLESS_INTRO
from vimniscient.ui.common import keybar, lesson_markdown, streak_text

if TYPE_CHECKING:
    from vimniscient.app import VimniscientApp


class MainScreen(Screen):
    """Everything at once, lazygit-style: Today and Lessons on the left, the
    highlighted entry on the right, progress below it. Tab moves between panes."""

    DETAIL_DELAY = 0.08  # rendering Markdown costs far more than moving the highlight
    detail_timer: Timer | None = None

    BINDINGS = [
        Binding("t", "app.today", "Start today"),
        Binding("c", "app.cards", "Cards", show=False),
        Binding("d", "app.drills", "Drills", show=False),
        Binding("e", "app.endless", "Endless", show=False),
        Binding("g", "app.vimgolf", "VimGolf", show=False),
        Binding("p", "app.placement", "Placement", show=False),
        Binding("s", "app.stats", "Stats", show=False),
        Binding("1", "pane('plan')", "Today", show=False),
        Binding("2", "pane('lesson-list')", "Lessons", show=False),
        Binding("j", "move(1)", "Down", show=False),
        Binding("k", "move(-1)", "Up", show=False),
        Binding("l", "open", "Open", show=False),
        Binding("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield OptionList(id="plan", classes="pane")
                yield OptionList(id="lesson-list", classes="pane")
            with Vertical(id="right"):
                with VerticalScroll(id="detail-pane", classes="pane"):
                    yield Markdown(id="detail")
                with Vertical(id="progress-pane", classes="pane"):
                    yield Static(id="progress-text")
                    yield Sparkline([], id="spark")
        yield Static(
            keybar(("t", "today"), ("⏎", "open"), ("⇥", "pane"), ("e", "endless"), ("c", "cards"),
                   ("d", "drills"), ("g", "golf"), ("p", "place"), ("s", "stats"), ("q", "quit")),
            classes="keybar",
        )

    def on_mount(self) -> None:
        self.query_one("#plan").border_title = "1 Today"
        self.query_one("#lesson-list").border_title = "2 Lessons"
        self.query_one("#progress-pane").border_title = "Progress"
        self.refresh_all()
        self.query_one("#plan", OptionList).focus()

    def on_screen_resume(self) -> None:
        self.refresh_all()

    # data

    def refresh_all(self) -> None:
        self.refresh_plan()
        self.refresh_lessons()
        self.refresh_progress()
        self.show_detail()


    PLAN_DETAIL = {
        "cards": ("Cards", "Type the keys for each prompt: Vim, LazyVim, Omarchy, tmux, the shell, foot, "
                  "Zathura, and the habits hardtime caught. Due cards first, then up to 10 new ones."),
        "drills": ("Omarchy drills", "Do it for real on the *Vimniscient drill* window; Hyprland's events "
                   "confirm each step. `h` shows the keys, `s` skips."),
        "review": ("Review", "Vim tasks from earlier days that are due again, plus a few drills for the "
                   "habits hardtime keeps catching."),
        "vimgolf": ("VimGolf", "One challenge from vimgolf.com, the most played ones first, scored against "
                    "the leaderboard.\n\nNot part of `t`: an extra, whenever you feel like it (or `g`)."),
        "endless": ("Endless", ENDLESS_INTRO.format(ramp=endless.RAMP, below=endless.RESTART_BELOW)
                    + "\n\nNot part of `t`: play it whenever you have time left."),
    }

    def refresh_plan(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        options = []
        steps = app.plan()
        for step in steps:
            optional = "[$secondary]∞[/]" if step.id == "endless" else "[$secondary]·[/]"
            mark = optional if step.todo is None else "[$primary]›[/]" if step.todo else "[$success]✓[/]"
            options.append(Option(Content.from_markup(f"{mark} [b]$label[/] [dim]$detail[/]",
                                                      label=f"{step.label:<8}", detail=step.detail), id=step.id))
        self.fill("plan", options)
        left = sum(step.minutes for step in today.left(steps))
        budget = settings.minutes()
        self.query_one("#plan").border_subtitle = (
            "all done" if not left else f"about {left} of {budget} min left" if left <= budget else f"about {left} min left")

    def refresh_lessons(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        progress = app.progress
        options: list[Option] = []
        week = None
        for lesson in app.lessons:
            if lesson.week != week:
                week = lesson.week
                options.append(Option(f"[dim]Week {week}[/]", disabled=True))
            best = progress.best(lesson)
            count = ""
            if len(best) == len(lesson.tasks):
                mark = "[$success]✓[/]"
            elif progress.is_placed(lesson):
                mark = "[$success]○[/]"
            elif best:
                mark, count = "[$primary]◐[/]", f" [dim]{len(best)}/{len(lesson.tasks)}[/]"
            else:
                mark = "[dim]·[/]"
            options.append(Option(f" {mark} {lesson.day} {lesson.title}{count}", id=lesson.id))
        nxt = progress.next_lesson(app.lessons)
        self.fill("lesson-list", options, nxt.id if nxt else None)

    def refresh_progress(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        progress, lessons = app.progress, app.lessons
        done = sum(progress.is_done(lesson) for lesson in lessons)
        earliest = progress.hardtime_earliest()
        hardtime = ("blocking" if progress.sync_hardtime(lessons)
                    else f"blocks after week 2, from {max(earliest, date.today()):%b %d} at the earliest")
        days = list(reversed(progress.efficiency_by_day(14)))
        efficiency = [100 * ref / keys for _, _, keys, ref in days if keys]
        parts = [streak_text(progress.streak()), f"[b]{done}/{len(lessons)}[/] lessons"]
        if progress.endless_best():
            parts.append(f"endless best level {progress.endless_best()}")
        if has_plugin("hardtime.nvim"):
            parts.append(f"hardtime {hardtime}")
        lines = [Content.from_markup(" · ".join(parts))]
        top = next((h for h in habits.habits() if h.recent), None)
        if top:  # hardtime's messages have brackets in them ("Use [count]k")
            lines.append(Content.from_markup("[dim]top habit:[/] $message ($n×)", message=top.message, n=top.recent))
        if not progress.days_trained():
            lines.append(Content.from_markup("[dim]New here? Press[/] [b $primary]p[/] [dim]for the placement test: it skips what you know.[/]"))
        lines.append(Content.from_markup("[dim]keystroke efficiency, last 14 days[/]" if efficiency else "[dim]efficiency shows up after your first lesson[/]"))
        self.query_one("#progress-text", Static).update(Content("\n").join(lines))
        spark = self.query_one("#spark", Sparkline)
        spark.data = efficiency
        spark.display = bool(efficiency)

    def fill(self, list_id: str, options: list[Option], select: str | None = None) -> None:
        """Replace a list's options, keeping the highlight where it was."""
        option_list = self.query_one(f"#{list_id}", OptionList)
        highlighted = option_list.highlighted
        option_list.clear_options()
        option_list.add_options(options)
        if highlighted is not None and highlighted < len(options):
            option_list.highlighted = highlighted
        elif select:
            option_list.highlighted = option_list.get_option_index(select)
        else:
            option_list.highlighted = next((i for i, o in enumerate(options) if not o.disabled), None)

    def show_detail(self) -> None:
        """The right pane follows whichever list has focus."""
        app: VimniscientApp = self.app  # type: ignore[assignment]
        focused = self.focused if isinstance(self.focused, OptionList) else self.query_one("#plan", OptionList)
        if focused.highlighted is None:
            return
        key = focused.get_option_at_index(focused.highlighted).id
        lesson = None
        if focused.id == "lesson-list":
            lesson = app.lesson(key)
        elif key == "lesson":
            lesson = app.progress.next_lesson(app.lessons)
            if lesson is None:
                title, text = "Lessons", "Every lesson is done. Pick any in the Lessons list to practise again."
        else:
            title, text = self.PLAN_DETAIL[key]
        if lesson:
            title = f"{lesson.label} · {lesson.title}"
            text = lesson_markdown(lesson, app.progress.best(lesson))
        pane = self.query_one("#detail-pane")
        pane.border_title = title
        self.query_one("#detail", Markdown).update(text)

    def detail_soon(self) -> None:
        """Show the detail once the highlight stops moving, so holding j stays quick."""
        if self.detail_timer:
            self.detail_timer.stop()
        self.detail_timer = self.set_timer(self.DETAIL_DELAY, self.show_detail)

    # events

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list is self.focused:
            self.detail_soon()

    def on_descendant_focus(self) -> None:
        self.show_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        if event.option_list.id == "lesson-list":
            app.start_lesson(app.lesson(event.option.id), done=self.refresh_all)
        else:
            app.run_step(event.option.id, self.refresh_all, direct=True)

    def action_pane(self, pane_id: str) -> None:
        self.query_one(f"#{pane_id}", OptionList).focus()

    def action_move(self, step: int) -> None:
        if isinstance(self.focused, OptionList):
            self.focused.action_cursor_down() if step > 0 else self.focused.action_cursor_up()

    def action_open(self) -> None:
        if isinstance(self.focused, OptionList):
            self.focused.action_select()
