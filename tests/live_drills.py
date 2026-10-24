"""Run every drill against the live desktop, with hyprctl standing in for the
keys. Opens the drill window, switches workspace briefly, then cleans up.

    uv run python tests/live_drills.py
"""

import asyncio
import subprocess
import sys

from vimniscient.drills import DrillRun, Hyprland, load_drills


def dispatch(lua: str) -> None:
    subprocess.run(["hyprctl", "dispatch", lua], capture_output=True, timeout=5)


def actions(drill_id: str, addr: str, run: DrillRun) -> list:
    w = f'window = "address:0x{addr}"'
    home, away = run.home, run.away
    terminal: list[subprocess.Popen] = []

    def open_terminal():
        terminal.append(subprocess.Popen(["foot", "--app-id", "vimniscient-test", "sh", "-c", "sleep 30"]))

    def close_terminal():
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True).stdout
        import json

        for c in json.loads(out):
            if c["class"] == "vimniscient-test":
                dispatch(f'hl.dsp.window.close({{ window = "address:{c["address"]}" }})')

    focus = lambda: dispatch(f"hl.dsp.focus({{ {w} }})")  # noqa: E731
    return {
        "focus": [lambda: dispatch('hl.dsp.focus({ direction = "l" })'), focus],
        "float": [lambda: dispatch(f'hl.dsp.window.float({{ {w}, action = "toggle" }})')] * 2,
        "fullscreen": [focus] + [lambda: dispatch(f'hl.dsp.window.fullscreen({{ {w}, mode = "fullscreen" }})')] * 2,
        "full-width": [focus] + [lambda: dispatch(f'hl.dsp.window.fullscreen({{ {w}, mode = "maximized" }})')] * 2,
        # SUPER + O runs Omarchy's pop script on the focused window (float + pin)
        "pop": [focus] + [lambda: subprocess.run(["omarchy-hyprland-window-pop"], capture_output=True)] * 2,
        "workspace-visit": [
            lambda: dispatch(f'hl.dsp.focus({{ workspace = "{away}" }})'),
            lambda: dispatch(f'hl.dsp.focus({{ workspace = "{home}" }})'),
        ],
        "workspace-move": [
            lambda: dispatch(f'hl.dsp.window.move({{ {w}, workspace = "{away}", follow = false }})'),
            lambda: dispatch(f'hl.dsp.focus({{ workspace = "{away}" }})'),
            lambda: dispatch(f'hl.dsp.window.move({{ {w}, workspace = "{home}" }})'),
        ],
        "terminal": [open_terminal, close_terminal],
        "close": [lambda: dispatch(f"hl.dsp.window.close({{ {w} }})")],
    }[drill_id]


async def main() -> int:
    hypr = Hyprland()
    if not hypr.available:
        print("no Hyprland session")
        return 1
    home = hypr.home()
    failed = 0
    for drill in load_drills():
        addr = hypr.ensure_drill_window()
        run = DrillRun(drill, addr, home)
        events = hypr.events()
        reader = asyncio.ensure_future(events.__anext__())
        await asyncio.sleep(0.3)
        for act in actions(drill.id, addr, run):
            act()
            await asyncio.sleep(0.6)
        deadline = asyncio.get_running_loop().time() + 3
        while not run.finished and asyncio.get_running_loop().time() < deadline:
            done, _ = await asyncio.wait({reader}, timeout=0.2)
            if done:
                run.feed(reader.result())
                reader = asyncio.ensure_future(events.__anext__())
        # drain whatever is left
        while not run.finished:
            done, _ = await asyncio.wait({reader}, timeout=0.3)
            if not done:
                break
            run.feed(reader.result())
            reader = asyncio.ensure_future(events.__anext__())
        reader.cancel()
        status = "ok" if run.finished else f"FAIL (stuck at step {run.step + 1}: {drill.steps[run.step].event})"
        failed += not run.finished
        print(f"{drill.id:16} {status}")
    hypr.close_drill_window()
    dispatch(f'hl.dsp.focus({{ workspace = "{home}" }})')
    return 1 if failed else 0


sys.exit(asyncio.run(main()))
