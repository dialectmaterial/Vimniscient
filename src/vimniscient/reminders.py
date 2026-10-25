"""Daily practice reminders through Omarchy's own reminder system.

The first reminder comes when you start using the computer (at login, or on the
first unlock after 07:00), with what's left today and about how long it takes.
While something is left, another comes every few hours until the evening, and
each one works out again what's left. Once everything is done, nothing comes.

The follow-ups are Omarchy reminders (`omarchy-reminder-*` timers with a
message file), so they show in the bar's reminder indicator and in `omarchy
reminder show`, and `omarchy reminder clear` cancels them. Unlike a plain
Omarchy reminder, each one runs `vimniscient remind` when it fires, which only
notifies if there's still something to do.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from datetime import time as clock
from pathlib import Path

from vimniscient import today

DAY_START = clock(6, 0)  # no reminders before this
DAY_END = clock(21, 30)  # nor after this
EVERY = 180  # minutes between reminders while something is left
MIN_GAP = 30  # don't bother with a last reminder sooner than this before DAY_END
LOGIN_QUIET = 60  # a login or unlock right after a reminder doesn't send another
MORNING = "07:00"

GLYPH = ""  # the Vim logo in Nerd Fonts
UNIT_TAG = "vimniscient"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
REMINDER_DIR = RUNTIME / "omarchy-reminders"  # where omarchy-reminder keeps its messages
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "vimniscient"
LAST_SENT = STATE / "last-reminder"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
SYSTEMD_DIR = CONFIG / "systemd" / "user"
HOOK = CONFIG / "omarchy" / "hooks" / "post-boot.d" / "vimniscient-reminder"


def command(*args: str) -> list[str]:
    """This Vimniscient, run the same way from systemd or a hook."""
    return [sys.executable, "-m", "vimniscient", *args]


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)


# what's left


def current_plan() -> list[today.Step]:
    from vimniscient import drills
    from vimniscient.cards import has_lazyvim, load_decks
    from vimniscient.lessons import load_lessons
    from vimniscient.progress import Progress

    lessons = [lesson for lesson in load_lessons() if not lesson.lazyvim or has_lazyvim()]
    return today.plan(Progress(), lessons, load_decks(), drills.load_drills())


def summary(left: list[today.Step]) -> tuple[str, str]:
    """(headline, body) for a notification about what's left."""
    total = sum(step.minutes for step in left)
    lines = [f"{step.label} · {step.detail} · ~{step.minutes} min" for step in left]
    return f"Vimniscient · about {total} min left today", "\n".join(lines)


# Omarchy reminders that are ours


def pending() -> list[tuple[str, datetime]]:
    """(timer unit, when) for the reminders still waiting, soonest first."""
    out = run("systemctl", "--user", "list-timers", "--all", "--output=json", f"omarchy-reminder-*{UNIT_TAG}*.timer").stdout
    now = time.time()
    found = []
    for timer in json.loads(out or "[]"):
        nxt = (timer.get("next") or 0) / 1_000_000
        if nxt > now:
            found.append((timer["unit"], datetime.fromtimestamp(nxt)))
    return sorted(found, key=lambda t: t[1])


def cancel() -> None:
    for unit, _ in pending():
        run("systemctl", "--user", "stop", unit)
        (REMINDER_DIR / f"{unit.removesuffix('.timer')}.message").unlink(missing_ok=True)
    refresh_indicator()


def refresh_indicator() -> None:
    if shutil.which("omarchy-shell"):
        run("omarchy-shell", "-q", "omarchy.indicators", "refresh")


def schedule(at: datetime, left_minutes: int) -> None:
    """One Omarchy reminder at `at` that checks again when it fires."""
    minutes = max(1, round((at - datetime.now()).total_seconds() / 60))
    unit = f"omarchy-reminder-{minutes}m-{UNIT_TAG}-{int(time.time())}"
    REMINDER_DIR.mkdir(parents=True, exist_ok=True)
    # the label the bar and `omarchy reminder show` use
    (REMINDER_DIR / f"{unit}.message").write_text(f"Vimniscient: about {left_minutes} min of practice left")
    run("systemd-run", "--user", "--quiet", "--collect", f"--on-active={minutes}m", f"--unit={unit}",
        *command("remind", "--check"))
    refresh_indicator()


def notify(left: list[today.Step]) -> None:
    headline, body = summary(left)
    run("omarchy-notification-send", "-g", GLYPH, "-u", "normal", headline, body,
        "--exec", "omarchy-launch-or-focus-tui", "vimniscient")
    STATE.mkdir(parents=True, exist_ok=True)
    LAST_SENT.write_text(datetime.now().isoformat(timespec="seconds"))


def sent_recently(minutes: int) -> bool:
    try:
        last = datetime.fromisoformat(LAST_SENT.read_text().strip())
    except (OSError, ValueError):
        return False
    return datetime.now() - last < timedelta(minutes=minutes)


def locked() -> bool:
    return run("pgrep", "-x", "hyprlock").returncode == 0


def wait_for_unlock(limit: float = 6 * 3600) -> None:
    """A reminder on the lock screen gets missed: hold it until the screen is unlocked."""
    waited = 0.0
    while locked() and waited < limit:
        time.sleep(20)
        waited += 20


def next_time(now: datetime) -> datetime | None:
    end = datetime.combine(now.date(), DAY_END)
    at = min(now + timedelta(minutes=EVERY), end)
    return at if at - now >= timedelta(minutes=MIN_GAP) else None


# entry points


def remind(trigger: str) -> str:
    """`trigger` is "login" (desktop start or the morning timer) or "check" (a
    follow-up firing). Returns what it did, for the command line."""
    wait_for_unlock()
    now = datetime.now()
    if not DAY_START <= now.time() <= DAY_END:
        return "outside the reminder hours"
    left = today.left(current_plan())
    if not left:
        cancel()
        return "everything done today: no reminder"
    if trigger == "login" and sent_recently(LOGIN_QUIET) and pending():
        return "reminded a moment ago; the next one is already set"
    notify(left)
    cancel()  # one follow-up at a time
    at = next_time(now)
    if at:
        schedule(at, sum(step.minutes for step in left))
        return f"reminded; next check at {at:%H:%M}"
    return "reminded; that was the last one today"


def sync(plan: list[today.Step]) -> None:
    """After practising: when nothing's left, the waiting reminders go."""
    if not today.left(plan) and pending():
        cancel()


def install() -> list[str]:
    """The morning timer (fires on resume too, if it was asleep at 07:00) and a post-boot hook."""
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    exec_line = " ".join(command("remind", "--login"))
    (SYSTEMD_DIR / "vimniscient-reminder.service").write_text(
        "[Unit]\nDescription=Vimniscient: remind me of today's practice\n\n"
        f"[Service]\nType=oneshot\nExecStart={exec_line}\n"
    )
    (SYSTEMD_DIR / "vimniscient-reminder.timer").write_text(
        "[Unit]\nDescription=Vimniscient: the morning reminder\n\n"
        f"[Timer]\nOnCalendar=*-*-* {MORNING}:00\nPersistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "--now", "vimniscient-reminder.timer")
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    # in the background: it waits for the first unlock, and boot shouldn't wait for it
    HOOK.write_text(f"#!/bin/bash\n# Vimniscient: remind me of today's practice\nsetsid {exec_line} >/dev/null 2>&1 &\n")
    HOOK.chmod(0o755)
    return [str(SYSTEMD_DIR / "vimniscient-reminder.timer"), str(SYSTEMD_DIR / "vimniscient-reminder.service"), str(HOOK)]


def uninstall() -> None:
    run("systemctl", "--user", "disable", "--now", "vimniscient-reminder.timer")
    for path in (SYSTEMD_DIR / "vimniscient-reminder.timer", SYSTEMD_DIR / "vimniscient-reminder.service", HOOK):
        path.unlink(missing_ok=True)
    run("systemctl", "--user", "daemon-reload")
    cancel()


def status() -> str:
    left = today.left(current_plan())
    lines = []
    if left:
        headline, body = summary(left)
        lines += [headline, body]
    else:
        lines.append("Everything done today.")
    waiting = pending()
    lines.append("Next reminder: " + (f"{waiting[0][1]:%H:%M}" if waiting else "none set"))
    enabled = run("systemctl", "--user", "is-enabled", "vimniscient-reminder.timer").stdout.strip()
    lines.append(f"Morning reminder ({MORNING}, or when you start): {'on' if enabled == 'enabled' else 'off'}")
    return "\n".join(lines)
