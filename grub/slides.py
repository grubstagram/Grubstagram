"""Render the carousel (hero, ingredients, method, call-to-action) as 1080x1350 JPEGs with Pillow.

Pure Pillow on purpose: no headless browser, so it runs anywhere in seconds.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import FONTS

W, H = 1080, 1350
M = 84  # side margin

THEMES = {
    "edible": dict(
        bg=(244, 237, 225), ink=(40, 31, 25), muted=(124, 108, 94), accent=(196, 66, 38),
        accent2=(92, 110, 50), rule=(214, 202, 186), title="serif",
        badge="EDIBLE", badge_bg=(92, 110, 50), badge_fg=(250, 246, 238),
    ),
    "not_edible": dict(
        bg=(17, 17, 17), ink=(236, 236, 226), muted=(150, 150, 140), accent=(208, 255, 52),
        accent2=(255, 56, 106), rule=(60, 60, 60), title="sans",
        badge="NOT FOOD", badge_bg=(255, 56, 106), badge_fg=(17, 17, 17),
    ),
}

_cache: dict = {}


def font(style: str, size: int) -> ImageFont.FreeTypeFont:
    key = (style, size)
    if key in _cache:
        return _cache[key]
    if style in ("serif", "serif-italic"):
        f = ImageFont.truetype(str(FONTS / ("Lora-Variable.ttf" if style == "serif" else "Lora-Italic-Variable.ttf")), size)
        try:
            f.set_variation_by_axes([700 if style == "serif" else 500])
        except Exception:
            pass
    else:
        f = ImageFont.truetype(str(FONTS / {"bold": "Poppins-Bold.ttf", "medium": "Poppins-Medium.ttf",
                                            "regular": "Poppins-Regular.ttf", "light": "Poppins-Light.ttf",
                                            "sans": "Poppins-Bold.ttf"}[style]), size)
    _cache[key] = f
    return f


def wrap(text: str, f, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if f.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def line_h(f, mult=1.18) -> int:
    a, d = f.getmetrics()
    return int((a + d) * mult)


def tracked(d: ImageDraw.ImageDraw, xy, text: str, f, fill, spacing=4):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + spacing
    return x


def hazard(d: ImageDraw.ImageDraw, box, a=(208, 255, 52), b=(17, 17, 17), band=34):
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=b)
    h = y1 - y0
    x = x0 - h
    while x < x1:
        d.polygon([(x, y1), (x + band, y1), (x + band + h, y0), (x + h, y0)], fill=a)
        x += band * 2


def title_text(recipe: dict, kind: str) -> str:
    return recipe["title"].upper() if kind == "not_edible" else recipe["title"]


def fit_title(text: str, style: str, width: int, start: int, stop: int, max_lines: int):
    for size in range(start, stop - 1, -4):
        f = font(style, size)
        lines = wrap(text, f, width)
        if len(lines) <= max_lines:
            return f, lines
    f = font(style, stop)
    return f, wrap(text, f, width)


def footer(d, t, handle: str, page: int, total: int, y=H - 70):
    f = font("medium", 24)
    d.text((M, y), handle, font=f, fill=t["muted"])
    label = f"{page}/{total}"
    d.text((W - M - f.getlength(label), y), label, font=f, fill=t["muted"])


def badge(d, t, xy):
    f = font("bold", 32)
    x, y = xy
    text_w = sum(f.getlength(c) + 4 for c in t["badge"]) - 4
    d.rounded_rectangle((x, y, x + text_w + 56, y + 64), radius=32, fill=t["badge_bg"])
    tracked(d, (x + 28, y + 11), t["badge"], f, t["badge_fg"])


# ---------------------------------------------------------------- slides

def slide_hero(hero: Path, recipe: dict, kind: str, handle: str, swipe: bool = True) -> Image.Image:
    t = THEMES[kind]
    img = Image.open(hero).convert("RGB").resize((W, H))
    shade = Image.new("L", (1, H))
    for y in range(H):
        p = max(0.0, (y - H * 0.42) / (H * 0.58))
        shade.putpixel((0, y), int(235 * min(1.0, p ** 1.25)))
    dark = Image.new("RGB", (W, H), (12, 10, 8))
    img = Image.composite(dark, img, shade.resize((W, H)))
    d = ImageDraw.Draw(img)
    if kind == "not_edible":
        hazard(d, (0, 0, W, 26))
    badge(d, t, (M - 20, 64))

    style = "serif" if t["title"] == "serif" else "bold"
    tf, tlines = fit_title(title_text(recipe, kind), style, W - 2 * M, 104, 64, 3)
    sf = font("serif-italic" if kind == "edible" else "regular", 38)
    slines = wrap(recipe["tagline"], sf, W - 2 * M)[:2]
    y = H - 120 - len(slines) * line_h(sf) - 26 - len(tlines) * line_h(tf, 1.05)
    for ln in tlines:
        d.text((M, y), ln, font=tf, fill=(255, 255, 255) if kind == "edible" else t["accent"])
        y += line_h(tf, 1.05)
    y += 26
    for ln in slines:
        d.text((M, y), ln, font=sf, fill=(232, 226, 216))
        y += line_h(sf)
    f = font("medium", 24)
    d.text((M, H - 70), handle, font=f, fill=(200, 194, 184))
    if swipe:
        hint = "SWIPE  >"
        tracked(d, (W - M - sum(f.getlength(c) + 3 for c in hint), H - 70), hint, f, (200, 194, 184), 3)
    return img


def _header(d, t, kicker: str, recipe: dict, kind: str, meta: bool = True) -> int:
    y = 96
    tracked(d, (M, y), kicker, font("bold", 26), t["accent2"] if kind == "edible" else t["accent2"], 5)
    y += 56
    style = "serif" if t["title"] == "serif" else "bold"
    tf, lines = fit_title(title_text(recipe, kind), style, W - 2 * M, 66, 46, 2)
    for ln in lines:
        d.text((M, y), ln, font=tf, fill=t["ink"] if kind == "edible" else t["accent"])
        y += line_h(tf, 1.08)
    if meta:
        y += 10
        mf = font("regular", 30)
        for ln in wrap(f"{recipe['servings']}  ·  {recipe['time']}", mf, W - 2 * M)[:2]:
            d.text((M, y), ln, font=mf, fill=t["muted"])
            y += line_h(mf, 1.1)
        y += 8
    y += 18
    d.line((M, y, W - M, y), fill=t["rule"], width=3)
    return y + 40


def slide_ingredients(recipe: dict, kind: str, handle: str, page: int, total: int) -> Image.Image:
    t = THEMES[kind]
    img = Image.new("RGB", (W, H), t["bg"])
    d = ImageDraw.Draw(img)
    if kind == "not_edible":
        hazard(d, (0, H - 26, W, H))
    kicker = "INGREDIENTS" if kind == "edible" else "INGREDIENTS  /  DO NOT GATHER"
    top = _header(d, t, kicker, recipe, kind)
    bottom = H - 130 - (56 if kind == "edible" and recipe.get("allergens") else 0)
    qty_w = 250
    for size in range(40, 23, -2):
        qf, itf = font("bold", size), font("regular", size)
        rows = [(r["qty"], wrap(r["item"], itf, W - 2 * M - qty_w)) for r in recipe["ingredients"]]
        gap = int(size * 0.75)
        need = sum(len(lines) * line_h(itf) + gap for _, lines in rows)
        if top + need <= bottom:
            break
    y = top
    for qty, lines in rows:
        qlines = wrap(qty, qf, qty_w - 24)
        for i, ql in enumerate(qlines[:2]):
            d.text((M, y + i * line_h(qf)), ql, font=qf, fill=t["accent"])
        for i, ln in enumerate(lines):
            d.text((M + qty_w, y + i * line_h(itf)), ln, font=itf, fill=t["ink"])
        y += max(len(lines), min(2, len(qlines))) * line_h(itf) + gap
    if kind == "edible" and recipe.get("allergens"):
        af = font("medium", 24)
        d.text((M, H - 160), "Contains: " + ", ".join(recipe["allergens"]), font=af, fill=t["muted"])
    footer(d, t, handle, page, total, H - 70 if kind == "edible" else H - 84)
    return img


def _layout_steps(steps, size):
    nf, sf = font("bold", size), font("regular", size)
    text_w = W - 2 * M - 92
    return nf, sf, [wrap(s, sf, text_w) for s in steps], int(size * 1.0)


def slides_method(recipe: dict, kind: str, handle: str, first_page: int, total_hint: int) -> list[Image.Image]:
    """One slide if it fits at a readable size, otherwise split across two."""
    t = THEMES[kind]
    steps = recipe["steps"]
    kicker = "METHOD" if kind == "edible" else "METHOD  /  PLEASE DON'T"

    def measure(chunk, top):
        for size in range(38, 27, -2):
            nf, sf, wrapped, gap = _layout_steps(chunk, size)
            need = sum(max(1, len(w)) * line_h(sf) + gap for w in wrapped)
            if top + need <= H - 140:
                return size
        return None

    probe = Image.new("RGB", (W, H))
    top = _header(ImageDraw.Draw(probe), t, kicker, recipe, kind, meta=False)
    chunks = [steps] if measure(steps, top) else [steps[: (len(steps) + 1) // 2], steps[(len(steps) + 1) // 2:]]

    out, n = [], 1
    for ci, chunk in enumerate(chunks):
        img = Image.new("RGB", (W, H), t["bg"])
        d = ImageDraw.Draw(img)
        if kind == "not_edible":
            hazard(d, (0, H - 26, W, H))
        k = kicker if len(chunks) == 1 else f"{kicker}  ({ci + 1}/{len(chunks)})"
        top = _header(d, t, k, recipe, kind, meta=False)
        size = measure(chunk, top) or 28
        nf, sf, wrapped, gap = _layout_steps(chunk, size)
        y = top
        for lines in wrapped:
            r = int(size * 0.85)
            cx, cy = M + r, y + line_h(sf) // 2
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=t["accent"])
            num = str(n)
            nfs = font("bold", int(size * 0.9))
            d.text((cx, cy + 1), num, font=nfs, fill=t["bg"], anchor="mm")
            for i, ln in enumerate(lines):
                d.text((M + 92, y + i * line_h(sf)), ln, font=sf, fill=t["ink"])
            y += max(1, len(lines)) * line_h(sf) + gap
            n += 1
        out.append(img)
    return out


def slide_cta(recipe: dict, kind: str, handle: str, page: int, total: int) -> Image.Image:
    t = THEMES[kind]
    img = Image.new("RGB", (W, H), t["bg"])
    d = ImageDraw.Draw(img)
    cx = W // 2
    if kind == "edible":
        f = font("serif", 96)
        y = 360
        for ln in wrap("Would you make it?", f, W - 2 * M):
            d.text((cx, y), ln, font=f, fill=t["ink"], anchor="ma")
            y += line_h(f, 1.05)
        y += 40
        sf = font("regular", 36)
        for ln in ["Save it for later.", "Send it to whoever's cooking tonight.", "Tell us if it worked."]:
            d.text((cx, y), ln, font=sf, fill=t["muted"], anchor="ma")
            y += line_h(sf)
        box = (M, H - 360, W - M, H - 170)
        d.rounded_rectangle(box, radius=24, outline=t["rule"], width=3)
        nf = font("medium", 27)
        note = "Recipe and photo generated by AI. Not every recipe is test-cooked: use your judgement and check allergens."
        yy = box[1] + 38
        for ln in wrap(note, nf, box[2] - box[0] - 80):
            d.text((cx, yy), ln, font=nf, fill=t["muted"], anchor="ma")
            yy += line_h(nf)
    else:
        hazard(d, (0, 0, W, 90))
        hazard(d, (0, H - 90, W, H))
        f = font("bold", 150)
        y = 300
        for ln in ["DO NOT", "ATTEMPT"]:
            d.text((cx, y), ln, font=f, fill=t["accent"], anchor="ma")
            y += line_h(f, 0.98)
        y += 50
        sf = font("medium", 40)
        d.text((cx, y), "Rate the grossness 1 to 10", font=sf, fill=t["ink"], anchor="ma")
        y += line_h(sf)
        d.text((cx, y), "in the comments.", font=sf, fill=t["ink"], anchor="ma")
        y += line_h(sf) + 60
        nf = font("regular", 28)
        for ln in wrap("This is a joke. It is not food. Nobody eat anything in this post.", nf, W - 2 * M - 80):
            d.text((cx, y), ln, font=nf, fill=t["accent2"], anchor="ma")
            y += line_h(nf)
    fy = H - 70 if kind == "edible" else H - 150
    footer(d, t, handle, page, total, fy)
    return img


def render_all(hero: Path, recipe: dict, kind: str, handle: str, out_dir: Path) -> list[Path]:
    method = slides_method(recipe, kind, handle, 3, 0)
    total = 3 + len(method)
    imgs = [slide_hero(hero, recipe, kind, handle),
            slide_ingredients(recipe, kind, handle, 2, total)]
    # re-render method with correct page numbers
    for i, m in enumerate(method):
        footer(ImageDraw.Draw(m), THEMES[kind], handle, 3 + i, total, H - 70 if kind == "edible" else H - 84)
        imgs.append(m)
    imgs.append(slide_cta(recipe, kind, handle, total, total))
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out_dir / f"slide_{i}.jpg"
        im.save(p, "JPEG", quality=90, optimize=True, progressive=False)
        paths.append(p)
    return paths
