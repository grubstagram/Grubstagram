"""Turn the day's slides into a 9:16 Reel with a music track baked in.

Instagram's API can't attach tracks from Instagram's own music library, so the audio has to be
inside the video file before upload. We use our own (AI-generated or royalty-free) track instead.
"""
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from . import ROOT

W, H = 1080, 1920
SLIDE_H = 1350


def music_for(kind: str, cfg: dict, theme: dict | None = None) -> Path | None:
    rcfg = cfg.get("reel", {})
    if not rcfg.get("enabled", False):
        return None
    rel = (theme or {}).get(f"{kind}_music") or rcfg.get(f"{kind}_music", "")
    if not rel:
        return None
    path = ROOT / rel
    return path if path.exists() else None


def _frame(slide: Path, hero: Path, out: Path) -> Path:
    """Centre the 4:5 slide on a blurred, darkened copy of the hero photo."""
    bg = Image.open(hero).convert("RGB")
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(45))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    bg.paste(Image.open(slide).convert("RGB").resize((W, SLIDE_H)), (0, (H - SLIDE_H) // 2))
    bg.save(out, "JPEG", quality=92)
    return out


def _probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def manual_song(kind: str, cfg: dict) -> str | None:
    """Song you add yourself in the Instagram app (licensed via Instagram's music library)."""
    rcfg = cfg.get("reel", {})
    if not rcfg.get("enabled", False):
        return None
    return rcfg.get(f"{kind}_manual_song") or None


def render(slides: list[Path], hero: Path, music: Path | None, out_dir: Path, cfg: dict, log=print) -> tuple[Path, Path]:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed")
    rcfg = cfg.get("reel", {})
    fps = 30
    fade = float(rcfg.get("crossfade_seconds", 0.5))
    first = float(rcfg.get("hero_seconds", 3.5))
    middle = float(rcfg.get("slide_seconds", 5.0))
    last = float(rcfg.get("end_seconds", 3.0))

    frames = [_frame(s, hero, out_dir / f"reel_frame_{i}.jpg") for i, s in enumerate(slides, 1)]
    durations = [first] + [middle] * (len(frames) - 2) + [last]
    total = sum(durations) - fade * (len(frames) - 1)

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for f, d in zip(frames, durations):
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{d:.3f}", "-i", str(f)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]

    parts = []
    # Slow push-in on the hero shot (upscaled first so the zoom doesn't judder).
    n0 = int(first * fps)
    parts.append(f"[0:v]scale={W*2}:{H*2},zoompan=z='1+0.07*on/{n0}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                 f":d=1:s={W}x{H}:fps={fps},trim=duration={first:.3f},setsar=1,format=yuv420p[v0]")
    for i in range(1, len(frames)):
        parts.append(f"[{i}:v]scale={W}:{H},setsar=1,fps={fps},format=yuv420p[v{i}]")
    prev, offset = "v0", 0.0
    for i in range(1, len(frames)):
        offset += durations[i - 1] - fade
        label = f"x{i}"
        parts.append(f"[{prev}][v{i}]xfade=transition=fade:duration={fade}:offset={offset:.3f}[{label}]")
        prev = label
    a = len(frames)
    if music:
        parts.append(f"[{a}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.3,"
                     f"afade=t=out:st={max(0, total - 1.8):.3f}:d=1.8,aresample=48000[aout]")

    video = out_dir / "reel.mp4"
    audio = ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"] if music else ["-an"]
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{prev}]",
            "-t", f"{total:.3f}", "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", str(rcfg.get("crf", 24)), "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.1", "-g", str(fps * 2), "-bf", "2",
            *audio,
            "-movflags", "+faststart", "-use_editlist", "0", str(video)]
    subprocess.run(cmd, check=True)

    cover = out_dir / "cover.jpg"
    shutil.copy(frames[0], cover)
    for f in frames:
        f.unlink()
    log(f"  reel: {_probe_seconds(video):.1f}s, {video.stat().st_size / 1e6:.1f} MB, "
        f"{'music ' + music.name if music else 'silent (music added in the app)'}")
    return video, cover
