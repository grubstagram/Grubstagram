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


def active_theme(date: _dt.date, cfg: dict) -> dict | None:
    """First [[themes]] entry whose MM-DD window contains the date (windows may wrap past New Year)."""
    md = date.strftime("%m-%d")
    for t in cfg.get("themes", []):
        start, end = t["start"], t["end"]
        inside = start <= md <= end if start <= end else (md >= start or md <= end)
        if inside:
            return t
    return None


def forced_kind(date: _dt.date, cfg: dict) -> str | None:
    theme = active_theme(date, cfg)
    return (theme or {}).get("force_kind", {}).get(date.strftime("%m-%d"))


def kind_for(date: _dt.date, cfg: dict, history: list[dict] | None = None) -> str:
    """Forced theme days win. Otherwise continue the pattern from the posts so far, skipping forced
    days, so a themed day doesn't knock the alternation out of step (no three gross posts in a row)."""
    forced = forced_kind(date, cfg)
    if forced:
        return forced
    pattern = cfg["schedule"]["pattern"]
    if history:
        n = sum(1 for h in history
                if h.get("date", "") < date.isoformat() and not h.get("forced") and not h.get("dry_run"))
        return pattern[n % len(pattern)]
    return pattern[date.toordinal() % len(pattern)]


def load_history() -> list[dict]:
    if HISTORY.exists():
        return json.loads(HISTORY.read_text())
    return []


def save_history(items: list[dict]) -> None:
    HISTORY.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")


def day_dir(date: _dt.date) -> Path:
    return QUEUE / date.isoformat()
