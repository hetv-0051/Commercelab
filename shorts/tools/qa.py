#!/usr/bin/env python3
"""QA for a rendered Short.

Usage:
  python3 shorts/tools/qa.py <project_dir> sheet [draft|final]
      Writes out/contact_sheet.png: one frame every 1 s (and one per shot
      midpoint), numbered with its timestamp. Look at EVERY frame.
  python3 shorts/tools/qa.py <project_dir> check
      Checks the final MP4: 1080x1920, 30 fps, H.264 + AAC, 15-60 s,
      loudness near -14 LUFS, words.json covers the script. Exit 1 on failure.
"""
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def sheet(proj, which):
    out = os.path.join(proj, "out")
    src = os.path.join(out, "draft.mp4" if which == "draft" else "final.mp4")
    rep = json.load(open(os.path.join(out, "render_report.json")))
    dur = rep["duration"]
    times = sorted({round(t, 2) for t in [i + 0.5 for i in range(int(dur))]} |
                   {round((a + b) / 2, 2) for a, b, _ in rep["shots"]})
    tw, th = 270, 480
    cols = 8
    rows = (len(times) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * (th + 34)), (30, 30, 30))
    f = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", 24)
    tmp = os.path.join(out, "_f.png")
    for i, t in enumerate(times):
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", src, "-frames:v", "1",
             "-vf", f"scale={tw}:{th}", tmp])
        im = Image.open(tmp).convert("RGB")
        x, y = (i % cols) * tw, (i // cols) * (th + 34)
        canvas.paste(im, (x, y + 34))
        ImageDraw.Draw(canvas).text((x + 8, y + 4), f"{t:.1f}s", font=f, fill=(255, 255, 0))
    os.remove(tmp)
    path = os.path.join(out, "contact_sheet.png")
    canvas.save(path)
    print(path, f"({len(times)} frames)")


def check(proj):
    out = os.path.join(proj, "out")
    final = os.path.join(out, "final.mp4")
    errs = []
    p = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", final]).stdout)
    v = [s for s in p["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in p["streams"] if s["codec_type"] == "audio"]
    dur = float(p["format"]["duration"])
    if (v["width"], v["height"]) != (1080, 1920):
        errs.append(f"resolution {v['width']}x{v['height']}")
    if v["codec_name"] != "h264":
        errs.append("video codec " + v["codec_name"])
    if eval(v["r_frame_rate"]) != 30:
        errs.append("fps " + v["r_frame_rate"])
    if not a:
        errs.append("no audio stream")
    if not 15 <= dur <= 60:
        errs.append(f"duration {dur:.1f}s outside 15-60s")
    lu = run(["ffmpeg", "-hide_banner", "-i", final, "-af", "ebur128", "-f", "null", "-"]).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", lu)
    lufs = float(m[-1]) if m else None
    if lufs is None or abs(lufs + 14) > 2:
        errs.append(f"loudness {lufs} LUFS (want about -14)")
    script = json.load(open(os.path.join(proj, "script.json")))
    words = json.load(open(os.path.join(proj, "words.json")))
    text = script.get("voice_text") or " ".join(script["lines"])
    n_script = len(re.findall(r"[\w']+", text))
    if len(words) < 0.9 * n_script:
        errs.append(f"word timings cover {len(words)} of {n_script} words")
    if not script.get("sources"):
        errs.append("script.json has no sources")
    t = script.get("title", "")
    if len(t) > 60 or not t.endswith("#shorts"):
        errs.append(f"title must be <=60 chars and end with #shorts: {t!r}")
    rep = json.load(open(os.path.join(out, "render_report.json")))
    res = {"duration": round(dur, 2), "lufs": lufs, "errors": errs, "render_warnings": rep["warnings"]}
    print(json.dumps(res, indent=1))
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    proj, cmd = sys.argv[1], sys.argv[2]
    if cmd == "sheet":
        sheet(proj, sys.argv[3] if len(sys.argv) > 3 else "draft")
    else:
        check(proj)
