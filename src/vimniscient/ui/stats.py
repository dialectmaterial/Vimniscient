"""The stats screen: progress tables."""

from datetime import date
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Static

from vimniscient import drills, habits
from vimniscient.ui.common import keybar, plural, streak_text, tint

if TYPE_CHECKING:
    from vimniscient.app import VimniscientApp


class StatsView(VerticalScroll):
    """Progress tables; `refresh_stats` rebuilds them."""

    def compose(self) -> ComposeResult:
        yield Static(id="overview")
        yield Static("Keystrokes · solved tasks · efficiency = reference keys ÷ your keys", classes="section-label")
        yield DataTable(id="keys-table")
        yield Static("Speed · tasks solved from memory, first tries against your latest", classes="section-label")
        yield DataTable(id="speed-table")
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

        table = self.table("speed-table", "Lesson", "Timed", "First tries", "Lately", "Before the first key")
        speed = progress.speed_by_lesson()
        for lesson in lessons:
            if lesson.id not in speed:
                continue
            n, first, latest, thinking = speed[lesson.id]
            change = tint(app, f"{latest:.1f}s", "success" if latest < first else "text-muted")
            table.add_row(Text(f"{lesson.label} · {lesson.title}"), str(n), f"{first:.1f}s", change,
                          f"{thinking:.1f}s" if thinking is not None else "")

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
