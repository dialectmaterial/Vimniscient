"""Your settings, in ~/.config/vimniscient/config.yaml. Only one so far:

    minutes: 15   # how long today's routine is meant to take

`vimniscient minutes 20` sets it.
"""

import os
from pathlib import Path

import yaml

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vimniscient" / "config.yaml"
DEFAULT_MINUTES = 15


def _read() -> dict:
    try:
        data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def minutes() -> int:
    value = _read().get("minutes", DEFAULT_MINUTES)
    return value if isinstance(value, int) and value > 0 else DEFAULT_MINUTES


def set_minutes(value: int) -> None:
    data = _read() | {"minutes": value}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
