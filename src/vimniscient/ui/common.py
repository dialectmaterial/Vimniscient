"""Pieces every screen uses: themes, status labels, help texts, key bars, small text helpers."""

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import App
from textual.theme import Theme

from vimniscient.lessons import Lesson

if TYPE_CHECKING:
    pass


LOGO = """\
█ █ █ █▀▄▀█ █▄ █ █ ▄▀▀ ▄▀▀ █ ██▀ █▄ █ ▀█▀
▀▄▀ █ █ ▀ █ █ ▀█ █ ▄██ ▀▄▄ █ █▄▄ █ ▀█  █ """

# decks whose answers are Vim keys, so mnemonics.hooks() can say what they stand for
HOOK_DECKS = {"vim", "lazyvim", "habits"}

# Result labels and the theme colour each is shown in.
STATUS = {
    "solved": ("solved", "success"),
    "failed": ("missed", "error"),
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

TASK_HELP = (
    "The goal shows in the top window, your text below. When they match, the next task loads by "
    "itself. Inside Neovim: `:Hint` (twice for the answer), `:Skip`, `:Reset`, `:q` to stop."
)
VIMGOLF_HELP = (
    "The goal shows in the top window, your text below; it's done when they match. Inside Neovim: "
    "`:Reset` to start over, `:q` to stop."
)
RETRY_HELP = "Skip a task you can't recall and you'll see the answer, type it once, and get it again at the end."
ROUNDS_HELP = (
    "Two rounds. **Learn**: each task with the keys to type shown. **Recall**: the same skills on "
    "new text, in another order, from memory. Only Recall counts towards your progress."
)


def plural(n: int, word: str, many: str = "") -> str:
    return f"{n} {word if n == 1 else many or word + 's'}"


def streak_text(days: int) -> str:
    return f"[b]{days}-day[/] streak" if days else "no streak yet"


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


def code_span(text: str) -> str:
    """`text` as Markdown code, even when it has backticks in it (`` `a ``)."""
    if "`" not in text:
        return f"`{text}`"
    fence = "`" * (max(len(run) for run in re.findall("`+", text)) + 1)
    return f"{fence} {text} {fence}"


def lesson_markdown(lesson: Lesson, best: dict[int, int] | None = None) -> str:
    keys = f"**New keys** {'  '.join(code_span(k) for k in lesson.keys)}\n\n" if lesson.keys else ""
    tasks = ""
    if best is not None:
        rows = []
        for i, task in enumerate(lesson.tasks):
            mark = f"✓ {best[i]} keys" if i in best else "·"
            rows.append(f"- {task.goal} *({mark}, ref {task.ref})*" if i in best else f"- {task.goal}")
        tasks = f"**{len(best)}/{len(lesson.tasks)} recalled**\n\n" + "\n".join(rows)
    return f"{lesson.intro}\n\n{keys}{tasks}"


def progress_bar(done: int, total: int, width: int = 40) -> str:
    filled = round(width * done / total) if total else 0
    return f"[$primary]{'━' * filled}[/][$panel]{'━' * (width - filled)}[/]"


def keybar(*pairs: tuple[str, str]) -> str:
    """One line of key hints, lazygit-style: the key in mauve, what it does after it."""
    return "  ".join(f"[bold $primary]{key}[/] {what}" for key, what in pairs)
