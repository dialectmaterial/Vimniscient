"""One run through a queue of cards: what's asked next and how each answer grades.

A card you've never answered from memory is introduced: its answer is shown and
you type it once. A miss comes back at the end, but only the first try counts.
"""

from dataclasses import dataclass, field

from vimniscient import srs
from vimniscient.answer import is_correct
from vimniscient.cards import Card
from vimniscient.progress import Progress


@dataclass
class CardSession:
    progress: Progress
    queue: list[Card]
    total: int = 0
    retried: set[str] = field(default_factory=set)
    pending: tuple[Card, bool, str] | None = None
    intro: bool = False  # the card on screen is new to you
    correct: int = 0
    answered: int = 0

    def __post_init__(self) -> None:
        self.queue = list(self.queue)
        self.total = len(self.queue)

    @property
    def done(self) -> int:
        return self.total - len([c for c in self.queue if c.id not in self.retried])

    @property
    def card(self) -> Card | None:
        return self.queue[0] if self.queue else None

    def begin(self) -> Card | None:
        """The next card, and whether to introduce it."""
        card = self.card
        if card:
            item = self.progress.item(card.id)
            # never answered from memory, and not introduced since the last miss
            self.intro = card.id not in self.retried and not self.progress.ever_right(card.id) and (not item or item.reps == 0)
        return card

    def submit(self, answer: str) -> bool:
        """False when an introduced card was copied wrong, so it's asked again."""
        card = self.queue[0]
        correct = is_correct(answer, card.answers, card.style, card.case_sensitive)
        if self.intro and not correct:
            return False
        self.pending = (card, correct, answer)
        return True

    def override(self) -> None:
        """"I was right": a miss the checker was too strict about."""
        if self.pending and not self.pending[1]:
            self.pending = (self.pending[0], True, self.pending[2])

    def settle(self) -> None:
        """Grade the answered card (only the first try of a session counts)."""
        if not self.pending:
            return
        card, correct, answer = self.pending
        self.pending = None
        self.queue.pop(0)
        if self.intro:  # typed with the answer shown: scheduled for tomorrow, not scored
            self.progress.grade(card.id, "card", srs.GOOD)
            self.progress.log_card(card, True, answer, intro=True)  # still practice, for the streak
            return
        if card.id in self.retried:
            return
        self.answered += 1
        self.correct += correct
        self.progress.log_card(card, correct, answer)
        known = self.progress.item(card.id) is not None
        self.progress.grade(card.id, "card", (srs.GOOD if known else srs.EASY) if correct else srs.AGAIN)
        if not correct:
            self.retried.add(card.id)
            self.queue.append(card)
