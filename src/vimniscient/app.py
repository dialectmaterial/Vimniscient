"""The Textual interface: four numbered screens around lessons, cards and drills.

The look follows SOL ESSENCE: flat, borderless lists with the highlighted
entry's text below them, muted help lines, and the colours of the Omarchy
theme in use (Catppuccin Mocha unless another one matches).
"""

import asyncio
import os
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import DataTable, Footer, Input, Markdown, OptionList, Static, TabbedContent, TabPane
from textual.widgets.option_list import Option

from vimniscient import drills, habits, srs, vimgolf
from vimniscient.answer import is_correct
from vimniscient.cards import Card, Deck, load_decks
from vimniscient.lessons import Lesson, Task, load_lessons
from vimniscient.progress import Progress
from vimniscient.session import TaskResult, run_lesson

LOGO = """\
█ █ █ █▀▄▀█ █▄ █ █ ▄▀▀ ▄▀▀ █ ██▀ █▄ █ ▀█▀
▀▄▀ █ █ ▀ █ █ ▀█ █ ▄██ ▀▄▄ █ █▄▄ █ ▀█  █ """

# Result labels and the theme colour each is shown in.
STATUS = {
    "solved": ("solved", "success"),
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

SCREENS = {"today": "Today", "lessons": "Lessons", "practice": "Practice", "stats": "Stats"}

TASK_HELP = (
    "The goal shows in the top window, your text below. When they match, the next task loads by "
    "itself. Inside Neovim: `:Hint` (twice for the answer), `:Skip`, `:Reset`, `:q` to stop."
)


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


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
        solution=f"not published; see {challenge.url}",
        hint=f"No hints in VimGolf. Other people's solutions are on {challenge.url}.",
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


def lesson_markdown(lesson: Lesson, best: dict[int, int] | None = None) -> str:
    keys = f"**New keys** {'  '.join(f'`{k}`' for k in lesson.keys)}\n\n" if lesson.keys else ""
    progress = ""
    if best is not None:
        solved = len(best)
        progress = f"*{solved}/{len(lesson.tasks)} tasks solved*" if solved else f"*{plural(len(lesson.tasks), 'task')}*"
    return f"{lesson.intro}\n\n{keys}{progress}"


class Browser(Vertical):
    """A list above the highlighted entry's text, as in SOL ESSENCE."""

    DEFAULT_CSS = """
    Browser { height: 1fr; }
    Browser > .browser-help { height: auto; padding: 0 0 1 0; color: $text-muted; }
    Browser > OptionList { height: 13; max-height: 45%; border: none; background: $surface; padding: 1; }
    Browser > OptionList:focus { border: none; }
    Browser > .browser-detail { height: 1fr; margin-top: 1; }
    """

    def __init__(self, help_text: str, list_id: str, detail_id: str) -> None:
        super().__init__()
        self.help_text = help_text
        self.list_id = list_id
        self.detail_id = detail_id

    def compose(self) -> ComposeResult:
        yield Static(self.help_text, classes="browser-help")
        yield OptionList(id=self.list_id)
        yield VerticalScroll(Markdown(id=self.detail_id), classes="browser-detail")


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
            f"[b]{plural(progress.streak(), 'day')}[/] streak · {plural(len(progress.days_trained()), 'day')} trained · "
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
                table.add_row(cards[item.id].prompt, cards[item.id].shown, str(item.lapses))
            elif item.id in tasks:
                table.add_row(tasks[item.id].goal, tasks[item.id].solution, str(item.lapses))

        table = self.table("habits-table", "Message", "Last two weeks", "All time", "Last seen")
        for habit in habits.habits()[:10]:
            table.add_row(habit.message, str(habit.recent), str(habit.total), habit.last.isoformat())

        table = self.table("vimgolf-table", "Day", "Challenge", "Your score", "Best on vimgolf.com")
        for day, title, score, best in progress.vimgolf_history():
            table.add_row(day, title, str(score) if score else tint(app, "not solved", "text-muted"), str(best) if best else "")
        self.placeholders()


class MainScreen(Screen):
    """The four screens: Today, Lessons, Practice, Stats."""

    BINDINGS = [
        Binding("t", "app.today", "Start today"),
        *(Binding(str(n), f"show('{name}')", label, show=False) for n, (name, label) in enumerate(SCREENS.items(), 1)),
        Binding("j", "move(1)", "Down", show=False),
        Binding("k", "move(-1)", "Up", show=False),
        Binding("l", "open", "Open", show=False),
        Binding("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="status-line")
        with TabbedContent(id="screens"):
            with TabPane("Today", id="today"):
                yield Static(LOGO, id="logo")
                yield Browser(
                    "Today's routine · arrows browse · Enter runs one step · t runs them all in order",
                    "plan", "plan-detail",
                )
                yield Static(id="habit-line")
            with TabPane("Lessons", id="lessons"):
                yield Browser(
                    "Lessons · arrows browse · Enter starts the lesson · ✓ solved  ○ placed  n/m tasks solved",
                    "lesson-list", "lesson-detail",
                )
            with TabPane("Practice", id="practice"):
                yield Browser(
                    "Practice outside today's routine · arrows browse · Enter starts",
                    "practice-list", "practice-detail",
                )
            with TabPane("Stats", id="stats"):
                yield StatsView(id="stats-view")
        yield Static("1–4 screens · t start today · q quit", id="hint-line")
        yield Footer()

    def on_screen_resume(self) -> None:
        self.refresh_all()

    def on_mount(self) -> None:
        self.refresh_all()

    # data

    def refresh_all(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        progress, lessons = app.progress, app.lessons
        done = sum(progress.is_done(lesson) for lesson in lessons)
        block = progress.hardtime_block_date()
        hardtime = "hardtime blocking" if date.today() >= block else f"hardtime hints until {block:%b %d}"
        self.query_one("#status-line", Static).update(
            f"[bold $accent]Vimniscient[/] · {plural(progress.streak(), 'day')} streak · "
            f"{done}/{len(lessons)} lessons · {hardtime}"
        )
        top = next((h for h in habits.habits() if h.recent), None)
        habit = f"Top habit: {top.message} ({top.recent}× in two weeks)" if top else ""
        if not progress.days_trained():
            habit = "New here? The placement test (Practice, 3) skips the lessons you already know."
        self.query_one("#habit-line", Static).update(habit)
        self.refresh_plan()
        self.refresh_lessons()
        self.refresh_practice()
        self.query_one(StatsView).refresh_stats()

    def plan(self) -> list[tuple[str, str, str, bool]]:
        """Today's steps: (id, label, detail, still to do)."""
        app: VimniscientApp = self.app  # type: ignore[assignment]
        progress, lessons = app.progress, app.lessons
        due, new = progress.due_cards(app.decks, lessons), progress.new_cards(app.decks, lessons)
        todays_drills = app.todays_drills()
        review = progress.due_tasks(lessons)
        review += app.drill_tasks(review)
        nxt = progress.next_lesson(lessons)
        golf_done = progress.vimgolf_done_today()
        return [
            ("cards", "Cards", f"{len(due)} due · {len(new)} new" if due or new else "done",
             bool(due or new)),
            ("drills", "Omarchy drills", plural(len(todays_drills), "drill") if todays_drills else "done",
             bool(todays_drills)),
            ("review", "Review", plural(len(review), "task") if review else "nothing due", bool(review)),
            ("lesson", "Lesson", f"{nxt.label} · {nxt.title}" if nxt else "all done", nxt is not None),
            ("vimgolf", "VimGolf", "done" if golf_done else "today's challenge", not golf_done),
        ]

    PLAN_DETAIL = {
        "cards": "Type the keys for each prompt: Vim, LazyVim, Omarchy, tmux, the shell, foot, Zathura, "
        "and the habits hardtime caught. Due cards first, then up to 10 new ones.",
        "drills": "Do it for real on the *Vimniscient drill* window; Hyprland's events confirm each step. "
        "`h` shows the keys, `s` skips.",
        "review": "Vim tasks from earlier days that are due again, plus a few drills for the habits "
        "hardtime keeps catching.",
        "lesson": "",
        "vimgolf": "One challenge from vimgolf.com, the most played ones first, scored against the leaderboard.",
    }

    def refresh_plan(self) -> None:
        options = []
        for step_id, label, detail, todo in self.plan():
            mark = "[$accent]›[/]" if todo else "[$success]✓[/]"
            text = f"{mark}  [b]{label}[/]  [dim]{detail}[/]"
            options.append(Option(text, id=step_id))
        self.fill("plan", options)
        self.show_plan_detail()

    def show_plan_detail(self) -> None:
        plan_list = self.query_one("#plan", OptionList)
        if plan_list.highlighted is None:
            return
        step_id = plan_list.get_option_at_index(plan_list.highlighted).id
        app: VimniscientApp = self.app  # type: ignore[assignment]
        text = self.PLAN_DETAIL[step_id]
        if step_id == "lesson":
            nxt = app.progress.next_lesson(app.lessons)
            text = f"**{nxt.label} · {nxt.title}**\n\n{lesson_markdown(nxt)}" if nxt else "Every lesson is done."
        self.query_one("#plan-detail", Markdown).update(text)

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
            if len(best) == len(lesson.tasks):
                mark = "[$success]✓  [/]"
            elif progress.is_placed(lesson):
                mark = "[$success]○  [/]"
            else:
                mark = f"[dim]{len(best)}/{len(lesson.tasks)}[/]"
            options.append(Option(f"  {mark}  Day {lesson.day} · {lesson.title}", id=lesson.id))
        nxt = progress.next_lesson(app.lessons)
        self.fill("lesson-list", options, nxt.id if nxt else None)
        self.show_lesson_detail()

    def show_lesson_detail(self) -> None:
        lesson_list = self.query_one("#lesson-list", OptionList)
        if lesson_list.highlighted is None:
            return
        app: VimniscientApp = self.app  # type: ignore[assignment]
        lesson = app.lesson(lesson_list.get_option_at_index(lesson_list.highlighted).id)
        self.query_one("#lesson-detail", Markdown).update(
            f"**{lesson.label} · {lesson.title}**\n\n{lesson_markdown(lesson, app.progress.best(lesson))}"
        )

    PRACTICE = {
        "cards": ("Cards", "Today's due and new cards, outside the routine."),
        "drills": ("Omarchy drills", "Today's drills, or all nine when none are due."),
        "vimgolf": ("VimGolf", "Today's challenge from vimgolf.com."),
        "placement": ("Placement test", "Two tasks from every lesson. Lessons you clearly know are marked "
                      "done, and their other tasks come back in review a week later."),
    }

    def refresh_practice(self) -> None:
        options = [Option(f"[b]{label}[/]", id=key) for key, (label, _) in self.PRACTICE.items()]
        self.fill("practice-list", options)
        self.show_practice_detail()

    def show_practice_detail(self) -> None:
        practice = self.query_one("#practice-list", OptionList)
        if practice.highlighted is not None:
            key = practice.get_option_at_index(practice.highlighted).id
            label, text = self.PRACTICE[key]
            self.query_one("#practice-detail", Markdown).update(f"**{label}**\n\n{text}")

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

    # events

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        {"plan": self.show_plan_detail, "lesson-list": self.show_lesson_detail,
         "practice-list": self.show_practice_detail}.get(event.option_list.id, lambda: None)()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        key = event.option.id
        if event.option_list.id == "lesson-list":
            app.start_lesson(app.lesson(key), done=self.refresh_all)
        elif event.option_list.id == "plan":
            app.run_step(key, self.refresh_all)
        elif event.option_list.id == "practice-list":
            {"cards": app.action_cards, "drills": app.action_drills,
             "vimgolf": app.action_vimgolf, "placement": app.action_placement}[key]()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane = event.pane
        lists = pane.query(OptionList)
        if lists:
            lists.first().focus()
        else:
            pane.query_one(StatsView).focus()

    def action_show(self, name: str) -> None:
        self.query_one("#screens", TabbedContent).active = name

    def focused_list(self) -> OptionList | None:
        return self.focused if isinstance(self.focused, OptionList) else None

    def action_move(self, step: int) -> None:
        option_list = self.focused_list()
        if option_list:
            option_list.action_cursor_down() if step > 0 else option_list.action_cursor_up()
        elif isinstance(self.focused, VerticalScroll):
            self.focused.scroll_relative(y=step * 2)

    def action_open(self) -> None:
        option_list = self.focused_list()
        if option_list:
            option_list.action_select()


class LessonScreen(Screen):
    """A lesson's intro; Enter runs it in Neovim. Dismisses when the user moves on."""

    BINDINGS = [
        Binding("enter", "start", "Start", priority=True),
        Binding("escape", "back", "Back"),
        Binding("h", "back", "Back", show=False),
    ]

    def __init__(self, lesson: Lesson, on_results: Callable[[list[TaskResult]], str] | None = None) -> None:
        """`on_results` stores the results and returns a note for the results screen."""
        super().__init__()
        self.lesson = lesson
        self.on_results = on_results

    def compose(self) -> ComposeResult:
        lesson = self.lesson
        yield Static(lesson.label if lesson.week else "Vimniscient", classes="screen-head")
        yield Static(lesson.title, classes="screen-title")
        yield VerticalScroll(
            Markdown(f"{lesson_markdown(lesson)}\n\n{plural(len(lesson.tasks), 'task')}. {TASK_HELP}"),
            classes="screen-body",
        )
        yield Static("Enter starts · Escape goes back", classes="help")
        yield Footer()

    def action_back(self) -> None:
        self.dismiss(None)

    def action_start(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        app.start_lesson(self.lesson, self.on_results, done=lambda: self.dismiss(True))


class ResultsScreen(Screen):
    """Dismisses with True to run the lesson again, False to move on."""

    BINDINGS = [
        Binding("r", "again", "Again"),
        Binding("escape", "done", "Done"),
        Binding("enter", "done", "Done", show=False, priority=True),  # before the table's row select
        Binding("q", "done", "Done", show=False),
    ]

    def __init__(self, lesson: Lesson, results: list[TaskResult], note: str = "") -> None:
        super().__init__()
        self.lesson = lesson
        self.results = results
        self.note = note

    def compose(self) -> ComposeResult:
        solved = sum(r.status == "solved" for r in self.results)
        yield Static(f"{self.lesson.label if self.lesson.week else 'Results'} · {solved}/{len(self.results)} solved",
                     classes="screen-head")
        yield Static(self.lesson.title, classes="screen-title")
        if self.note:
            yield Static(self.note, id="note")
        yield DataTable(id="results", cursor_type="row")
        yield Static("ref = the reference solution's keystrokes; fewer than ref and you beat it · "
                     "r again · Enter done", classes="help")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("#", "Task", "Result", "Keys", "Ref", "You typed", "Reference")
        for i, r in enumerate(self.results, 1):
            keys = str(r.count) if r.status == "solved" else ""
            if r.status == "solved" and r.count <= r.task.ref:
                keys = tint(self.app, keys, "success")
            label, colour = STATUS[r.status]
            table.add_row(str(i), r.task.goal, tint(self.app, label, colour), keys, str(r.task.ref), r.keys,
                          r.task.solution)

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
        self.correct = 0
        self.answered = 0

    def compose(self) -> ComposeResult:
        yield Static(id="card-head", classes="screen-head")
        yield Static(id="card-prompt", classes="screen-title")
        yield Input(id="card-input")
        yield Static(id="card-feedback")
        yield Static(id="card-help", classes="help")
        yield Footer()

    def on_mount(self) -> None:
        self.show_card()

    def show_card(self) -> None:
        if not self.queue:
            self.dismiss((self.correct, self.answered))
            return
        card = self.queue[0]
        done = self.total - len([c for c in self.queue if c.id not in self.retried])
        again = " · [$warning]again[/]" if card.id in self.retried else ""
        self.query_one("#card-head", Static).update(
            f"{self.title_text} · {min(done + 1, self.total)}/{self.total} · [$accent]{self.decks[card.deck].title}[/]{again}"
        )
        self.query_one("#card-prompt", Static).update(card.prompt)
        box = self.query_one("#card-input", Input)
        box.value = ""
        box.disabled = False
        box.placeholder = (
            "modifiers + key, like CTRL SHIFT + X"
            if card.style == "combo"
            else "the keys as typed: <C-x> for Ctrl-x, <leader> for Space"
        )
        box.focus()
        self.query_one("#card-feedback", Static).update("")
        self.query_one("#card-help", Static).update("Enter checks · Escape stops")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.pending or not self.queue:
            return
        card = self.queue[0]
        correct = is_correct(event.value, card.answers, card.style, card.case_sensitive)
        self.pending = (card, correct, event.value)
        event.input.disabled = True
        self.set_focus(None)
        self.show_feedback()

    def show_feedback(self) -> None:
        card, correct, _ = self.pending  # type: ignore[misc]
        also = f"   [dim]also {', '.join(card.also)}[/]" if card.also else ""
        note = f"\n[dim]{card.note}[/]" if card.note else ""
        if correct:
            text = f"[$success]✓[/]  [b]{card.shown}[/]{also}{note}"
            help_text = "Enter next · Escape stops"
        else:
            text = f"[$error]✗[/]  [b]{card.shown}[/]{also}{note}"
            help_text = "Enter next · o I was right · Escape stops"
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

    def compose(self) -> ComposeResult:
        yield Static(id="drill-head", classes="screen-head")
        yield Static(id="drill-prompt", classes="screen-title")
        yield Static(id="drill-steps")
        yield Static(id="drill-status", classes="help")
        yield Footer()

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
        self.query_one("#drill-head", Static).update(
            f"{self.title_text} · {done + 1}/{self.total} · [$accent]{drill.title}[/]"
        )
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
        hint = self.hint_text() if self.hinted else "h hint · s skip · Escape stops"
        self.query_one("#drill-status", Static).update(f"{seconds}s · {hint}")

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
            self.query_one("#drill-status", Static).update(f"{seconds}s · {self.hint_text()}")

    def action_skip(self) -> None:
        if self.current and not self.current.finished:
            self.current.step = len(self.current.drill.steps)  # stop listening for this one
            self.finish_drill(skipped=True)

    async def stop(self) -> None:
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
    #status-line, #hint-line { padding: 0 2; color: $text-muted; height: 1; }
    #status-line { margin-top: 1; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 1 2 0 2; }
    #logo { color: $accent; height: auto; padding: 0 0 1 0; }
    #habit-line { height: auto; color: $text-muted; padding-top: 1; }
    Markdown { padding: 0 1; margin: 0; }
    MarkdownBlock > .code_inline { background: $surface; color: $primary; }
    .section-label { color: $text-muted; text-style: bold; height: 1; margin-top: 1; }
    DataTable { background: $background; height: auto; max-height: 14; margin-top: 1; }
    DataTable > .datatable--header { background: $surface; color: $text-muted; text-style: bold; }
    #stats-view { height: 1fr; }
    #overview { height: auto; }

    .screen-head { padding: 1 2 0 2; color: $text-muted; height: auto; }
    .screen-title { padding: 1 2; color: $accent; text-style: bold; height: auto; }
    .screen-body { padding: 0 1; height: 1fr; }
    .help { padding: 1 2; color: $text-muted; height: auto; }
    #note { padding: 0 2 1 2; color: $success; height: auto; }
    #results { margin: 0 2; max-height: 1fr; }

    #card-input { margin: 0 2; border: tall $surface; background: $surface; }
    #card-input:focus { border: tall $accent; }
    #card-feedback { padding: 1 2; height: auto; }
    #drill-steps { padding: 0 2; height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.lessons = load_lessons()
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
        self.push_screen(MainScreen())

    # running things

    def start_lesson(
        self,
        lesson: Lesson,
        on_results: Callable[[list[TaskResult]], str] | None = None,
        done: Callable[[], None] = lambda: None,
    ) -> None:
        """Run a lesson in Neovim, then show the results; `done` runs when the user moves on."""
        with self.suspend():
            results = run_lesson(lesson)
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

        self.push_screen(ResultsScreen(lesson, results, note), after)

    def run_steps(self, steps: list[Callable[[Callable[[], None]], None]]) -> None:
        """Run screens one after another; each step calls `done` when finished."""
        if steps:
            steps[0](lambda: self.run_steps(steps[1:]))

    def drill_tasks(self, exclude: list[Task]) -> list[Task]:
        """One task from each lesson that fixes a habit hardtime keeps catching (lessons you've done only)."""
        taken = {t.item_id for t in exclude}
        items = self.progress.items("task")
        tasks = []
        for lesson_id in habits.drill_lessons():
            lesson = next((lesson for lesson in self.lessons if lesson.id == lesson_id), None)
            if not lesson or not self.progress.is_done(lesson):
                continue
            # the task that has gone worst so far
            candidates = [t for t in lesson.tasks if t.item_id not in taken]
            if candidates:
                worst = min(candidates, key=lambda t: items[t.item_id].ease if t.item_id in items else 0)
                tasks.append(worst)
                taken.add(worst.item_id)
        return tasks[:3]

    def step(self, step_id: str) -> Callable[[Callable[[], None]], None] | None:
        """One step of today's routine, or None when there's nothing to do for it."""
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
            review = progress.due_tasks(self.lessons)
            review += self.drill_tasks(review)
            if review:
                return lambda done: self.push_screen(LessonScreen(review_lesson(review)), lambda _: done())
        elif step_id == "lesson":
            nxt = progress.next_lesson(self.lessons)
            if nxt:
                return lambda done: self.push_screen(LessonScreen(nxt), lambda _: done())
        elif step_id == "vimgolf":
            if not progress.vimgolf_done_today():
                return self.start_vimgolf
        return None

    def run_step(self, step_id: str, done: Callable[[], None]) -> None:
        step = self.step(step_id)
        if step:
            step(done)
        else:
            self.notify("Nothing left for this one today.")

    def action_today(self) -> None:
        """Cards, drills, review (plus habit drills), the next lesson, then VimGolf."""
        steps = [s for s in (self.step(i) for i in ("cards", "drills", "review", "lesson", "vimgolf")) if s]
        if not steps:
            self.notify("Nothing due and every lesson done. Pick any lesson to practise.")
        self.run_steps(steps)

    def todays_drills(self) -> list[drills.Drill]:
        if not drills.Hyprland().available:
            return []
        return self.progress.due_drills(self.drills) + self.progress.new_drills(self.drills)

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
