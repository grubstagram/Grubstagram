"""Hero photo: generated on fal.ai, then cropped to Instagram's 4:5 portrait size."""
import io
import random
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter

from . import env

W, H = 1080, 1350


def fit_4x5(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    target = W / H
    w, h = img.size
    if w / h > target:            # too wide: trim the sides
        nw = int(h * target)
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:                         # too tall: trim top and bottom
        nh = int(w / target)
        img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return img.resize((W, H), Image.LANCZOS)


def generate(prompt: str, kind: str, cfg: dict, out: Path, log=print) -> Path:
    icfg = cfg["image"]
    full_prompt = f"{prompt.strip()}\n\nStyle: {icfg['style'][kind]}"
    body = {"prompt": full_prompt, **icfg.get("params", {})}
    log(f"  image: calling {icfg['model']}")
    resp = httpx.post(f"https://fal.run/{icfg['model']}",
                      headers={"Authorization": f"Key {env('FAL_KEY')}"}, json=body, timeout=300)
    if resp.status_code >= 400:
        raise RuntimeError(f"fal.ai {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    url = (data.get("images") or [{}])[0].get("url") or (data.get("image") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai returned no image: {str(data)[:300]}")
    raw = httpx.get(url, timeout=120, follow_redirects=True).content
    fit_4x5(Image.open(io.BytesIO(raw))).save(out, "JPEG", quality=92)
    return out


def placeholder(kind: str, out: Path, seed: int = 0) -> Path:
    """Stand-in hero photo for dry runs: a plate on a table, no API needed."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), (88, 64, 46) if kind == "edible" else (52, 52, 58))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 6):  # wood/linen texture
        shade = rnd.randint(-10, 10)
        base = img.getpixel((0, y))
        d.line([(0, y), (W, y)], fill=tuple(max(0, min(255, c + shade)) for c in base), width=6)
    cx, cy, r = W // 2, int(H * 0.46), 400
    d.ellipse((cx - r + 18, cy - r + 30, cx + r + 18, cy + r + 30), fill=(30, 22, 18))
    img = img.filter(ImageFilter.GaussianBlur(3))
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(238, 233, 224))
    d.ellipse((cx - r + 60, cy - r + 60, cx + r - 60, cy + r - 60), fill=(228, 222, 210))
    palette = ([(196, 74, 38), (230, 170, 60), (110, 140, 60), (150, 40, 30)] if kind == "edible"
               else [(120, 200, 60), (90, 90, 100), (200, 60, 140), (60, 50, 40)])
    for _ in range(26):
        x, y = cx + rnd.randint(-240, 240), cy + rnd.randint(-240, 240)
        s = rnd.randint(40, 120)
        d.ellipse((x - s, y - s // 1.4, x + s, y + s // 1.4), fill=rnd.choice(palette))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    img.save(out, "JPEG", quality=90)
    return out
