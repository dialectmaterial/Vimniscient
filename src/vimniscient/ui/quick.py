"""Quick practice: pick a skill and a length. Dismisses with (skill, minutes), or None."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from vimniscient import quick
from vimniscient.ui.common import keybar, plural


class QuickScreen(Screen):
    BINDINGS = [
        Binding("1", "start(1)", "1 minute", show=False, priority=True),
        Binding("2", "start(2)", "2 minutes", show=False, priority=True),
        Binding("5", "start(5)", "5 minutes", show=False, priority=True),
        Binding("enter", "start(2)", "Start", show=False, priority=True),
        Binding("l", "start(2)", "Start", show=False),
        Binding("j", "move(1)", "Down", show=False),
        Binding("k", "move(-1)", "Up", show=False),
        Binding("escape", "back", "Back"),
        Binding("h", "back", "Back", show=False),
        Binding("q", "back", "Back", show=False),
    ]

    def __init__(self, counts: dict[str, int], mission: str = "") -> None:
        """`counts`: tasks each skill can draw on. `mission`: the one to offer, if any."""
        super().__init__()
        self.counts = counts
        self.mission = mission

    def compose(self) -> ComposeResult:
        options = [Option(f"{quick.title(quick.NAVIGATION):<14} [dim]count, find, delete the #[/]", id=quick.NAVIGATION)]
        options += [Option(f"{quick.title(skill):<14} [dim]{plural(n, 'task')}[/]", id=skill) for skill, n in self.counts.items()]
        if self.mission:
            options.append(Option(f"{'Mission':<14} [dim]{self.mission}, across real files[/]", id="mission"))
        yield OptionList(*options, id="quick-list", classes="pane column")
        yield Static(keybar(("1", "minute"), ("2", "minutes"), ("5", "minutes"), ("⏎", "2 minutes"), ("esc", "back")), classes="keybar")

    def on_mount(self) -> None:
        skills = self.query_one("#quick-list", OptionList)
        skills.border_title = "Quick practice"
        skills.highlighted = 0
        skills.focus()

    def action_move(self, step: int) -> None:
        skills = self.query_one("#quick-list", OptionList)
        skills.action_cursor_down() if step > 0 else skills.action_cursor_up()

    def action_start(self, minutes: int) -> None:
        skills = self.query_one("#quick-list", OptionList)
        self.dismiss((skills.get_option_at_index(skills.highlighted).id, minutes))

    def action_back(self) -> None:
        self.dismiss(None)
