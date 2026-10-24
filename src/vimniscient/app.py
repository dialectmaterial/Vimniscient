"""The Textual menu around the lessons and cards."""

from collections.abc import Callable
from datetime import date

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from vimniscient import habits, srs, vimgolf
from vimniscient.answer import is_correct
from vimniscient.cards import Card, Deck, load_decks
from vimniscient.lessons import Lesson, Task, load_lessons
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


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


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
        hint=f"No hints in VimGolf. Solutions show on {challenge.url} once you submit one.",
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
        f"keystrokes as you can. {best_text}\n\nThis runs in your own LazyVim, so your count can differ "
        "a little from the official one (VimGolf uses plain Vim). To submit for real: install `vim`, "
        f"run `vimgolf setup` once, then `vimgolf put {challenge.id}`.",
        keys=[],
        tasks=[task],
    )


def placement_lesson(lessons: list[Lesson]) -> Lesson:
    """The first and last task of every lesson except the weekly reviews."""
    tasks = [t for lesson in lessons if lesson.day != 7 for t in (lesson.tasks[0], lesson.tasks[-1])]
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


class HomeScreen(Screen):
    BINDINGS = [
        Binding("t", "app.today", "Today"),
        Binding("c", "app.cards", "Cards"),
        Binding("g", "app.vimgolf", "VimGolf"),
        Binding("p", "app.placement", "Placement"),
        Binding("s", "app.stats", "Stats"),
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
        self.query_one("#stats", Static).update(
            f"streak [b]{plural(progress.streak(), 'day')}[/] · [b]{done}/{len(lessons)}[/] lessons · hardtime: {hardtime}"
        )

        due, new = progress.due_cards(app.decks, lessons), progress.new_cards(app.decks, lessons)
        review = progress.due_tasks(lessons)
        nxt = progress.next_lesson(lessons)
        parts = []
        if due or new:
            parts.append(f"{len(due)} due + {len(new)} new cards")
        if review:
            parts.append(plural(len(review), "review task"))
        parts.append(f"{nxt.label}: {nxt.title}" if nxt else "all lessons done")
        if not progress.vimgolf_done_today():
            parts.append("VimGolf")
        today = "[b]Today:[/] " + " → ".join(parts) + "  [dim](press t)[/]"
        top = next((h for h in habits.habits() if h.recent), None)
        if top:
            today += f"\n[dim]Top habit (hardtime): {top.message} ({top.recent}× in two weeks)[/]"
        if not progress.days_trained():
            today += "\n[dim]New here? Press p for a placement test that skips the lessons you already know.[/]"
        self.query_one("#today", Static).update(today)

        options: list[Option] = []
        week = None
        for lesson in lessons:
            if lesson.week != week:
                week = lesson.week
                options.append(Option(f"[b]Week {week}[/]", disabled=True))
            best = progress.best(lesson)
            if len(best) == len(lesson.tasks):
                mark = "[green]✓[/]"
            elif progress.is_placed(lesson):
                mark = "[green]○[/]"
            else:
                mark = f"[dim]{len(best)}/{len(lesson.tasks)}[/]"
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
        app: VimniscientApp = self.app  # type: ignore[assignment]
        app.push_screen(LessonScreen(app.lesson(event.option.id)))

    def action_move(self, step: int) -> None:
        lessons_list = self.query_one("#lessons", OptionList)
        if step > 0:
            lessons_list.action_cursor_down()
        else:
            lessons_list.action_cursor_up()

    def action_open(self) -> None:
        self.query_one("#lessons", OptionList).action_select()


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
        heading = f"{lesson.label}: {lesson.title}" if lesson.week else lesson.title
        keys = f"**New keys:** {'  '.join(f'`{k}`' for k in lesson.keys)}\n\n" if lesson.keys else ""
        yield VerticalScroll(
            Markdown(
                f"# {heading}\n\n{lesson.intro}\n\n{keys}"
                f"{plural(len(lesson.tasks), 'task')}. The goal shows in the top window, your text below. "
                "When they match, the next task loads by itself. Inside Neovim: "
                "`:Hint` (twice for the answer), `:Skip`, `:Reset`, `:q` to stop.\n\n"
                "**Press Enter to start.**"
            )
        )
        yield Footer()

    def action_back(self) -> None:
        self.dismiss(None)

    def action_start(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        with app.suspend():
            results = run_lesson(self.lesson)
        if self.on_results:
            note = self.on_results(results)
        else:
            app.progress.record(results)
            note = ""
        app.push_screen(
            ResultsScreen(self.lesson, results, note),
            lambda again: None if again else self.dismiss(results),
        )


class ResultsScreen(Screen):
    """Dismisses with True to run the lesson again, False to move on."""

    BINDINGS = [
        Binding("r", "again", "Again"),
        Binding("escape", "done", "Done"),
        Binding("enter", "done", "Done", show=False),
        Binding("q", "done", "Done", show=False),
    ]

    def __init__(self, lesson: Lesson, results: list[TaskResult], note: str = "") -> None:
        super().__init__()
        self.lesson = lesson
        self.results = results
        self.note = note

    def compose(self) -> ComposeResult:
        solved = sum(r.status == "solved" for r in self.results)
        title = f"{self.lesson.label}: {self.lesson.title}" if self.lesson.week else self.lesson.title
        yield Static(f"[b]{title}[/]  {solved}/{len(self.results)} solved", id="summary")
        if self.note:
            yield Static(self.note, id="note")
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
        yield Static(id="card-head")
        yield Static(id="card-prompt")
        yield Input(id="card-input")
        yield Static(id="card-feedback")
        yield Footer()

    def on_mount(self) -> None:
        self.show_card()

    def show_card(self) -> None:
        if not self.queue:
            self.dismiss((self.correct, self.answered))
            return
        card = self.queue[0]
        done = self.total - len([c for c in self.queue if c.id not in self.retried])
        again = "  [yellow](again)[/]" if card.id in self.retried else ""
        self.query_one("#card-head", Static).update(
            f"[dim]{self.title_text} · {min(done + 1, self.total)}/{self.total} · {self.decks[card.deck].title}[/]{again}"
        )
        self.query_one("#card-prompt", Static).update(f"[b]{card.prompt}[/]")
        box = self.query_one("#card-input", Input)
        box.value = ""
        box.disabled = False
        box.placeholder = (
            "modifiers + key, like CTRL SHIFT + X   (Enter to check)"
            if card.style == "combo"
            else "the keys as typed: <C-x> for Ctrl-x, <leader> for Space   (Enter to check)"
        )
        box.focus()
        self.query_one("#card-feedback", Static).update("")

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
        also = f"  [dim](also: {', '.join(card.also)})[/]" if card.also else ""
        note = f"\n[dim]{card.note}[/]" if card.note else ""
        if correct:
            text = f"[green]✓[/] [b]{card.shown}[/]{also}{note}\n\n[dim]Enter: next[/]"
        else:
            text = f"[red]✗[/] answer: [b]{card.shown}[/]{also}{note}\n\n[dim]Enter: next · o: I was right[/]"
        self.query_one("#card-feedback", Static).update(text)

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


class StatsScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back"), Binding("q", "app.pop_screen", "Back", show=False)]

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Static(id="overview"),
            Static("[b]Keystrokes[/] [dim](solved tasks; efficiency = reference keys ÷ your keys)[/]", classes="heading"),
            DataTable(id="keys-table", zebra_stripes=True),
            Static("[b]Cards[/]", classes="heading"),
            DataTable(id="decks-table", zebra_stripes=True),
            DataTable(id="accuracy-table", zebra_stripes=True),
            Static("[b]Trouble spots[/] [dim](forgotten most often)[/]", classes="heading"),
            DataTable(id="trouble-table", zebra_stripes=True),
            Static("[b]Habits[/] [dim](what hardtime.nvim caught you doing)[/]", classes="heading"),
            DataTable(id="habits-table", zebra_stripes=True),
            Static("[b]VimGolf[/] [dim](your score includes ZZ, like on vimgolf.com)[/]", classes="heading"),
            DataTable(id="vimgolf-table", zebra_stripes=True),
        )
        yield Footer()

    def on_mount(self) -> None:
        app: VimniscientApp = self.app  # type: ignore[assignment]
        progress, lessons, decks = app.progress, app.lessons, app.decks
        today = date.today()

        done = sum(progress.is_done(lesson) for lesson in lessons)
        placed = sum(progress.is_placed(lesson) for lesson in lessons)
        tasks_total = sum(len(lesson.tasks) for lesson in lessons)
        tasks_solved = sum(len(progress.best(lesson)) for lesson in lessons)
        self.query_one("#overview", Static).update(
            f"streak [b]{plural(progress.streak(), 'day')}[/] · {plural(len(progress.days_trained()), 'day')} trained · "
            f"[b]{done}/{len(lessons)}[/] lessons ({placed} placed) · {tasks_solved}/{tasks_total} tasks solved"
        )

        table = self.query_one("#keys-table", DataTable)
        table.add_columns("Day", "Tasks", "Your keys", "Reference", "Efficiency")
        for day, n, keys, ref in progress.efficiency_by_day():
            table.add_row(day, str(n), str(keys), str(ref), f"{100 * ref / keys:.0f}%" if keys else "")

        items = progress.items("card")
        unlocked = {c.id for c in progress.unlocked(decks, lessons)}
        table = self.query_one("#decks-table", DataTable)
        table.add_columns("Deck", "Cards", "Unlocked", "Seen", "Mature (3+ weeks)", "Due today")
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

        table = self.query_one("#accuracy-table", DataTable)
        table.add_columns("Day", "Cards answered", "Correct")
        for day, n, correct in progress.card_accuracy():
            table.add_row(day, str(n), f"{100 * correct / n:.0f}%")

        cards = {c.id: c for deck in decks.values() for c in deck.cards}
        tasks = {t.item_id: t for lesson in lessons for t in lesson.tasks}
        table = self.query_one("#trouble-table", DataTable)
        table.add_columns("What", "Answer", "Forgotten")
        for item in progress.hardest():
            if item.id in cards:
                table.add_row(cards[item.id].prompt, cards[item.id].shown, str(item.lapses))
            elif item.id in tasks:
                table.add_row(tasks[item.id].goal, tasks[item.id].solution, str(item.lapses))

        table = self.query_one("#habits-table", DataTable)
        table.add_columns("Message", "Last two weeks", "All time", "Last seen")
        for habit in habits.habits()[:10]:
            table.add_row(habit.message, str(habit.recent), str(habit.total), habit.last.isoformat())

        table = self.query_one("#vimgolf-table", DataTable)
        table.add_columns("Day", "Challenge", "Your score", "Best on vimgolf.com")
        for day, title, score, best in progress.vimgolf_history():
            table.add_row(day, title, str(score) if score else "[dim]not solved[/]", str(best) if best else "")


class VimniscientApp(App):
    TITLE = "Vimniscient"
    CSS = """
    #logo { color: $accent; padding: 1 2 0 2; }
    #stats { padding: 0 2; color: $text-muted; }
    #today { padding: 1 2; }
    #lessons { margin: 0 2; height: 1fr; }
    #summary { padding: 1 2; }
    #note { padding: 0 2 1 2; color: $success; }
    #results { margin: 0 2; height: auto; max-height: 1fr; }
    LessonScreen VerticalScroll { padding: 1 2; }
    #card-head { padding: 1 2 0 2; }
    #card-prompt { padding: 1 2; text-style: bold; }
    #card-input { margin: 0 2; }
    #card-feedback { padding: 1 2; }
    StatsScreen VerticalScroll { padding: 1 2; }
    StatsScreen DataTable { height: auto; margin-bottom: 1; }
    .heading { margin-top: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.lessons = load_lessons()
        self.progress = Progress()
        self.decks = load_decks()

    def lesson(self, lesson_id: str) -> Lesson:
        return next(lesson for lesson in self.lessons if lesson.id == lesson_id)

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

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

    def action_today(self) -> None:
        """Cards, then review tasks (plus habit drills), then the next lesson, then VimGolf."""
        progress = self.progress
        cards = progress.due_cards(self.decks, self.lessons) + progress.new_cards(self.decks, self.lessons)
        review = progress.due_tasks(self.lessons)
        review += self.drill_tasks(review)
        nxt = progress.next_lesson(self.lessons)
        steps = []
        if cards:
            steps.append(lambda done: self.push_screen(CardScreen(cards, self.decks, "Today's cards"), lambda _: done()))
        if review:
            steps.append(lambda done: self.push_screen(LessonScreen(review_lesson(review)), lambda _: done()))
        if nxt:
            steps.append(lambda done: self.push_screen(LessonScreen(nxt), lambda _: done()))
        if not progress.vimgolf_done_today():
            steps.append(lambda done: self.start_vimgolf(done))
        if not steps:
            self.notify("Nothing due and every lesson done. Pick any lesson to practise.")
        self.run_steps(steps)

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
                return f"Not solved. It stays today's challenge. Try again with g. ({challenge.url})"
            best = f", best on vimgolf.com {challenge.best}" if challenge.best else ""
            return f"Your VimGolf score: {score} (keys + ZZ){best}. Solutions: {challenge.url}"

        self.call_from_thread(
            self.push_screen, LessonScreen(vimgolf_lesson(challenge), on_results), lambda _: done()
        )

    def action_stats(self) -> None:
        self.push_screen(StatsScreen())
