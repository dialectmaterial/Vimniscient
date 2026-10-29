"""The live Omarchy drill screen."""

import asyncio
import time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from vimniscient import drills
from vimniscient.cards import Deck
from vimniscient.ui.common import keybar, progress_bar

if TYPE_CHECKING:
    from vimniscient.app import VimniscientApp


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
