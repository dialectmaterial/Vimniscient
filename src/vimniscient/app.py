"""The Textual interface.

Laid out like lazygit: everything on one screen in titled panes, Tab moves
focus, one key bar at the bottom, nothing animates. Cards and drills get a
centred focus screen, as in terminal typing trainers. Colours come from the
Omarchy theme in use (Catppuccin Mocha's own palette by default).
"""

import asyncio
import os
import re
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Color
from textual.binding import Binding
from textual.content import Content
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import DataTable, Input, Markdown, OptionList, Sparkline, Static
from textual.widgets.option_list import Option

from vimniscient import drills, endless, habits, reminders, srs, today, vimgolf
from vimniscient.answer import is_correct
from vimniscient.cards import Card, Deck, has_lazyvim, has_plugin, load_decks
from vimniscient.lessons import Lesson, Task, load_lessons, two_rounds
from vimniscient.mnemonics import hooks
from vimniscient.progress import Progress
from vimniscient.session import COLORS, TaskResult, run_endless, run_lesson

LOGO = """\
█ █ █ █▀▄▀█ █▄ █ █ ▄▀▀ ▄▀▀ █ ██▀ █▄ █ ▀█▀
▀▄▀ █ █ ▀ █ █ ▀█ █ ▄██ ▀▄▄ █ █▄▄ █ ▀█  █ """

# decks whose answers are Vim keys, so mnemonics.hooks() can say what they stand for
HOOK_DECKS = {"vim", "lazyvim", "habits"}

# Result labels and the theme colour each is shown in.
STATUS = {
    "solved": ("solved", "success"),
    "failed": ("missed", "error"),
    "skipped": ("skipped", "warning"),
    "quit": ("quit", "error"),
    "unseen": ("not reached", "text-muted"),
}

# Catppuccin from its own palette (catppuccin.com/palette): mauve leads, lavender
# and blue accent, no peach. Textual's built-in Catppuccin themes use peach.
CATPPUCCIN = (
    Theme(name="vimniscient-mocha", dark=True,
          primary="#cba6f7", secondary="#89b4fa", accent="#b4befe",           # mauve, blue, lavender
          success="#a6e3a1", warning="#f9e2af", error="#f38ba8",             # green, yellow, red
          foreground="#cdd6f4", background="#1e1e2e", surface="#313244", panel="#45475a",
          variables={"block-cursor-foreground": "#1e1e2e", "footer-key-foreground": "#cba6f7",
                     "input-selection-background": "#cba6f7 35%"}),
    Theme(name="vimniscient-latte", dark=False,
          primary="#8839ef", secondary="#1e66f5", accent="#7287fd",
          success="#40a02b", warning="#df8e1d", error="#d20f39",
          foreground="#4c4f69", background="#eff1f5", surface="#ccd0da", panel="#bcc0cc",
          variables={"block-cursor-foreground": "#eff1f5", "footer-key-foreground": "#8839ef",
                     "input-selection-background": "#8839ef 35%"}),
)

# Omarchy theme names (~/.local/state/omarchy/current/theme.name) with a Textual twin.
OMARCHY_THEMES = {
    "catppuccin": "vimniscient-mocha",
    "catppuccin-latte": "vimniscient-latte",
    "gruvbox": "gruvbox",
    "nord": "nord",
    "tokyo-night": "tokyo-night",
    "rose-pine": "rose-pine",
    "flexoki-light": "flexoki",
}
DEFAULT_THEME = "vimniscient-mocha"

TASK_HELP = (
    "The goal shows in the top window, your text below. When they match, the next task loads by "
    "itself. Inside Neovim: `:Hint` (twice for the answer), `:Skip`, `:Reset`, `:q` to stop."
)
VIMGOLF_HELP = (
    "The goal shows in the top window, your text below; it's done when they match. Inside Neovim: "
    "`:Reset` to start over, `:q` to stop."
)
RETRY_HELP = "Skip a task you can't recall and you'll see the answer, type it once, and get it again at the end."
ROUNDS_HELP = (
    "Two rounds. **Learn**: each task with the keys to type shown. **Recall**: the same skills on "
    "new text, in another order, from memory. Only Recall counts towards your progress."
)


def plural(n: int, word: str, many: str = "") -> str:
    return f"{n} {word if n == 1 else many or word + 's'}"


def streak_text(days: int) -> str:
    return f"[b]{days}-day[/] streak" if days else "no streak yet"


def tint(app: App, text: str, colour: str) -> Text:
    """Text in one of the theme's colours, for tables (their cells don't read $variables)."""
    if colour == "text-muted":  # "auto 60%" in the theme, which only CSS understands
        return Text(text, style="dim")
    return Text(text, style=app.theme_variables.get(colour, ""))


def omarchy_theme() -> str:
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    try:
        name = (state / "omarchy" / "current" / "theme.name").read_text().strip().lower()
    except OSError:
        return DEFAULT_THEME
    return OMARCHY_THEMES.get(name, DEFAULT_THEME)


ENDLESS_INTRO = (
    "Tasks from every lesson, one after another, for as long as you like. Each one you solve "
    "climbs a level. New lessons join the mix as you climb, and the key budget shrinks: about "
    "twice the reference at first, exactly the reference by level {ramp}.\n\n"
    "Go over the budget, `:Skip`, or ask for the answer, and it's a miss. A miss shows the answer, "
    "then you type it in with the keys shown (**Learn**). A couple of tasks later it comes back on "
    "another text, from memory (**Recall**). `:q` stops; your level is kept, and the next run starts "
    "{below} levels below it."
)


def endless_lesson(start: int, best: int) -> Lesson:
    record = f" Your best is level **{best}**." if best else ""
    return Lesson(
        id="endless",
        week=0,
        day=0,
        title="Endless",
        intro=f"**Starting at level {start}.**{record}\n\n"
        + ENDLESS_INTRO.format(ramp=endless.RAMP, below=endless.RESTART_BELOW),
        keys=[],
        tasks=[],
    )


def review_lesson(tasks: list[Task]) -> Lesson:
    return Lesson(
        id="review",
        week=0,
        day=0,
        title="Review",
        intro="Tasks from earlier days that are due again. Spaced repetition brings each one back "
        "just before you'd forget it, sooner when it went badly and later when it went well.",
        keys=[],
        tasks=tasks,
    )


def vimgolf_lesson(challenge: vimgolf.Challenge) -> Lesson:
    best = challenge.best
    # The runner finishes by itself, so the reference is the best score minus saving (ZZ).
    ref = max(1, best - vimgolf.SAVE_KEYS) if best else None
    best_text = (
        f"The best score on vimgolf.com is **{best}** ({challenge.entries} entries). VimGolf scores "
        f"include `ZZ` to save, so your score is your keys + {vimgolf.SAVE_KEYS}."
        if best
        else ""
    )
    task = Task(
        goal=f"VimGolf: {challenge.title}",
        start=challenge.start,
        cursor=(1, 0),
        target=challenge.target,
        solution="—",
        hint="No hints in VimGolf. Other people's solutions are on vimgolf.com; the link is on the results screen.",
        ft="",
        lesson_id="vimgolf",
        ref_override=ref,
    )
    return Lesson(
        id="vimgolf",
        week=0,
        day=0,
        title=f"VimGolf: {challenge.title}",
        intro=f"Today's challenge from [vimgolf.com]({challenge.url}): make the text match, in as few "
        f"keystrokes as you can. {best_text}",
        keys=[],
        tasks=[task],
    )


def placement_lesson(lessons: list[Lesson]) -> Lesson:
    """The first and last task of every lesson except the weekly reviews."""
    tasks = [t for lesson in lessons if not lesson.review for t in (lesson.tasks[0], lesson.tasks[-1])]
    return Lesson(
        id="placement",
        week=0,
        day=0,
        title="Placement test",
        intro="Two tasks from every lesson, so you can skip what you already know. A lesson counts "
        "as known when you solve both of its tasks without `:Hint` and in at most about 1.5× the "
        "reference keystrokes. Don't guess: `:Skip` whatever you don't know. That's what the "
        "test is for.",
        keys=[],
        tasks=tasks,
    )


def code_span(text: str) -> str:
    """`text` as Markdown code, even when it has backticks in it (`` `a ``)."""
    if "`" not in text:
        return f"`{text}`"
    fence = "`" * (max(len(run) for run in re.findall("`+", text)) + 1)
    return f"{fence} {text} {fence}"


def lesson_markdown(lesson: Lesson, best: dict[int, int] | None = None) -> str:
    keys = f"**New keys** {'  '.join(code_span(k) for k in lesson.keys)}\n\n" if lesson.keys else ""
    tasks = ""
    if best is not None:
        rows = []
        for i, task in enumerate(lesson.tasks):
            mark = f"✓ {best[i]} keys" if i in best else "·"
            rows.append(f"- {task.goal} *({mark}, ref {task.ref})*" if i in best else f"- {task.goal}")
        tasks = f"**{len(best)}/{len(lesson.tasks)} recalled**\n\n" + "\n".join(rows)
    return f"{lesson.intro}\n\n{keys}{tasks}"


class StatsView(VerticalScroll):
    """Progress tables; `refresh_stats` rebuilds them."""

    def compose(self) -> ComposeResult:
        yield Static(id="overview")
        yield Static("Keystrokes · solved tasks · efficiency = reference keys ÷ your keys", classes="section-label")
        yield DataTable(id="keys-table")
        yield Static("Decks", classes="section-label")
        yield DataTable(id="decks-table")
        yield Static("Card accuracy", classes="section-label")
        yield DataTable(id="accuracy-table")
        yield Static("Trouble spots · forgotten most often", classes="section-label")
        yield DataTable(id="trouble-table")
        yield Static("Habits · what hardtime.nvim caught you doing", classes="section-label")
        yield DataTable(id="habits-table")
        yield Static("VimGolf · your score includes ZZ, like on vimgolf.com", classes="section-label")
        yield DataTable(id="vimgolf-table")

    def table(self, table_id: str, *columns: str) -> DataTable:
        table = self.query_one(f"#{table_id}", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns)
        table.cursor_type = "none"
        return table

    def placeholders(self) -> None:
        """A dim "nothing yet" row in every table that stayed empty."""
        for table in self.query(DataTable):
            if table.row_count == 0 and table.columns:
                table.add_row(tint(self.app, "nothing yet", "text-muted"), *[""] * (len(table.columns) - 1))

    def refresh_stats(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        progress, lessons, decks = app.progress, app.lessons, app.decks
        today = date.today()

        done = sum(progress.is_done(lesson) for lesson in lessons)
        placed = sum(progress.is_placed(lesson) for lesson in lessons)
        tasks_total = sum(len(lesson.tasks) for lesson in lessons)
        tasks_solved = sum(len(progress.best(lesson)) for lesson in lessons)
        self.query_one("#overview", Static).update(
            f"{streak_text(progress.streak())} · {plural(len(progress.days_trained()), 'day')} trained · "
            f"[b]{done}/{len(lessons)}[/] lessons ({placed} placed) · {tasks_solved}/{tasks_total} tasks solved"
        )

        table = self.table("keys-table", "Day", "Tasks", "Your keys", "Reference", "Efficiency")
        for day, n, keys, ref in progress.efficiency_by_day():
            table.add_row(day, str(n), str(keys), str(ref), f"{100 * ref / keys:.0f}%" if keys else "")

        items = progress.items("card")
        unlocked = {c.id for c in progress.unlocked(decks, lessons)}
        table = self.table("decks-table", "Deck", "Cards", "Unlocked", "Seen", "Mature (3+ weeks)", "Due today")
        for deck in decks.values():
            ids = [c.id for c in deck.cards]
            seen = [items[i] for i in ids if i in items]
            table.add_row(
                deck.title,
                str(len(ids)),
                str(sum(i in unlocked for i in ids)),
                str(len(seen)),
                str(sum(item.interval >= 21 for item in seen)),
                str(sum(item.due <= today for item in seen)),
            )
        drill_items = progress.items("drill")
        seen = [drill_items[d.item_id] for d in app.drills if d.item_id in drill_items]
        if drills.Hyprland().available or seen:
            table.add_row(
                "Omarchy drills (live)",
                str(len(app.drills)),
                str(len(app.drills)),
                str(len(seen)),
                str(sum(item.interval >= 21 for item in seen)),
                str(sum(item.due <= today for item in seen)),
            )

        table = self.table("accuracy-table", "Day", "Cards answered", "Correct")
        for day, n, correct in progress.card_accuracy():
            table.add_row(day, str(n), f"{100 * correct / n:.0f}%")

        cards = {c.id: c for deck in decks.values() for c in deck.cards}
        tasks = {t.item_id: t for lesson in lessons for t in lesson.tasks}
        table = self.table("trouble-table", "What", "Answer", "Forgotten")
        for item in progress.hardest():
            if item.id in cards:
                table.add_row(Text(cards[item.id].prompt), Text(cards[item.id].shown), str(item.lapses))
            elif item.id in tasks:
                table.add_row(Text(tasks[item.id].goal), Text(tasks[item.id].solution), str(item.lapses))

        table = self.table("habits-table", "Message", "Last two weeks", "All time", "Last seen")
        for habit in habits.habits()[:10]:
            table.add_row(Text(habit.message), str(habit.recent), str(habit.total), habit.last.isoformat())

        table = self.table("vimgolf-table", "Day", "Challenge", "Your score", "Best on vimgolf.com")
        for day, title, score, best in progress.vimgolf_history():
            table.add_row(day, Text(title), str(score) if score else tint(app, "not solved", "text-muted"), str(best) if best else "")
        self.placeholders()


def progress_bar(done: int, total: int, width: int = 40) -> str:
    filled = round(width * done / total) if total else 0
    return f"[$primary]{'━' * filled}[/][$panel]{'━' * (width - filled)}[/]"


def keybar(*pairs: tuple[str, str]) -> str:
    """One line of key hints, lazygit-style: the key in mauve, what it does after it."""
    return "  ".join(f"[bold $primary]{key}[/] {what}" for key, what in pairs)


class MainScreen(Screen):
    """Everything at once, lazygit-style: Today and Lessons on the left, the
    highlighted entry on the right, progress below it. Tab moves between panes."""

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
        self.query_one("#plan").border_subtitle = f"about {left} min left" if left else "all done"

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
        block = progress.hardtime_block_date()
        hardtime = "blocking" if date.today() >= block else f"blocks from {block:%b %d}"
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

    # events

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list is self.focused:
            self.show_detail()

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


class StatsScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back"), Binding("q", "app.pop_screen", "Back", show=False),
                Binding("j", "scroll(2)", "Down", show=False), Binding("k", "scroll(-2)", "Up", show=False)]

    def compose(self) -> ComposeResult:
        yield StatsView(id="stats-view", classes="pane")
        yield Static(keybar(("j/k", "scroll"), ("esc", "back")), classes="keybar")

    def on_mount(self) -> None:
        view = self.query_one(StatsView)
        view.border_title = "Stats"
        view.refresh_stats()
        view.focus()

    def action_scroll(self, lines: int) -> None:
        self.query_one(StatsView).scroll_relative(y=lines)


class LessonScreen(Screen):
    """A lesson's intro; Enter runs it in Neovim. Dismisses when the user moves on."""

    BINDINGS = [
        Binding("enter", "start", "Start", priority=True),
        Binding("escape", "back", "Back"),
        Binding("h", "back", "Back", show=False),
    ]

    def __init__(
        self,
        lesson: Lesson,
        on_results: Callable[[list[TaskResult]], str] | None = None,
        start: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        """`on_results` stores the results and returns a note for the results screen;
        `start` runs something other than the lesson's tasks (endless mode)."""
        super().__init__()
        self.lesson = lesson
        self.on_results = on_results
        self.start = start

    def compose(self) -> ComposeResult:
        lesson = self.lesson
        with VerticalScroll(id="lesson-panel", classes="pane column"):
            rounds = f" {ROUNDS_HELP} {RETRY_HELP}" if lesson.week else f" {RETRY_HELP}" if lesson.id == "review" else ""
            count = f"{plural(len(lesson.tasks), 'task')}.{rounds} " if len(lesson.tasks) > 1 else ""
            help_text = VIMGOLF_HELP if lesson.id == "vimgolf" else TASK_HELP
            yield Markdown(f"{lesson_markdown(lesson)}\n\n{count}{help_text}")
        yield Static(keybar(("enter", "start"), ("esc", "back")), classes="keybar")

    def on_mount(self) -> None:
        lesson = self.lesson
        self.query_one("#lesson-panel").border_title = f"{lesson.label} · {lesson.title}" if lesson.week else lesson.title

    def action_back(self) -> None:
        self.dismiss(None)

    def action_start(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        if self.start:
            self.start(lambda: self.dismiss(True))
        else:
            app.start_lesson(self.lesson, self.on_results, done=lambda: self.dismiss(True))


def why_these_keys(missed: list[TaskResult], most: int = 3) -> Content:
    """For the tasks you missed: the reference keys and what they stand for."""
    lines, values, said = [], {}, set()
    for r in {r.task.solution: r for r in missed}.values():
        found = [h for h in hooks(r.task.solution) if h not in said]  # each hook once
        if not found or len(lines) == most:
            continue
        said.update(found)
        n = len(lines)
        values[f"k{n}"], values[f"h{n}"] = r.task.solution, " · ".join(found)
        lines.append(f"[b]$k{n}[/]  [$accent]$h{n}[/]")
    if not lines:
        return Content("")
    return Content.from_markup("[dim]Why these keys[/]\n" + "\n".join(lines), **values)


class ResultsScreen(Screen):
    """How a lesson went, in the same centred column as cards and the lesson itself.
    Dismisses with True to run the lesson again, False to move on."""

    BINDINGS = [
        Binding("r", "again", "Again"),
        Binding("escape", "done", "Done"),
        Binding("enter", "done", "Done", show=False, priority=True),
        Binding("q", "done", "Done", show=False),
        Binding("j", "scroll(2)", "Down", show=False),
        Binding("k", "scroll(-2)", "Up", show=False),
    ]

    def __init__(self, lesson: Lesson, results: list[TaskResult], note: str = "", subtitle: str = "") -> None:
        super().__init__()
        self.lesson = lesson
        self.results = results
        self.note = note
        self.subtitle = subtitle

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="results-panel", classes="pane column"):
            yield Static(id="results-bar")
            yield Static(id="results-summary", classes="prompt")
            if self.note:
                yield Static(self.note, id="note")
            yield Static(id="results-list")
            missed = [r for r in self.results if r.status in ("failed", "skipped")]
            if missed:
                yield Static(why_these_keys(missed), id="results-why")
        yield Static(keybar(("enter", "done"), ("r", "again")), classes="keybar")

    def on_mount(self) -> None:
        results = self.results
        recall = [r for r in results if r.task.phase != "learn"]
        two_rounds = len(recall) < len(results)
        solved = sum(r.status == "solved" for r in recall)
        beat = sum(r.status == "solved" and r.count < r.task.ref for r in recall)
        panel = self.query_one("#results-panel")
        panel.border_title = f"{self.lesson.label} · {self.lesson.title}" if self.lesson.week else self.lesson.title
        panel.border_subtitle = self.subtitle or (f"{solved}/{len(recall)} recalled" if two_rounds else f"{solved}/{len(recall)} solved")
        self.query_one("#results-bar", Static).update(progress_bar(solved, len(recall)))
        verb = "recalled" if two_rounds else "solved"
        self.query_one("#results-summary", Static).update(
            f"{solved} of {len(recall)} {verb}" + (f" · {beat} beat the reference" if beat else ""))

        budgets = any(r.budget for r in results)
        table = Table(box=None, show_header=True, header_style="dim", expand=True, padding=(0, 1, 0, 0), pad_edge=False)
        table.add_column("", width=1, no_wrap=True)
        table.add_column("task", ratio=3, no_wrap=True, overflow="ellipsis")
        table.add_column("you typed", ratio=2, no_wrap=True, overflow="ellipsis")
        table.add_column("budget" if budgets else "ref", justify="right", no_wrap=True)

        def rows(title: str, round_results: list[TaskResult]) -> None:
            if title:
                table.add_row("", Text(title, style="dim bold"), "", "")
            for r in round_results:
                label, colour = STATUS[r.status]
                mark = {"solved": "✓", "unseen": "·"}.get(r.status, "✗")
                if r.status == "solved":
                    good = r.count <= (r.budget or r.task.ref)
                    keys = Text(r.keys) if r.keys else Text("")
                    count = tint(self.app, f"{r.count}/{r.budget or r.task.ref}", "success" if good else "text-muted")
                elif r.status == "unseen":
                    keys, count = tint(self.app, label, "text-muted"), Text("")
                else:  # what it should have been, louder
                    keys = Text.assemble((f"{label}  ", "dim"), tint(self.app, r.task.solution, "accent"))
                    count = tint(self.app, str(r.budget or r.task.ref), "text-muted")
                goal = f"level {r.level} · {r.task.goal}" if r.task.phase == "climb" else r.task.goal
                table.add_row(tint(self.app, mark, colour), Text(goal), keys, count)

        if two_rounds:
            learn = [r for r in results if r.task.phase == "learn"]
            rows("Recall", recall)
            table.add_row("", "", "", "")
            rows(f"Learn · {sum(r.status == 'solved' for r in learn)}/{len(learn)} typed with the keys shown", learn)
        else:
            rows("", results)
        legend = Text("n/ref: your keys and the reference solution's; fewer and you beat it" if not budgets
                      else "n/budget: your keys and the most allowed at that level", style="dim")
        self.query_one("#results-list", Static).update(Group(table, Text(""), legend))
        panel.focus()

    def action_scroll(self, lines: int) -> None:
        self.query_one("#results-panel", VerticalScroll).scroll_relative(y=lines)

    def action_again(self) -> None:
        self.dismiss(True)

    def action_done(self) -> None:
        self.dismiss(False)


class CardScreen(Screen):
    """Type the keys for each prompt. Dismisses with (correct, answered)."""

    BINDINGS = [
        Binding("escape", "finish", "Stop"),
        Binding("enter", "next", "Next", show=False),
        Binding("o", "override", "I was right", show=False),
    ]

    def __init__(self, cards: list[Card], decks: dict[str, Deck], title: str) -> None:
        super().__init__()
        self.queue = list(cards)
        self.total = len(cards)
        self.decks = decks
        self.title_text = title
        self.retried: set[str] = set()
        self.pending: tuple[Card, bool, str] | None = None
        self.intro = False  # the card on screen is new to you: its answer is shown, you type it once
        self.correct = 0
        self.answered = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="card-panel", classes="pane column"):
            yield Static(id="card-bar")
            yield Static(id="card-prompt", classes="prompt")
            yield Input(id="card-input")
            yield Static(id="card-feedback")
        yield Static(id="card-help", classes="keybar")

    def on_mount(self) -> None:
        self.show_card()

    def show_card(self) -> None:
        if not self.queue:
            self.dismiss((self.correct, self.answered))
            return
        card = self.queue[0]
        done = self.total - len([c for c in self.queue if c.id not in self.retried])
        panel = self.query_one("#card-panel")
        panel.border_title = f"{self.title_text} · {self.decks[card.deck].title}"
        app: VimniscientApp = self.app  # type: ignore[assignment]
        # never answered from memory, and not introduced since the last miss
        item = app.progress.item(card.id)
        self.intro = card.id not in self.retried and not app.progress.ever_right(card.id) and (not item or item.reps == 0)
        again = "new · " if self.intro else "again · " if card.id in self.retried else ""
        panel.border_subtitle = again + f"{min(done + 1, self.total)}/{self.total}"
        self.query_one("#card-bar", Static).update(progress_bar(done, self.total))
        self.query_one("#card-prompt", Static).update(Content(card.prompt))
        box = self.query_one("#card-input", Input)
        box.value = ""
        box.disabled = False
        box.placeholder = (
            "modifiers + key, like CTRL SHIFT + X"
            if card.style == "combo"
            else "the keys as typed: <C-x> for Ctrl-x, <leader> for Space"
        )
        box.focus()
        self.query_one("#card-feedback", Static).update(self.introduction(card) if self.intro else "")
        self.query_one("#card-help", Static).update(keybar(("enter", "check"), ("esc", "stop")))

    def introduction(self, card: Card, again: bool = False) -> Content:
        """A new card's answer, to type once; it's asked from memory next time."""
        why = "\n".join(hooks(card.answers[0])) if card.deck in HOOK_DECKS else ""
        lead = "[$error]✗[/]  type it as shown:" if again else "[$accent]new[/]  type it once:"
        note = "\n[dim]$note[/]" if card.note else ""
        return Content.from_markup(f"{lead} [b]$shown[/]{note}" + ("\n[dim]$why[/]" if why else ""),
                                   shown=card.shown, note=card.note, why=why)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.pending or not self.queue:
            return
        card = self.queue[0]
        correct = is_correct(event.value, card.answers, card.style, card.case_sensitive)
        if self.intro and not correct:  # copying it out: try again
            event.input.value = ""
            self.query_one("#card-feedback", Static).update(self.introduction(card, again=True))
            return
        self.pending = (card, correct, event.value)
        event.input.disabled = True
        self.set_focus(None)
        self.show_feedback()

    def show_feedback(self) -> None:
        card, correct, _ = self.pending  # type: ignore[misc]
        # answers are put in as variables: as markup, `[b` or `[d` would break it
        also = "   [dim]also $also[/]" if card.also else ""
        note = "\n[dim]$note[/]" if card.note else ""
        mark = "[$success]✓[/]" if correct else "[$error]✗[/]"
        # what the keys stand for, only now that the answer is out; louder after a miss
        why = "\n".join(hooks(card.answers[0])) if card.deck in HOOK_DECKS else ""
        why_markup = ("\n[dim]$why[/]" if correct else "\n[$accent]$why[/]") if why else ""
        text = Content.from_markup(f"{mark}  [b]$shown[/]{also}{note}{why_markup}", shown=card.shown,
                                   also=", ".join(card.also), note=card.note, why=why)
        if correct:
            help_text = keybar(("enter", "next"), ("esc", "stop"))
        else:
            help_text = keybar(("enter", "next"), ("o", "I was right"), ("esc", "stop"))
        self.query_one("#card-feedback", Static).update(text)
        self.query_one("#card-help", Static).update(help_text)

    def settle(self) -> None:
        """Grade the answered card (only the first try of a session counts)."""
        if not self.pending:
            return
        card, correct, answer = self.pending
        self.pending = None
        self.queue.pop(0)
        app: VimniscientApp = self.app  # type: ignore[assignment]
        if self.intro:  # typed with the answer shown: scheduled for tomorrow, not scored
            app.progress.grade(card.id, "card", srs.GOOD)
            return
        if card.id in self.retried:
            return
        self.answered += 1
        self.correct += correct
        app.progress.log_card(card, correct, answer)
        known = app.progress.item(card.id) is not None
        grade = (srs.GOOD if known else srs.EASY) if correct else srs.AGAIN
        app.progress.grade(card.id, "card", grade)
        if not correct:
            self.retried.add(card.id)
            self.queue.append(card)

    def action_next(self) -> None:
        if self.pending:
            self.settle()
            self.show_card()

    def action_override(self) -> None:
        if self.pending and not self.pending[1]:
            card, _, answer = self.pending
            self.pending = (card, True, answer)
            self.show_feedback()

    def action_finish(self) -> None:
        self.settle()
        self.dismiss((self.correct, self.answered))


class DrillScreen(Screen):
    """Live Omarchy drills: do it for real, the event socket confirms it."""

    BINDINGS = [
        Binding("h", "hint", "Hint"),
        Binding("s", "skip", "Skip"),
        Binding("escape", "stop", "Stop"),
    ]
    AUTO_HINT_SECONDS = 25

    def __init__(self, drill_list: list[drills.Drill], title: str) -> None:
        super().__init__()
        self.queue = list(drill_list)
        self.total = len(drill_list)
        self.title_text = title
        self.hypr = drills.Hyprland()
        self.current: drills.DrillRun | None = None
        self.hinted = False
        self.done_count = 0
        self.stopping = False

    def compose(self) -> ComposeResult:
        with Vertical(id="drill-panel", classes="pane column"):
            yield Static(id="drill-bar")
            yield Static(id="drill-prompt", classes="prompt")
            yield Static(id="drill-steps")
            yield Static(id="drill-status")
        yield Static(keybar(("h", "hint"), ("s", "skip"), ("esc", "stop")), classes="keybar")

    async def on_mount(self) -> None:
        if not self.hypr.available:
            self.app.notify("No Hyprland session found, so no drills.", severity="warning")
            self.dismiss(0)
            return
        self.home_ws = await asyncio.to_thread(self.hypr.home)
        self.run_worker(self.listen(), exclusive=True, group="drill-events")
        self.set_interval(1, self.tick)
        await self.next_drill()

    async def listen(self) -> None:
        async for line in self.hypr.events():
            self.on_hypr_event(line)

    async def next_drill(self) -> None:
        if self.stopping:
            return
        if not self.queue:
            await self.stop()
            return
        drill = self.queue[0]
        self.query_one("#drill-status", Static).update("Opening the drill window…")
        addr = await asyncio.to_thread(self.hypr.ensure_drill_window)
        if not addr:
            self.app.notify("Couldn't open the drill window.", severity="error")
            await self.stop()
            return
        self.current = drills.DrillRun(drill, addr, self.home_ws)
        self.hinted = False
        done = self.total - len(self.queue)
        panel = self.query_one("#drill-panel")
        panel.border_title = f"{self.title_text} · {drill.title}"
        panel.border_subtitle = f"{done + 1}/{self.total}"
        self.query_one("#drill-bar", Static).update(progress_bar(done, self.total))
        self.query_one("#drill-prompt", Static).update(self.current.text(drill.prompt))
        self.show_steps()
        self.tick()

    def show_steps(self) -> None:
        run = self.current
        if not run:
            return
        lines = []
        for i, step in enumerate(run.drill.steps):
            mark = "[$success]✓[/]" if i < run.step else "[$accent]›[/]" if i == run.step else "[dim]·[/]"
            lines.append(f"{mark}  {run.text(step.done)}")
        if run.drill.steps[min(run.step, len(run.drill.steps) - 1)].active == "$drill" or run.drill.id == "float":
            lines.append("\n[dim]Do it to the window titled “Vimniscient drill” (focus it first).[/]")
        self.query_one("#drill-steps", Static).update("\n".join(lines))

    def tick(self) -> None:
        run = self.current
        if not run or run.finished:
            return
        seconds = int(time.monotonic() - run.started)
        if seconds >= self.AUTO_HINT_SECONDS and not self.hinted:
            self.action_hint()
            return
        hint = self.hint_text() if self.hinted else "[dim]waiting for Hyprland…[/]"
        self.query_one("#drill-status", Static).update(f"[dim]{seconds}s[/]  {hint}")

    def hint_text(self) -> str:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        cards = {c.prompt: c for c in app.decks.get("omarchy", Deck("omarchy", "Omarchy")).cards}
        parts = [f"{b}: [b $foreground]{', '.join(cards[b].answers)}[/]" for b in self.current.drill.bindings if b in cards]
        text = " · ".join(parts) or "see SUPER + K"
        if any(b.endswith(" 1") for b in self.current.drill.bindings):
            text += " (1 stands for any number)"
        return text

    def on_hypr_event(self, line: str) -> None:
        run = self.current
        if not run or run.finished:
            return
        if run.feed(line):
            self.show_steps()
            if run.finished:
                self.finish_drill(skipped=False)

    def finish_drill(self, skipped: bool) -> None:
        run = self.current
        app: VimniscientApp = self.app  # type: ignore[assignment]
        seconds = time.monotonic() - run.started
        app.progress.grade(run.drill.item_id, "drill", drills.grade(seconds, self.hinted, skipped))
        app.progress.log_drill(run.drill.id, seconds, self.hinted, skipped)
        self.queue.pop(0)
        if skipped:
            self.query_one("#drill-status", Static).update(f"[$warning]Skipped.[/] {self.hint_text()}")
        else:
            self.done_count += 1
            self.query_one("#drill-status", Static).update(f"[$success]Done in {seconds:.0f}s.[/]")
        self.set_timer(1.5 if not skipped else 3, self.next_drill)

    def action_hint(self) -> None:
        if self.current and not self.current.finished:
            self.hinted = True
            seconds = int(time.monotonic() - self.current.started)
            self.query_one("#drill-status", Static).update(f"[dim]{seconds}s[/]  {self.hint_text()}")

    def action_skip(self) -> None:
        if self.current and not self.current.finished:
            self.current.step = len(self.current.drill.steps)  # stop listening for this one
            self.finish_drill(skipped=True)

    async def stop(self) -> None:
        if self.stopping:  # Esc while the next drill was about to load: stop once
            return
        self.stopping = True
        self.current = None
        await asyncio.to_thread(self.hypr.close_drill_window)
        self.dismiss(self.done_count)

    async def action_stop(self) -> None:
        await self.stop()


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
    #plan { height: 8; }
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
    #results-why { height: auto; padding: 1 0 0 0; }

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
        on_results: Callable[[list[TaskResult]], str] | None = None,
        done: Callable[[], None] = lambda: None,
    ) -> None:
        """Run a lesson in Neovim, then show the results; `done` runs when the user moves on.
        Real lessons (not review, placement or VimGolf) run in two rounds: Learn, then Recall.
        In lessons and reviews, a skipped task is shown, typed, and asked again at the end."""
        session = replace(lesson, tasks=two_rounds(lesson)) if lesson.week else lesson
        with self.suspend():
            results = run_lesson(session, retry=bool(lesson.week) or lesson.id == "review")
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

    def plan(self) -> list[today.Step]:
        return today.plan(self.progress, self.lessons, self.decks, self.drills)

    def todays_drills(self) -> list[drills.Drill]:
        return today.todays_drills(self.progress, self.drills)

    def step(self, step_id: str, direct: bool = False) -> Callable[[Callable[[], None]], None] | None:
        """One step of today's routine, or None when there's nothing to do for it.

        `direct` starts lessons without their intro screen (the main screen shows it already)."""
        progress = self.progress
        if step_id == "cards":
            cards = progress.due_cards(self.decks, self.lessons) + progress.new_cards(self.decks, self.lessons)
            if cards:
                return lambda done: self.push_screen(CardScreen(cards, self.decks, "Today's cards"), lambda _: done())
        elif step_id == "drills":
            todays = self.todays_drills()
            if todays:
                return lambda done: self.push_screen(DrillScreen(todays, "Omarchy drills"), lambda _: done())
        elif step_id == "review":
            review = today.review_tasks(progress, self.lessons)
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

    def start_endless(self, start: int, done: Callable[[], None]) -> None:
        """Climb from `start` until the user quits, then show how it went."""
        best = self.progress.endless_best()
        rungs = endless.ladder(self.lessons, start)
        pool = {t.item_id: t for t, _ in rungs}
        with self.suspend():
            results = run_endless(pool, [(t.item_id, v) for t, v in rungs], start, endless.RAMP, endless.GAP)
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
