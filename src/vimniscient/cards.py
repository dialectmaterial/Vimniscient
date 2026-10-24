"""Flashcards: static decks from `cards/*.yaml` plus decks read live from the
user's setup (Omarchy, tmux and LazyVim keybindings)."""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from vimniscient.answer import pretty_keys

NVIM_DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "nvim"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "vimniscient"
NVIM_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "nvim"

# New cards are introduced round-robin in this order.
DECK_ORDER = ["habits", "vim", "lazyvim", "omarchy", "tmux", "shell", "foot", "zathura"]


@dataclass
class Card:
    deck: str
    id: str
    prompt: str
    answers: list[str]
    style: str  # keys | combo
    case_sensitive: bool
    week: int = 0
    note: str = ""
    order: int = 0  # position within the deck for introducing new cards

    @property
    def shown(self) -> str:
        return pretty_keys(self.answers[0])

    @property
    def also(self) -> list[str]:
        return [pretty_keys(a) for a in self.answers[1:]]


@dataclass
class Deck:
    id: str
    title: str
    cards: list[Card] = field(default_factory=list)


def has_lazyvim() -> bool:
    """LazyVim installed through lazy.nvim (its lessons and cards need it)."""
    return (NVIM_DATA / "lazy" / "LazyVim").is_dir()


def _static_decks() -> dict[str, Deck]:
    decks = {}
    for f in (resources.files("vimniscient") / "cards").iterdir():
        if not f.name.endswith(".yaml"):
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        # a deck about a program only shows up when that program is installed
        if data.get("requires") == "lazyvim" and not has_lazyvim():
            continue
        if data.get("requires") not in (None, "lazyvim") and not shutil.which(data["requires"]):
            continue
        deck = Deck(data["deck"], data["title"])
        for i, c in enumerate(data["cards"]):
            deck.cards.append(
                Card(
                    deck=deck.id,
                    id=f"{deck.id}:{c['prompt']}",
                    prompt=c["prompt"],
                    answers=[str(a) for a in c["answer"]],
                    style=data.get("style", "keys"),
                    case_sensitive=data.get("case_sensitive", True),
                    week=c.get("week", 0),
                    note=c.get("note", data.get("note", "")),
                    order=i,
                )
            )
        decks[deck.id] = deck
    return decks


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _arrow_list(deck_id: str, text: str, case_sensitive: bool) -> list[Card]:
    """Cards from `KEYS → description` lines (the Omarchy keybinding menus)."""
    by_desc: dict[str, list[str]] = {}
    for line in text.splitlines():
        if "→" not in line:
            continue
        keys, desc = (s.strip() for s in line.split("→", 1))
        if not keys or not desc or re.search(r"MOUSE|SCROLL|SWITCH:|XF86", keys, re.I):
            continue
        by_desc.setdefault(desc, []).append(keys)
    cards = []
    for i, (desc, keys) in enumerate(by_desc.items()):
        # "Switch to workspace 1..10" is one thing to learn: keep the 1.
        m = re.fullmatch(r"(.*\D)(\d+)", desc)
        if m and m.group(2) != "1" and f"{m.group(1)}1" in by_desc:
            continue
        if keys == ["PREFIX"]:  # tmux: "PREFIX → CTRL + SPACE / CTRL + B"
            desc, keys = "The tmux prefix", [k.strip() for k in desc.split("/")]
        cards.append(
            Card(deck_id, f"{deck_id}:{desc}", desc, keys, "combo", case_sensitive, order=i)
        )
    return cards


def omarchy_cards() -> list[Card]:
    return _arrow_list("omarchy", _run(["omarchy", "menu", "keybindings", "--print"]), False)


def tmux_cards() -> list[Card]:
    return _arrow_list("tmux", _run(["omarchy-menu-tmux-keybindings", "--print"]), True)


def _nvim_signature() -> str:
    newest = 0.0
    for root, _, files in os.walk(NVIM_CONFIG):
        for name in files:
            newest = max(newest, os.path.getmtime(os.path.join(root, name)))
    return str(newest)


def nvim_keymaps() -> list[dict]:
    """Every described keymap in the user's Neovim, cached until the config changes."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / "nvim-keymaps.json"
    signature = _nvim_signature()
    if cache.exists():
        data = json.loads(cache.read_text())
        if data.get("signature") == signature:
            return data["maps"]
    out = CACHE_DIR / "nvim-keymaps.tmp.json"
    script = resources.files("vimniscient") / "nvim" / "keymaps.lua"
    with resources.as_file(script) as script_path:
        try:
            subprocess.run(
                ["nvim", "--headless", "-i", "NONE", "-n", "-S", str(script_path)],
                env=os.environ | {"VIMNISCIENT_KEYMAPS": str(out)},
                capture_output=True,
                timeout=60,
                cwd=CACHE_DIR,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
    if not out.exists():
        return []
    maps = json.loads(out.read_text())
    out.unlink()
    cache.write_text(json.dumps({"signature": signature, "maps": maps}))
    return maps


def lazyvim_extra_cards(core: list[Card]) -> list[Card]:
    """The `from_config` keymaps of cards/lazyvim.yaml, as named in the user's config."""
    data = yaml.safe_load((resources.files("vimniscient") / "cards" / "lazyvim.yaml").read_text(encoding="utf-8"))
    wanted = [pretty_keys(k) for k in data.get("from_config", [])]
    known = {a for card in core for a in card.answers}
    by_lhs = {
        pretty_keys(m["lhs"]): m["desc"]
        for m in nvim_keymaps()
        if m["mode"] == "n" and not m["desc"].startswith("+")
    }
    start = len(core)
    return [
        Card("lazyvim", f"lazyvim:{by_lhs[lhs]}", by_lhs[lhs], [lhs], "keys", True, order=start + i)
        for i, lhs in enumerate(lhs for lhs in wanted if lhs in by_lhs and lhs not in known)
    ]


def load_decks(live: bool = True) -> dict[str, Deck]:
    decks = _static_decks()
    if live:
        for deck in (Deck("omarchy", "Omarchy", omarchy_cards()), Deck("tmux", "tmux", tmux_cards())):
            if deck.cards:
                decks[deck.id] = deck
        if "lazyvim" in decks:
            decks["lazyvim"].cards += lazyvim_extra_cards(decks["lazyvim"].cards)
        from vimniscient.habits import habit_deck

        decks["habits"] = habit_deck()
    return {d: decks[d] for d in DECK_ORDER if d in decks} | {d: v for d, v in decks.items() if d not in DECK_ORDER}
