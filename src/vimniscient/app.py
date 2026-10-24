"""The Textual menu around the lessons."""

from datetime import date

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from vimniscient.lessons import Lesson, load_lessons
from vimniscient.progress import Progress
from vimniscient.session import TaskResult, run_lesson

LOGO = """\
█ █ █ █▀▄▀█ █▄ █ █ ▄▀▀ ▄▀▀ █ ██▀ █▄ █ ▀█▀
▀▄▀ █ █ ▀ █ █ ▀█ █ ▄██ ▀▄▄ █ █▄▄ █ ▀█  █ """

STATUS = {
    "solved": "[green]solved[/]",
    "skipped": "[yellow]skipped[/]",
    "quit": "[red]quit[/]",
    "unseen": "[dim]not reached[/]",
}


class HomeScreen(Screen):
    BINDINGS = [
        Binding("t", "today", "Today's lesson"),
        Binding("j", "move(1)", "Down", show=False),
        Binding("k", "move(-1)", "Up", show=False),
        Binding("l", "open", "Open", show=False),
        Binding("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(LOGO, id="logo")
        yield Static(id="stats")
        yield Static(id="today")
        yield OptionList(id="lessons")
        yield Footer()

    def on_screen_resume(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        progress, lessons = app.progress, app.lessons
        done = sum(progress.is_done(lesson) for lesson in lessons)
        block = progress.hardtime_block_date()
        hardtime = "blocking" if date.today() >= block else f"hints until {block:%b %d}"
        streak = progress.streak()
        self.query_one("#stats", Static).update(
            f"streak [b]{streak}[/] day{'' if streak == 1 else 's'} · [b]{done}/{len(lessons)}[/] lessons · hardtime: {hardtime}"
        )
        nxt = progress.next_lesson(lessons)
        self.query_one("#today", Static).update(
            f"[b]Today:[/] {nxt.label}: {nxt.title}  [dim](press t)[/]" if nxt else "[b]All lessons done.[/] Pick any to practise."
        )

        options: list[Option] = []
        week = None
        for lesson in lessons:
            if lesson.week != week:
                week = lesson.week
                options.append(Option(f"[b]Week {week}[/]", disabled=True))
            best = progress.best(lesson)
            mark = "[green]✓[/]" if len(best) == len(lesson.tasks) else f"[dim]{len(best)}/{len(lesson.tasks)}[/]"
            options.append(Option(f"  {mark}  Day {lesson.day}: {lesson.title}", id=lesson.id))
        lessons_list = self.query_one("#lessons", OptionList)
        highlighted = lessons_list.highlighted
        lessons_list.clear_options()
        lessons_list.add_options(options)
        if highlighted is not None:
            lessons_list.highlighted = highlighted
        elif nxt:
            lessons_list.highlighted = lessons_list.get_option_index(nxt.id)
        lessons_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.app.push_screen(LessonScreen(self.app.lesson(event.option.id)))  # type: ignore[attr-defined]

    def action_move(self, step: int) -> None:
        lessons_list = self.query_one("#lessons", OptionList)
        if step > 0:
            lessons_list.action_cursor_down()
        else:
            lessons_list.action_cursor_up()

    def action_open(self) -> None:
        self.query_one("#lessons", OptionList).action_select()

    def action_today(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        nxt = app.progress.next_lesson(app.lessons)
        if nxt:
            app.push_screen(LessonScreen(nxt))


class LessonScreen(Screen):
    BINDINGS = [
        Binding("enter", "start", "Start", priority=True),
        Binding("escape", "app.pop_screen", "Back"),
        Binding("h", "app.pop_screen", "Back", show=False),
    ]

    def __init__(self, lesson: Lesson) -> None:
        super().__init__()
        self.lesson = lesson

    def compose(self) -> ComposeResult:
        lesson = self.lesson
        keys = "  ".join(f"`{k}`" for k in lesson.keys)
        yield VerticalScroll(
            Markdown(
                f"# {lesson.label}: {lesson.title}\n\n{lesson.intro}\n\n**New keys:** {keys}\n\n"
                f"{len(lesson.tasks)} tasks. The goal shows in the top window, your text below. "
                "When they match the next task loads by itself. Inside Neovim: "
                "`:Hint` (twice for the answer), `:Skip`, `:Reset`, `:q` to stop.\n\n"
                "**Press Enter to start.**"
            )
        )
        yield Footer()

    def action_start(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        with app.suspend():
            results = run_lesson(self.lesson)
        app.progress.record(self.lesson, results)
        app.switch_screen(ResultsScreen(self.lesson, results))


class ResultsScreen(Screen):
    BINDINGS = [
        Binding("r", "retry", "Again"),
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Back", show=False),
    ]

    def __init__(self, lesson: Lesson, results: list[TaskResult]) -> None:
        super().__init__()
        self.lesson = lesson
        self.results = results

    def compose(self) -> ComposeResult:
        solved = sum(r.status == "solved" for r in self.results)
        yield Static(f"[b]{self.lesson.label}: {self.lesson.title}[/]  {solved}/{len(self.results)} solved", id="summary")
        yield DataTable(id="results", cursor_type="row", zebra_stripes=True)
        yield Static("[dim]ref = the reference solution's keystrokes. Fewer keys than ref = you beat it.[/]")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("#", "Task", "Result", "Keys", "Ref", "You typed", "Reference")
        for i, r in enumerate(self.results, 1):
            keys = str(r.count) if r.status == "solved" else ""
            if r.status == "solved" and r.count <= r.task.ref:
                keys = f"[green]{keys}[/]"
            table.add_row(str(i), r.task.goal, STATUS[r.status], keys, str(r.task.ref), r.keys, r.task.solution)

    def action_retry(self) -> None:
        self.app.switch_screen(LessonScreen(self.lesson))


class VimniscientApp(App):
    TITLE = "Vimniscient"
    CSS = """
    #logo { color: $accent; padding: 1 2 0 2; }
    #stats { padding: 0 2; color: $text-muted; }
    #today { padding: 1 2; }
    #lessons { margin: 0 2; height: 1fr; }
    #summary { padding: 1 2; }
    #results { margin: 0 2; height: auto; max-height: 1fr; }
    LessonScreen VerticalScroll { padding: 1 2; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.lessons = load_lessons()
        self.progress = Progress()

    def lesson(self, lesson_id: str) -> Lesson:
        return next(lesson for lesson in self.lessons if lesson.id == lesson_id)

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())
