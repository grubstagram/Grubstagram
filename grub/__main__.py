"""Command line entry point.

  python -m grub generate [--date YYYY-MM-DD] [--kind edible|not_edible] [--dry-run]
  python -m grub publish  [--date YYYY-MM-DD] [--dry-run]
  python -m grub refresh-token --out FILE
  python -m grub check
"""
import argparse
import re
import random
import datetime as dt
import json
import os
import sys

from . import course_for, theme_for, day_dir, forced_kind, kind_for, load_config, load_history, save_history, env
from . import image as img
from . import recipe as rec
from . import reel as reels
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


def pick_inspiration(date, kind: str, cfg: dict, theme: dict | None, history: list[dict]) -> str | None:
    """Work through a shuffled list, one per post of this kind, so nothing repeats until the list runs out.
    Themes can bring their own list."""
    pool = list((theme or {}).get(f"{kind}_inspiration") or cfg.get("inspiration", {}).get(kind, []))
    if not pool:
        return None
    random.Random(f"{kind}-{(theme or {}).get('name', '')}").shuffle(pool)
    n = sum(1 for h in history if h.get("kind") == kind and h.get("date", "") < date.isoformat())
    return pool[n % len(pool)]


def upload_media(path) -> str:
    """Host a file on fal's CDN (kept 30 days) so Instagram can fetch it without bloating the repo."""
    import fal_client
    from fal_client.client import StorageSettings
    return fal_client.upload_file(path, lifecycle=StorageSettings(expires_in="30d"))


def cmd_generate(a, cfg) -> None:
    date = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    history = load_history()
    kind = a.kind or kind_for(date, cfg, history)
    theme = theme_for(date, cfg)
    out = day_dir(date)
    existing = json.loads((out / "recipe.json").read_text()) if (out / "recipe.json").exists() else None
    if existing and not existing.get("dry_run") and not a.force:
        log(f"{out} already has a post. Use --force to regenerate.")
        return
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("slide_*.jpg"):
        old.unlink()
    log(f"Generating {kind} post for {date}{' (' + theme['name'] + ' theme)' if theme else ''} -> {out}")

    inspiration = None
    if a.dry_run:
        from .fixtures import SAMPLES
        recipe = SAMPLES[kind]
        img.placeholder(kind, out / "hero.jpg", seed=date.toordinal())
    else:
        inspiration = pick_inspiration(date, kind, cfg, theme, history)
        course = course_for(date, kind, cfg, history)
        if course == "dessert" and kind == "not_edible":
            inspiration = "make it a revolting fake DESSERT (a custard, pie, trifle, jelly or cake that is obviously not food)" + (f", inspired by {inspiration}" if inspiration else "")
        elif course == "dessert":
            inspiration = "make it a DESSERT (a sweet bake, pudding, tart, cake, ice cream or similar)" + (f", inspired by {inspiration}" if inspiration else "")
        elif kind == "edible":
            inspiration = ("make it a savoury dish, not a dessert (if the inspiration below is sweet, find a savoury dish in the same spirit)"
                           + (f", inspired by {inspiration}" if inspiration else ""))
        season = cfg.get("seasonal", {}).get(date.strftime("%m"))
        if kind == "edible" and season:
            inspiration = (inspiration + "; " if inspiration else "") + f"lean on what's in season now in Europe: {season}"
        if inspiration:
            log(f"  inspiration: {inspiration}")
        owner_note = None
        if a.feedback_file:
            owner_note = open(a.feedback_file, encoding="utf-8").read()
            log(f"  redo, owner note: {owner_note.strip()[:120] or '(none)'}")
        recipe = rec.write_recipe(kind, [h["title"] for h in history], cfg, log, theme, inspiration, owner_note)
        labels = cfg["image"].get("hidden_labels", []) if kind == "not_edible" else []
        rng = random.Random(date.toordinal() * 31)
        hidden = rng.choice(labels) if labels and rng.random() < cfg["image"].get("hidden_label_chance", 0.25) else None
        if hidden:
            log(f"  hidden label: {hidden}")
        img.generate(recipe["image_prompt"], kind, cfg, out / "hero.jpg", log, theme, hidden)

    caption = rec.build_caption(recipe, kind, cfg, theme)
    paths = slides.render_all(out / "hero.jpg", recipe, kind, cfg["brand"]["handle"], out)
    for stale in ("reel.mp4", "cover.jpg"):
        (out / stale).unlink(missing_ok=True)
    meta = {"kind": kind, "theme": (theme or {}).get("name"), "dry_run": a.dry_run, "format": "carousel"}
    reel_note = ""
    music = reels.music_for(kind, cfg, theme)
    song = None if music else reels.manual_song(kind, cfg)
    if music or song:
        try:
            reel_slides = list(paths)
            hero_frame = out / "reel_hero.jpg"
            slides.slide_hero(out / "hero.jpg", recipe, kind, cfg["brand"]["handle"], swipe=False).save(hero_frame, "JPEG", quality=92)
            reel_slides[0] = hero_frame
            video, _cover = reels.render(reel_slides, out / "hero.jpg", music, out, cfg, log)
            hero_frame.unlink()
            caption = (caption.replace("Full recipe in the slides 👉", "Pause to read the full recipe ⏸️")
                       .replace("Swipe for the 'method' 👉", "Pause for the 'method', if you dare ⏸️"))
            if music:
                meta.update(format="reel", music=music.name)
            else:
                meta.update(format="manual_reel", song=song)
            if env("FAL_KEY", required=False):
                meta["reel_url"] = upload_media(video)
                if music:
                    reel_note = f"▶️ **[Watch the Reel with music]({meta['reel_url']})** · this posts as a Reel\n\n"
                else:
                    reel_note = (
                        f"## 📲 You post this one (it's a \"{song}\" day)\n"
                        f"1. **[Download the Reel]({meta['reel_url']})** on your phone: open the link, then Share → **Save Video**.\n"
                        "2. Copy the caption below.\n"
                        "3. Instagram (as yummers.grubbers) → ➕ → **Reel** → pick the video → **Add audio** → "
                        f"search **{song}** → choose the catchy part → Next → paste the caption → **Share**.\n"
                        "4. Close this issue when it's live.\n\n"
                        "The bot won't post it, and you'll get a reminder at the usual posting time.\n\n")
            else:
                reel_note = "🎬 Reel rendered locally (no FAL_KEY, so not uploaded).\n\n"
        except Exception as e:  # never lose the day's post over the video: fall back to the carousel
            log(f"  reel failed, falling back to carousel: {e}")
            meta.pop("song", None)
            meta["format"] = "carousel"
            reel_note = f"⚠️ Reel failed ({str(e)[:120]}), so this will post as a carousel.\n\n"
    (out / "recipe.json").write_text(json.dumps({**meta, **recipe}, indent=2, ensure_ascii=False) + "\n")
    (out / "caption.txt").write_text(caption + "\n")

    base = media_base()
    rel = f"queue/{date.isoformat()}"
    pics = reel_note + " ".join(f'<img src="{base + "/" if base else "../../"}{rel}/{p.name}" width="240">' for p in paths)
    (out / "issue.md").write_text(
        ("> **DRY RUN** with a sample recipe and placeholder photo. This will never be posted.\n\n" if a.dry_run else "")
        + f"**{recipe['title']}** · `{kind}`" + (f" · {theme.get('emoji', '🗓️')} {theme['name']} theme" if theme else "") + f"\n\n{pics}\n\n### Caption\n```\n{caption}\n```\n\n"
        "**Reject:** add the `reject` label before the publish time and it will be skipped.\n"
        "**Approve:** do nothing. It posts automatically.\n"
    )
    history = [h for h in history if h.get("date") != date.isoformat()]
    history.append({"date": date.isoformat(), "kind": kind, "title": recipe["title"], "status": "drafted",
                    "inspiration": inspiration,
                    "course": course_for(date, kind, cfg, history) if not a.dry_run else None,
                    "forced": bool(forced_kind(date, cfg)) and not a.kind, "dry_run": a.dry_run})
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
    if recipe.get("format") == "manual_reel":
        log(f"{date} is a post-it-yourself day ({recipe.get('song')}). Not posting; reminding you instead.")
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a") as f:
                f.write("manual=true\n")
        return
    caption = (out / "caption.txt").read_text().strip()
    slides_ = sorted(out.glob("slide_*.jpg"), key=lambda p: int(p.stem.split("_")[1]))
    base = media_base()
    if not base:
        raise SystemExit("Set MEDIA_BASE_URL (or run inside GitHub Actions) so Instagram can fetch the images.")
    urls = [f"{base}/queue/{date.isoformat()}/{p.name}" for p in slides_]
    log(f"Publishing {date}: {recipe['title']} ({recipe.get('format', 'carousel')}, {len(urls)} slides)")
    if a.dry_run:
        for u in urls:
            log(f"  would post {u}")
        return
    if recipe.get("format") == "reel" and recipe.get("reel_url"):
        log(f"  as a Reel: {recipe['reel_url']}")
        cover = f"{base}/queue/{date.isoformat()}/cover.jpg" if (out / "cover.jpg").exists() else ""
        result = IG(cfg).reel(recipe["reel_url"], caption, cover, cfg.get("reel", {}).get("audio_name", ""), log)
    else:
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


def cmd_music(a, cfg) -> None:
    from . import ROOT
    mcfg = cfg["music"]
    folder = ROOT / "brand" / "music"
    cand = folder / "candidates"
    cand.mkdir(parents=True, exist_ok=True)
    if a.use:
        src = cand / f"{a.kind}-{a.use}.mp3"
        if not src.exists():
            raise SystemExit(f"No candidate {src.name}. Generate some first.")
        rel = cfg["reel"].get(f"{a.kind}_music") or f"brand/music/{a.kind}.mp3"
        dest = ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        # Point the config at the track if it wasn't set yet.
        conf = ROOT / "config.toml"
        text = conf.read_text()
        new = re.sub(rf'^{a.kind}_music = ""', f'{a.kind}_music = "{rel}"', text, count=1, flags=re.M)
        if new != text:
            conf.write_text(new)
        log(f"Now using {src.name} as {dest.relative_to(ROOT)}. {a.kind} posts will go out as Reels with it.")
        return
    prompt = a.prompt or mcfg["prompts"][a.kind]
    import httpx
    lines = [f"Music candidates for **{a.kind}** posts, model `{mcfg['model']}`.", "", f"> {prompt}", ""]
    base = media_base()
    for i in range(1, a.count + 1):
        log(f"  generating candidate {i}/{a.count}")
        resp = httpx.post(f"https://fal.run/{mcfg['model']}", headers={"Authorization": f"Key {env('FAL_KEY')}"},
                          json={"prompt": prompt, **mcfg.get("params", {})}, timeout=600)
        if resp.status_code >= 400:
            raise RuntimeError(f"fal.ai {resp.status_code}: {resp.text[:400]}")
        audio = resp.json().get("audio")
        url = audio.get("url") if isinstance(audio, dict) else audio
        if not url:
            raise RuntimeError(f"fal.ai returned no audio: {resp.text[:300]}")
        dest = cand / f"{a.kind}-{i}.mp3"
        dest.write_bytes(httpx.get(url, timeout=120, follow_redirects=True).content)
        link = f"{base}/brand/music/candidates/{dest.name}" if base else dest.name
        lines.append(f"{i}. ▶️ [Listen to candidate {i}]({link})")
    lines += ["", "**To choose one:** run *4. Make music* with `use` set to the number (e.g. `2`), or tell Claude which you liked."]
    (cand / "issue.md").write_text("\n".join(lines) + "\n")
    log("Done.")


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
    g.add_argument("--feedback-file", default="", help="redo after a rejection, with the owner's note in this file")
    pb = sub.add_parser("publish")
    pb.add_argument("--date")
    pb.add_argument("--dry-run", action="store_true")
    m = sub.add_parser("music")
    m.add_argument("--kind", choices=["edible", "not_edible"], default="edible")
    m.add_argument("--prompt", default="")
    m.add_argument("--count", type=int, default=3)
    m.add_argument("--use", default="", help="promote candidate N to the live track")
    r = sub.add_parser("refresh-token")
    r.add_argument("--out", required=True)
    sub.add_parser("check")
    a = p.parse_args()
    cfg = load_config()
    {"generate": cmd_generate, "publish": cmd_publish, "music": cmd_music, "refresh-token": cmd_refresh, "check": cmd_check}[a.cmd](a, cfg)


if __name__ == "__main__":
    main()
