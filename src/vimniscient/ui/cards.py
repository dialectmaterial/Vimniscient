"""The card screen: type the keys for each prompt."""


from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.screen import Screen
from textual.widgets import Input, Static

from vimniscient.card_session import CardSession
from vimniscient.cards import Card, Deck
from vimniscient.mnemonics import hooks
from vimniscient.ui.common import HOOK_DECKS, keybar, progress_bar

if TYPE_CHECKING:
    from vimniscient.app import VimniscientApp


class CardScreen(Screen):
    """Type the keys for each prompt. Dismisses with (correct, answered)."""

    BINDINGS = [
        Binding("escape", "finish", "Stop"),
        Binding("enter", "next", "Next", show=False),
        Binding("o", "override", "I was right", show=False),
    ]

    def __init__(self, cards: list[Card], decks: dict[str, Deck], title: str) -> None:
        super().__init__()
        self.cards = cards
        self.decks = decks
        self.title_text = title

    def compose(self) -> ComposeResult:
        with Vertical(id="card-panel", classes="pane column"):
            yield Static(id="card-bar")
            yield Static(id="card-prompt", classes="prompt")
            yield Input(id="card-input")
            yield Static(id="card-feedback")
        yield Static(id="card-help", classes="keybar")

    def on_mount(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        self.session = CardSession(app.progress, self.cards)
        self.show_card()

    def show_card(self) -> None:
        session = self.session
        card = session.begin()
        if card is None:
            self.dismiss((session.correct, session.answered))
            return
        panel = self.query_one("#card-panel")
        panel.border_title = f"{self.title_text} · {self.decks[card.deck].title}"
        again = "new · " if session.intro else "again · " if card.id in session.retried else ""
        panel.border_subtitle = again + f"{min(session.done + 1, session.total)}/{session.total}"
        self.query_one("#card-bar", Static).update(progress_bar(session.done, session.total))
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
        self.query_one("#card-feedback", Static).update(self.introduction(card) if session.intro else "")
        self.query_one("#card-help", Static).update(keybar(("enter", "check"), ("esc", "stop")))

    def introduction(self, card: Card, again: bool = False) -> Content:
        """A new card's answer, to type once; it's asked from memory next time."""
        why = "\n".join(hooks(card.answers[0])) if card.deck in HOOK_DECKS else ""
        lead = "[$error]✗[/]  type it as shown:" if again else "[$accent]new[/]  type it once:"
        note = "\n[dim]$note[/]" if card.note else ""
        return Content.from_markup(f"{lead} [b]$shown[/]{note}" + ("\n[dim]$why[/]" if why else ""),
                                   shown=card.shown, note=card.note, why=why)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        session = self.session
        if session.pending or not session.queue:
            return
        if not session.submit(event.value):  # copying it out: try again
            event.input.value = ""
            self.query_one("#card-feedback", Static).update(self.introduction(session.card, again=True))
            return
        event.input.disabled = True
        self.set_focus(None)
        self.show_feedback()

    def show_feedback(self) -> None:
        card, correct, _ = self.session.pending  # type: ignore[misc]
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

    def action_next(self) -> None:
        if self.session.pending:
            self.session.settle()
            self.show_card()

    def action_override(self) -> None:
        pending = self.session.pending
        if pending and not pending[1]:
            self.session.override()
            self.show_feedback()

    def action_finish(self) -> None:
        self.session.settle()
        self.dismiss((self.session.correct, self.session.answered))
