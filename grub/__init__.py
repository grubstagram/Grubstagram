"""Grubstagram: one AI recipe a day, edible or (gloriously) not."""
import datetime as _dt
import json
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue"
HISTORY = ROOT / "data" / "history.json"
FONTS = ROOT / "fonts"


def load_config() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        return tomllib.load(f)


def env(name: str, required: bool = True) -> str | None:
    val = os.environ.get(name, "").strip()
    if required and not val:
        raise SystemExit(f"Missing environment variable {name}. Set it as a GitHub secret (or export it locally).")
    return val or None


def kind_for(date: _dt.date, cfg: dict) -> str:
    pattern = cfg["schedule"]["pattern"]
    return pattern[date.toordinal() % len(pattern)]


def load_history() -> list[dict]:
    if HISTORY.exists():
        return json.loads(HISTORY.read_text())
    return []


def save_history(items: list[dict]) -> None:
    HISTORY.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")


def day_dir(date: _dt.date) -> Path:
    return QUEUE / date.isoformat()
