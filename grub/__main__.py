"""Command line entry point.

  python -m grub generate [--date YYYY-MM-DD] [--kind edible|not_edible] [--dry-run]
  python -m grub publish  [--date YYYY-MM-DD] [--dry-run]
  python -m grub refresh-token --out FILE
  python -m grub check
"""
import argparse
import datetime as dt
import json
import os
import sys

from . import day_dir, kind_for, load_config, load_history, save_history, env
from . import image as img
from . import recipe as rec
from . import slides


def log(msg: str) -> None:
    print(msg, flush=True)


def media_base() -> str:
    explicit = os.environ.get("MEDIA_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    if repo:
        return f"https://raw.githubusercontent.com/{repo}/{branch}"
    return ""


def cmd_generate(a, cfg) -> None:
    date = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    kind = a.kind or kind_for(date, cfg)
    out = day_dir(date)
    existing = json.loads((out / "recipe.json").read_text()) if (out / "recipe.json").exists() else None
    if existing and not existing.get("dry_run") and not a.force:
        log(f"{out} already has a post. Use --force to regenerate.")
        return
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("slide_*.jpg"):
        old.unlink()
    log(f"Generating {kind} post for {date} -> {out}")

    history = load_history()
    if a.dry_run:
        from .fixtures import SAMPLES
        recipe = SAMPLES[kind]
        img.placeholder(kind, out / "hero.jpg", seed=date.toordinal())
    else:
        recipe = rec.write_recipe(kind, [h["title"] for h in history], cfg, log)
        img.generate(recipe["image_prompt"], kind, cfg, out / "hero.jpg", log)

    caption = rec.build_caption(recipe, kind, cfg)
    paths = slides.render_all(out / "hero.jpg", recipe, kind, cfg["brand"]["handle"], out)
    (out / "recipe.json").write_text(json.dumps({"kind": kind, "dry_run": a.dry_run, **recipe}, indent=2, ensure_ascii=False) + "\n")
    (out / "caption.txt").write_text(caption + "\n")

    base = media_base()
    rel = f"queue/{date.isoformat()}"
    pics = " ".join(f'<img src="{base + "/" if base else "../../"}{rel}/{p.name}" width="240">' for p in paths)
    (out / "issue.md").write_text(
        ("> **DRY RUN** with a sample recipe and placeholder photo. This will never be posted.\n\n" if a.dry_run else "")
        + f"**{recipe['title']}** · `{kind}`\n\n{pics}\n\n### Caption\n```\n{caption}\n```\n\n"
        "**Reject:** add the `reject` label before the publish time and it will be skipped.\n"
        "**Approve:** do nothing. It posts automatically.\n"
    )
    history = [h for h in history if h.get("date") != date.isoformat()]
    history.append({"date": date.isoformat(), "kind": kind, "title": recipe["title"], "status": "drafted"})
    save_history(history)
    log(f"Done: {len(paths)} slides, caption {len(caption)} chars.")


def cmd_publish(a, cfg) -> None:
    from .publish import IG
    date = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    out = day_dir(date)
    if not (out / "recipe.json").exists():
        raise SystemExit(f"No draft for {date}. Nothing to publish.")
    if (out / "published.json").exists():
        log(f"{date} is already published: {json.loads((out / 'published.json').read_text()).get('permalink')}")
        return
    recipe = json.loads((out / "recipe.json").read_text())
    if recipe.get("dry_run"):
        log(f"{date} is a dry-run draft (sample recipe, placeholder photo). Not posting it.")
        return
    caption = (out / "caption.txt").read_text().strip()
    slides_ = sorted(out.glob("slide_*.jpg"), key=lambda p: int(p.stem.split("_")[1]))
    base = media_base()
    if not base:
        raise SystemExit("Set MEDIA_BASE_URL (or run inside GitHub Actions) so Instagram can fetch the images.")
    urls = [f"{base}/queue/{date.isoformat()}/{p.name}" for p in slides_]
    log(f"Publishing {date}: {recipe['title']} ({len(urls)} slides)")
    if a.dry_run:
        for u in urls:
            log(f"  would post {u}")
        return
    result = IG(cfg).carousel(urls, caption, recipe.get("alt_text", ""), log)
    (out / "published.json").write_text(json.dumps(result, indent=2) + "\n")
    history = load_history()
    for h in history:
        if h.get("date") == date.isoformat():
            h["status"] = "published"
            h["permalink"] = result.get("permalink")
    save_history(history)
    log(f"Published: {result.get('permalink')}")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"permalink={result.get('permalink', '')}\n")


def cmd_refresh(a, cfg) -> None:
    from .publish import refresh_token
    token = refresh_token(cfg)
    with open(a.out, "w") as f:
        f.write(token)
    log("Token refreshed and written to file (not printed).")


def cmd_check(a, cfg) -> None:
    ok = True
    for name in ("ANTHROPIC_API_KEY", "FAL_KEY", "IG_ACCESS_TOKEN"):
        present = bool(env(name, required=False))
        ok &= present
        log(f"  {name}: {'set' if present else 'MISSING'}")
    if env("IG_ACCESS_TOKEN", required=False):
        from .publish import IG
        ig = IG(cfg)
        me = ig._req("GET", ig.user, fields="user_id,username,account_type")
        log(f"  Instagram: @{me.get('username')} ({me.get('account_type')}), id {me.get('user_id')}")
        log(f"  Publishing limit: {ig.limit()}")
    log(f"  Media base URL: {media_base() or '(not set)'}")
    sys.exit(0 if ok else 1)


def main() -> None:
    p = argparse.ArgumentParser(prog="grub")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--date")
    g.add_argument("--kind", choices=["edible", "not_edible"])
    g.add_argument("--dry-run", action="store_true", help="use sample recipe + placeholder photo, no API calls")
    g.add_argument("--force", action="store_true")
    pb = sub.add_parser("publish")
    pb.add_argument("--date")
    pb.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("refresh-token")
    r.add_argument("--out", required=True)
    sub.add_parser("check")
    a = p.parse_args()
    cfg = load_config()
    {"generate": cmd_generate, "publish": cmd_publish, "refresh-token": cmd_refresh, "check": cmd_check}[a.cmd](a, cfg)


if __name__ == "__main__":
    main()
