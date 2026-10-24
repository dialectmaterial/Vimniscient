"""Live Omarchy drills, checked against Hyprland's event socket (socket2).

The matching (`DrillRun.feed`) is plain and testable; `Hyprland` holds the
parts that touch the desktop: the drill window and the sockets.
"""

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from importlib import resources

import yaml

DRILL_CLASS = "vimniscient-drill"
DRILL_TITLE = "Vimniscient drill"


@dataclass
class Step:
    event: str
    args: list[str]
    done: str
    active: str | None = None


@dataclass
class Drill:
    id: str
    title: str
    prompt: str
    bindings: list[str]
    steps: list[Step]

    @property
    def item_id(self) -> str:
        return f"drill:{self.id}"


def load_drills() -> list[Drill]:
    data = yaml.safe_load((resources.files("vimniscient") / "drills" / "omarchy.yaml").read_text(encoding="utf-8"))
    return [
        Drill(
            id=d["id"],
            title=d["title"],
            prompt=d["prompt"],
            bindings=d.get("bindings", []),
            steps=[Step(s["event"], [str(a) for a in s["args"]], s["done"], s.get("active")) for s in d["steps"]],
        )
        for d in data["drills"]
    ]


@dataclass
class DrillRun:
    """Walks one drill's steps as events come in."""

    drill: Drill
    drill_addr: str  # without 0x, as the events write it
    home: str  # workspace id
    step: int = 0
    active: str = ""  # address of the focused window
    new: str | None = None
    started: float = field(default_factory=time.monotonic)

    @property
    def away(self) -> str:
        return "8" if self.home == "9" else "9"

    def text(self, template: str) -> str:
        return template.replace("{home}", self.home).replace("{away}", self.away)

    @property
    def finished(self) -> bool:
        return self.step >= len(self.drill.steps)

    def _arg_ok(self, pattern: str, value: str) -> bool:
        if pattern == "*":
            return True
        if pattern == "$drill":
            return value == self.drill_addr
        if pattern == "$home":
            return value == self.home
        if pattern == "$away":
            return value == self.away
        if pattern == "!drill":
            return bool(value) and value != self.drill_addr
        if pattern == "$new":
            if self.new is None:
                if value and value != self.drill_addr:
                    self.new = value
                    return True
                return False
            return value == self.new
        return value == pattern

    def feed(self, line: str) -> Step | None:
        """Take one `event>>data` line; returns the step it completed, if any."""
        name, _, data = line.partition(">>")
        if name == "activewindowv2":
            self.active = data.removeprefix("0x")
        if self.finished:
            return None
        step = self.drill.steps[self.step]
        if name != step.event:
            return None
        args = data.split(",", len(step.args) - 1) if step.args else []
        if len(args) != len(step.args):
            return None
        if step.active == "$drill" and self.active != self.drill_addr:
            return None
        new_before = self.new
        if not all(self._arg_ok(p, v) for p, v in zip(step.args, args)):
            self.new = new_before
            return None
        self.step += 1
        return step


def grade(seconds: float, hinted: bool, skipped: bool) -> int:
    from vimniscient import srs

    if skipped:
        return srs.AGAIN
    if hinted:
        return srs.HARD
    return srs.EASY if seconds <= 10 else srs.GOOD if seconds <= 30 else srs.HARD


class Hyprland:
    """The live desktop: the drill window and the event stream."""

    def __init__(self) -> None:
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        self.socket2 = os.path.join(runtime, "hypr", sig, ".socket2.sock") if sig else ""
        self.drill_window: subprocess.Popen | None = None

    @property
    def available(self) -> bool:
        return bool(self.socket2) and os.path.exists(self.socket2)

    def _json(self, what: str):
        out = subprocess.run(["hyprctl", what, "-j"], capture_output=True, text=True, timeout=5).stdout
        return json.loads(out or "null")

    def home(self) -> str:
        return str(self._json("activeworkspace")["id"])

    def drill_address(self) -> str | None:
        for client in self._json("clients") or []:
            if client.get("class") == DRILL_CLASS:
                return client["address"].removeprefix("0x")
        return None

    def ensure_drill_window(self) -> str | None:
        """Open the drill window if it isn't there; returns its address."""
        addr = self.drill_address()
        if addr:
            return addr
        text = "This is the drill window.\\nThe drills happen to it, so your own windows are left alone."
        self.drill_window = subprocess.Popen(
            [
                "xdg-terminal-exec", f"--app-id={DRILL_CLASS}", f"--title={DRILL_TITLE}",
                "-e", "sh", "-c", f'printf "\\n  {text}\\n"; exec sleep 86400',
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            time.sleep(0.1)
            addr = self.drill_address()
            if addr:
                return addr
        return None

    def close_drill_window(self) -> None:
        addr = self.drill_address()
        if addr:
            subprocess.run(
                ["hyprctl", "dispatch", f'hl.dsp.window.close({{ window = "address:0x{addr}" }})'],
                capture_output=True,
                timeout=5,
            )
        if self.drill_window and self.drill_window.poll() is None:
            self.drill_window.terminate()

    async def events(self):
        """Yield `event>>data` lines from socket2 forever."""
        reader, writer = await asyncio.open_unix_connection(self.socket2)
        try:
            while line := await reader.readline():
                yield line.decode(errors="replace").rstrip("\n")
        finally:
            writer.close()
