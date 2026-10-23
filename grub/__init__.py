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


def _in_window(date: _dt.date, start: str, end: str) -> bool:
    """start/end are 'MM-DD' (every year, may wrap past New Year) or 'YYYY-MM-DD' (that year only)."""
    if len(start) == 10:
        return start <= date.isoformat() <= end
    md = date.strftime("%m-%d")
    return start <= md <= end if start <= end else (md >= start or md <= end)


def active_theme(date: _dt.date, cfg: dict) -> dict | None:
    """First festival in [[themes]] whose window contains the date."""
    for t in cfg.get("themes", []):
        if _in_window(date, t["start"], t["end"]):
            return t
    return None


def week_theme(date: _dt.date, cfg: dict) -> dict | None:
    """Outside festivals, weeks alternate: a country special, then a story-and-film week."""
    w = cfg.get("weekly", {})
    countries = w.get("countries", [])
    if not countries:
        return None
    anchor = _dt.date.fromisoformat(w.get("first_country_week", "2026-11-09"))
    week = (date - anchor).days // 7             # Monday-to-Sunday weeks counted from the anchor
    if week % 2:
        return None                              # story week: the normal inspiration list
    country = countries[(week // 2) % len(countries)]
    tag = "#" + "".join(ch for ch in country.lower() if ch.isalnum()) + "food"
    return {
        "name": f"{country} week",
        "emoji": "🌍",
        "hashtags": [tag, "#worldfood"],
        "edible_inspiration": [w["edible"].format(country=country)],
        "not_edible_inspiration": [w["not_edible"].format(country=country)],
        "extra_check": w.get("check", ""),
    }


def course_for(date: _dt.date, kind: str, cfg: dict, history: list[dict]) -> str:
    """Count this Monday-to-Sunday week's earlier posts of the same kind; the configured slots are desserts.
    Defaults: the 1st and 3rd edible posts (alternate days give 3 or 4 a week, so always 2 desserts) and the
    1st gross post (at least one revolting dessert a week)."""
    sched = cfg.get("schedule", {})
    slots = sched.get("dessert_slots", [0, 2]) if kind == "edible" else sched.get("gross_dessert_slots", [0])
    monday = date - _dt.timedelta(days=date.weekday())
    n = sum(1 for h in history
            if h.get("kind") == kind and not h.get("dry_run")
            and monday.isoformat() <= h.get("date", "") < date.isoformat())
    return "dessert" if n in slots else "savoury"


def theme_for(date: _dt.date, cfg: dict) -> dict | None:
    return active_theme(date, cfg) or week_theme(date, cfg)


def forced_kind(date: _dt.date, cfg: dict) -> str | None:
    theme = active_theme(date, cfg)
    if not theme:
        return None
    if theme.get("edible_only"):
        return "edible"
    fk = theme.get("force_kind", {})
    return fk.get(date.isoformat()) or fk.get(date.strftime("%m-%d"))


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
