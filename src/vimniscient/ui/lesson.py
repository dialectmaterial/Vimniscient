"""A lesson's intro screen, and the results screen after it."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.widgets import Markdown, Static

from vimniscient.lessons import Lesson
from vimniscient.diagnose import diagnose
from vimniscient.mnemonics import hooks
from vimniscient.session import TaskResult
from vimniscient.ui.common import (
    RETRY_HELP,
    ROUNDS_HELP,
    STATUS,
    TASK_HELP,
    VIMGOLF_HELP,
    keybar,
    lesson_markdown,
    plural,
    progress_bar,
    tint,
)

if TYPE_CHECKING:
    from vimniscient.app import VimniscientApp


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


def your_keys(results: list[TaskResult], most: int = 3) -> Content:
    """What your own keys said, once each: nothing when there's nothing clear to say."""
    said = list(dict.fromkeys(diagnose(r.keys, r.count, r.task.ref) for r in results
                              if r.status == "solved" and r.task.phase != "learn"))
    said = [text for text in said if text][:most]
    if not said:
        return Content("")
    return Content.from_markup("[dim]Your keys[/]\n" + "\n".join(f"[$accent]$s{i}[/]" for i in range(len(said))),
                               **{f"s{i}": text for i, text in enumerate(said)})


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
            advice = your_keys(self.results)
            if advice:
                yield Static(advice, id="results-advice")
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
        times = sorted(r.seconds for r in recall if r.status == "solved" and r.seconds is not None)
        typical = f" · {times[len(times) // 2]:.1f}s a task" if times else ""  # the median
        self.query_one("#results-summary", Static).update(
            f"{solved} of {len(recall)} {verb}" + (f" · {beat} beat the reference" if beat else "") + typical)

        budgets = any(r.budget for r in results)
        table = Table(box=None, show_header=True, header_style="dim", expand=True, padding=(0, 1, 0, 0), pad_edge=False)
        table.add_column("", width=1, no_wrap=True)
        table.add_column("task", ratio=3, no_wrap=True, overflow="ellipsis")
        table.add_column("you typed", ratio=2, no_wrap=True, overflow="ellipsis")
        table.add_column("budget" if budgets else "ref", justify="right", no_wrap=True)
        table.add_column("time", justify="right", no_wrap=True)

        def rows(title: str, round_results: list[TaskResult]) -> None:
            if title:
                table.add_row("", Text(title, style="dim bold"), "", "", "")
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
                seconds = tint(self.app, f"{r.seconds:.1f}s", "text-muted") if r.seconds is not None and r.status != "unseen" else ""
                table.add_row(tint(self.app, mark, colour), Text(goal), keys, count, seconds)

        if two_rounds:
            learn = [r for r in results if r.task.phase == "learn"]
            rows("Recall", recall)
            table.add_row("", "", "", "", "")
            rows(f"Learn · {sum(r.status == 'solved' for r in learn)}/{len(learn)} typed with the keys shown", learn)
        else:
            rows("", results)
        legend = Text(("n/ref: your keys and the reference solution's; fewer and you beat it" if not budgets
                       else "n/budget: your keys and the most allowed at that level")
                      + "\ntime: from the task appearing to it ending; just for you, nothing is graded on it", style="dim")
        self.query_one("#results-list", Static).update(Group(table, Text(""), legend))
        panel.focus()

    def action_scroll(self, lines: int) -> None:
        self.query_one("#results-panel", VerticalScroll).scroll_relative(y=lines)

    def action_again(self) -> None:
        self.dismiss(True)

    def action_done(self) -> None:
        self.dismiss(False)
