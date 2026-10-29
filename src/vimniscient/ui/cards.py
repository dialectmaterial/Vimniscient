"""The card screen: type the keys for each prompt."""


from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.screen import Screen
from textual.widgets import Input, Static

from vimniscient import srs
from vimniscient.answer import is_correct
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
            app.progress.log_card(card, True, answer, intro=True)  # still practice, for the streak
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
