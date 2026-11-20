#!/usr/bin/env python3
"""Render a faceless Short (1080x1920, 30 fps) from a project folder.

Usage:
  python3 shorts/tools/render.py <project_dir> --draft   # fast 540x960, silent, for QA
  python3 shorts/tools/render.py <project_dir>           # final MP4 with mixed audio

Project files:
  script.json  title, lines, highlight words, sources
  words.json   word timings from tts.py
  shots.json   {"style": "...", "shots": [{"from_word": i, "kind": "...", ...}]}
  voice.mp3    voiceover from tts.py

Writes out/final.mp4 (or out/draft.mp4) and out/render_report.json, which lists
any layout warnings (text shrunk to fit, missing emoji, gaps) for QA.
"""
import json
import math
import os
import random
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import music  # noqa: E402

W, H, FPS = 1080, 1920, 30
FONT_DIR = "/usr/share/fonts/opentype/inter"
FONTS = {
    "black": os.path.join(FONT_DIR, "InterDisplay-Black.otf"),
    "bold": os.path.join(FONT_DIR, "InterDisplay-Bold.otf"),
    "semibold": os.path.join(FONT_DIR, "Inter-SemiBold.otf"),
    "serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
}
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

# Safe zone: YouTube Shorts overlays cover roughly the bottom 400 px and the
# right 140 px. Visuals live in VIS_BOX, captions in the band below it.
VIS_TOP, VIS_BOTTOM = 230, 1120
CAP_Y = 1250
SAFE_L, SAFE_R = 70, W - 150

STYLES = {
    "cosmos": dict(bg1=(6, 8, 28), bg2=(28, 16, 64), text=(245, 247, 255),
                   accent=(255, 200, 60), accent2=(90, 210, 255), font="black", fx="stars"),
    "lab": dict(bg1=(4, 32, 38), bg2=(10, 70, 72), text=(240, 255, 250),
                accent=(170, 255, 90), accent2=(255, 95, 150), font="black", fx="cells"),
    "archive": dict(bg1=(58, 40, 24), bg2=(150, 112, 70), text=(255, 244, 222),
                    accent=(255, 92, 60), accent2=(255, 214, 140), font="serif", fx="grain"),
    "alert": dict(bg1=(10, 8, 8), bg2=(70, 12, 12), text=(255, 250, 245),
                  accent=(255, 176, 0), accent2=(255, 70, 50), font="black", fx="scan"),
    # Flat vector explainer: navy, soft glows, small top captions with a
    # word-by-word reveal and a blue pill on key words.
    "flat": dict(bg1=(21, 28, 43), bg2=(24, 32, 50), text=(240, 242, 248),
                 accent=(255, 160, 40), accent2=(64, 156, 230), font="black", fx="flat",
                 layout="top", panel=(36, 46, 68), cream=(246, 240, 226), cork=(150, 105, 62)),
}


def apply_layout(st):
    global VIS_TOP, VIS_BOTTOM, CAP_Y
    if st.get("layout") == "top":
        VIS_TOP, VIS_BOTTOM, CAP_Y = 540, 1540, 360


def star_points(cx, cy, r, inner=0.48):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def soft_shadow(canvas, box, radius, blur=18, alpha=110, offset=(0, 14), ellipse=False):
    x0, y0, x1, y1 = [int(v) for v in box]
    pad = blur * 3
    sh = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    r = [pad, pad, pad + x1 - x0, pad + y1 - y0]
    if ellipse:
        d.ellipse(r, fill=(0, 0, 0, alpha))
    else:
        d.rounded_rectangle(r, radius=radius, fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh, (x0 - pad + offset[0], y0 - pad + offset[1]))


def medallion(canvas, cx, cy, r, st, ring=None):
    soft_shadow(canvas, [cx - r, cy - r, cx + r, cy + r], r, ellipse=True)
    d = ImageDraw.Draw(canvas)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=st.get("panel", (40, 50, 70)))
    if ring:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring, width=8)


def dashed_circle(d, cx, cy, r, col, width=5, dashes=16):
    for i in range(dashes):
        a0 = i * 360 / dashes
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + 360 / dashes * 0.55, fill=col, width=width)

_font_cache = {}
_emoji_cache = {}
WARN = []


def font(name, size):
    key = (name, int(size))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONTS.get(name, FONTS["black"]), int(size))
    return _font_cache[key]


def emoji_img(ch, size):
    key = (ch, int(size))
    if key in _emoji_cache:
        return _emoji_cache[key]
    f = ImageFont.truetype(EMOJI_FONT, 109)
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((80, 80), ch, font=f, embedded_color=True, anchor="mm")
    bb = im.getbbox()
    if not bb:
        WARN.append(f"emoji not renderable: {ch!r}")
        im = Image.new("RGBA", (int(size), int(size)), (0, 0, 0, 0))
    else:
        im = im.crop(bb)
        s = size / max(im.size)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    _emoji_cache[key] = im
    return im


# ---------- easing ----------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


# ---------- text helpers ----------
def wrap(text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if fnt.getlength(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(text, fname, max_w, max_h, start=150, min_size=52, spacing=1.08):
    bad = [c for c in text if ord(c) > 0x2400 and c not in "–—…’‘“”•·"]
    if bad:
        WARN.append(f"emoji/symbol in text field won't render (use an emoji field): {text!r}")
        text = "".join(c for c in text if c not in bad).strip()
    size = start
    while size >= min_size:
        f = font(fname, size)
        lines = wrap(text, f, max_w)
        lh = size * spacing
        if len(lines) * lh <= max_h and all(f.getlength(l) <= max_w for l in lines):
            return f, lines, lh
        size -= 4
    WARN.append(f"text too long, shrunk to minimum: {text[:40]!r}")
    f = font(fname, min_size)
    return f, wrap(text, f, max_w), min_size * spacing


def draw_lines(d, lines, f, lh, cx, cy, fill, stroke=(0, 0, 0), sw=6, hl=None, hl_fill=None):
    y0 = cy - (len(lines) * lh) / 2 + lh / 2
    for i, ln in enumerate(lines):
        y = y0 + i * lh
        if hl:
            # draw word by word to colour highlighted words
            total = f.getlength(ln)
            x = cx - total / 2
            for j, w in enumerate(ln.split(" ")):
                piece = w + (" " if j < len(ln.split(" ")) - 1 else "")
                key = re.sub(r"[^\w%]", "", w).lower()
                col = hl_fill if key in hl else fill
                d.text((x, y), piece, font=f, fill=col, anchor="lm",
                       stroke_width=sw, stroke_fill=stroke)
                x += f.getlength(piece)
        else:
            d.text((cx, y), ln, font=f, fill=fill, anchor="mm", stroke_width=sw, stroke_fill=stroke)


# ---------- backgrounds ----------
class Background:
    def __init__(self, st, seed):
        self.st = st
        rng = random.Random(seed)
        self.base = Image.new("RGB", (W, H))
        px = self.base.load()
        grad = [mix(st["bg1"], st["bg2"], (y / H) ** 1.3) for y in range(H)]
        d = ImageDraw.Draw(self.base)
        for y in range(H):
            d.line([(0, y), (W, y)], fill=grad[y])
        # soft glow blobs
        glow = Image.new("RGB", (W // 4, H // 4), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for _ in range(3):
            x, y, r = rng.randint(0, W // 4), rng.randint(0, H // 4), rng.randint(60, 140)
            gd.ellipse([x - r, y - r, x + r, y + r], fill=mix(st["bg2"], st["accent2"], 0.35))
        glow = glow.filter(ImageFilter.GaussianBlur(40)).resize((W, H), Image.BICUBIC)
        self.base = Image.composite(glow, self.base, Image.new("L", (W, H), 70))
        fx = st["fx"]
        self.items = []
        if fx == "stars":
            self.items = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(1, 3.6),
                           rng.uniform(0, 6.28), rng.uniform(0.5, 2)) for _ in range(170)]
        elif fx == "cells":
            self.items = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(20, 90),
                           rng.uniform(0, 6.28), rng.uniform(0.2, 0.7)) for _ in range(22)]
        elif fx == "grain":
            g = Image.effect_noise((W // 2, H // 2), 40).resize((W, H)).convert("RGB")
            self.base = Image.blend(self.base, g, 0.07)
            vign = Image.new("L", (W, H), 0)
            ImageDraw.Draw(vign).ellipse([-300, -200, W + 300, H + 200], fill=255)
            vign = vign.filter(ImageFilter.GaussianBlur(160))
            self.base = Image.composite(self.base, Image.new("RGB", (W, H), (20, 12, 6)), vign)
            self.items = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(1, 3)) for _ in range(60)]
        elif fx == "flat":
            self.base = Image.new("RGB", (W, H), st["bg1"])
            self.glows = []
            for col, alpha in (((200, 60, 60), 70), ((50, 110, 220), 80)):
                g = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
                ImageDraw.Draw(g).ellipse([60, 60, 240, 240], fill=(*col, alpha))
                g = g.filter(ImageFilter.GaussianBlur(40)).resize((1400, 1400), Image.BICUBIC)
                self.glows.append(g)
        elif fx == "scan":
            d = ImageDraw.Draw(self.base)
            for y in range(0, H, 6):
                d.line([(0, y), (W, y)], fill=mix(st["bg1"], (0, 0, 0), 0.5))

    def frame(self, t):
        im = self.base.copy()
        st, fx = self.st, self.st["fx"]
        if fx == "flat":
            im = im.convert("RGBA")
            for i, g in enumerate(self.glows):
                x = int(-500 + (i * 600) + 160 * math.sin(t * 0.25 + i * 2))
                y = int(200 + i * 500 + 220 * math.cos(t * 0.2 + i))
                im.alpha_composite(g, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
            return im.convert("RGB")
        d = ImageDraw.Draw(im, "RGBA")
        if fx == "stars":
            for x, y, r, ph, sp in self.items:
                a = int(120 + 135 * (0.5 + 0.5 * math.sin(t * sp * 2 + ph)))
                yy = (y + t * 12 * r) % H
                d.ellipse([x - r, yy - r, x + r, yy + r], fill=(255, 255, 255, a))
        elif fx == "cells":
            for x, y, r, ph, sp in self.items:
                xx = x + 30 * math.sin(t * sp + ph)
                yy = (y - t * 25 * sp) % (H + 200) - 100
                rr = r * (1 + 0.08 * math.sin(t * 2 + ph))
                d.ellipse([xx - rr, yy - rr, xx + rr, yy + rr], outline=(*st["accent"], 60), width=4)
                d.ellipse([xx - rr * .35, yy - rr * .35, xx + rr * .35, yy + rr * .35], fill=(*st["accent2"], 45))
        elif fx == "grain":
            for x, y, r in self.items:
                yy = (y + t * 20) % H
                d.ellipse([x - r, yy - r, x + r, yy + r], fill=(255, 230, 190, 70))
            if int(t * FPS) % 7 == 0:
                d.line([(int(t * 997) % W, 0), (int(t * 997) % W, H)], fill=(255, 240, 210, 30), width=2)
        elif fx == "scan":
            p = 0.5 + 0.5 * math.sin(t * 4)
            d.rectangle([0, 0, W, H], fill=(*st["accent2"], int(14 * p)))
            y = int((t * 400) % H)
            d.rectangle([0, y, W, y + 60], fill=(255, 255, 255, 10))
        return im


# ---------- shots ----------
def draw_shot(canvas, shot, lt, dur, st, hl):
    """Draw one shot onto RGBA canvas. lt = seconds since shot start."""
    d = ImageDraw.Draw(canvas)
    k = shot.get("kind", "headline")
    cx = (SAFE_L + SAFE_R) / 2
    cy = (VIS_TOP + VIS_BOTTOM) / 2
    pin = ease_back(lt / 0.35)
    fnt_name = st["font"]
    txt = st["text"]
    acc = st["accent"]

    def paste_emoji(ch, size, x, y, scale=1.0):
        im = emoji_img(ch, size * max(0.05, scale))
        canvas.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2)))

    if k == "headline":
        top = cy
        if shot.get("emoji"):
            paste_emoji(shot["emoji"], 300, cx, VIS_TOP + 190 + 12 * math.sin(lt * 3), pin)
            top = cy + 150
        f, lines, lh = fit_text(shot["text"], fnt_name, SAFE_R - SAFE_L - 20,
                                (VIS_BOTTOM - top) * 2 - 120 if shot.get("emoji") else 760,
                                start=shot.get("size", 128))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_lines(ImageDraw.Draw(layer), lines, f, lh, cx, top, txt, sw=7, hl=hl, hl_fill=acc)
        s = lerp(0.6, 1.0, pin)
        if s != 1.0:
            layer = layer.resize((int(W * s), int(H * s)), Image.BILINEAR)
            off = (int(cx - cx * s), int(top - top * s))
            tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            tmp.alpha_composite(layer, (max(0, off[0]), max(0, off[1])))
            layer = tmp
        canvas.alpha_composite(layer)

    elif k == "emoji":
        bob = 18 * math.sin(lt * 2.6)
        if st.get("layout") == "top":
            medallion(canvas, cx, cy - 90, int(shot.get("size", 460) * 0.62 * max(0.2, pin)), st)
        paste_emoji(shot["emoji"], shot.get("size", 460), cx, cy - 90 + bob, pin)
        if shot.get("label"):
            f, lines, lh = fit_text(shot["label"], fnt_name, SAFE_R - SAFE_L, 260, start=96)
            draw_lines(d, lines, f, lh, cx, VIS_BOTTOM - 150, txt, sw=6, hl=hl, hl_fill=acc)

    elif k == "number":
        val = float(shot["value"])
        p = ease_out(lt / max(0.6, min(1.6, dur * 0.6)))
        cur = val * p
        dec = int(shot.get("decimals", 0))
        s = f"{cur:,.{dec}f}"
        s = shot.get("prefix", "") + s + shot.get("suffix", "")
        f, lines, lh = fit_text(s, "black", SAFE_R - SAFE_L, 300, start=230, min_size=80)
        draw_lines(d, lines, f, lh, cx, cy - 80, acc, sw=8)
        if shot.get("label"):
            f2, l2, lh2 = fit_text(shot["label"], fnt_name, SAFE_R - SAFE_L, 260, start=84)
            draw_lines(d, l2, f2, lh2, cx, cy + 170, txt, sw=6, hl=hl, hl_fill=acc)
        if shot.get("emoji"):
            paste_emoji(shot["emoji"], 200, cx, VIS_TOP + 90, pin)

    elif k == "bars":
        items = shot["items"][:4]
        mx = max(float(i["value"]) for i in items) or 1
        bh, gap = 92, 86
        y0 = cy - (len(items) * (bh + gap)) / 2 + 40
        if shot.get("title"):
            f, lines, lh = fit_text(shot["title"], fnt_name, SAFE_R - SAFE_L, 180, start=80)
            draw_lines(d, lines, f, lh, cx, VIS_TOP + 70, txt, sw=6, hl=hl, hl_fill=acc)
        lf = font("bold", 50)
        for i, it in enumerate(items):
            p = ease_out((lt - 0.25 * i) / 0.8)
            y = y0 + i * (bh + gap)
            d.text((SAFE_L, y - 10), it["label"], font=lf, fill=txt, anchor="ls",
                   stroke_width=4, stroke_fill=(0, 0, 0))
            wfull = (SAFE_R - SAFE_L - 40) * float(it["value"]) / mx
            col = acc if i == len(items) - 1 or it.get("hl") else st["accent2"]
            d.rounded_rectangle([SAFE_L, y, SAFE_L + max(bh, wfull * p), y + bh], radius=24, fill=col)
            vs = it.get("text", str(it["value"]))
            d.text((SAFE_L + max(bh, wfull * p) - 20, y + bh / 2), vs, font=font("black", 50),
                   fill=(0, 0, 0), anchor="rm")

    elif k == "vs":
        a, b = shot["left"], shot["right"]
        for side, item, x in ((0, a, SAFE_L + 205), (1, b, SAFE_R - 205)):
            p = ease_back((lt - 0.2 * side) / 0.4)
            xx = x + (1 - p) * (-500 if side == 0 else 500)
            box = [xx - 190, cy - 280, xx + 190, cy + 220]
            d.rounded_rectangle(box, radius=40, fill=(*mix(st["bg2"], (0, 0, 0), 0.3), 255),
                                outline=acc if side else st["accent2"], width=8)
            if item.get("emoji"):
                paste_emoji(item["emoji"], 190, xx, cy - 120)
            f, lines, lh = fit_text(item["text"], fnt_name, 330, 200, start=64, min_size=36)
            draw_lines(d, lines, f, lh, xx, cy + 90, txt, sw=4)
        vp = ease_back((lt - 0.4) / 0.3)
        if vp > 0:
            vf = font("black", int(120 * vp) + 1)
            d.text((cx, cy - 30), "VS", font=vf, fill=acc, anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))
        if shot.get("title"):
            f, lines, lh = fit_text(shot["title"], fnt_name, SAFE_R - SAFE_L, 170, start=80)
            draw_lines(d, lines, f, lh, cx, VIS_TOP + 40, txt, sw=6, hl=hl, hl_fill=acc)

    elif k == "timeline":
        pts = shot["points"][:4]
        x0, x1 = SAFE_L + 150, SAFE_R - 150
        y = cy + 60
        pl = ease_out(lt / 0.9)
        d.line([(x0, y), (lerp(x0, x1, pl), y)], fill=txt, width=10)
        for i, ptn in enumerate(pts):
            x = lerp(x0, x1, i / max(1, len(pts) - 1))
            p = ease_back((lt - 0.3 - 0.3 * i) / 0.35)
            if p <= 0:
                continue
            r = 28 * p
            col = acc if i == len(pts) - 1 else st["accent2"]
            d.ellipse([x - r, y - r, x + r, y + r], fill=col, outline=(0, 0, 0), width=4)
            up = i % 2 == 0
            d.text((x, y + (-80 if up else 90)), str(ptn["year"]), font=font("black", 84),
                   fill=col, anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
            f, lines, lh = fit_text(ptn["label"], "bold", 300, 150, start=60, min_size=36)
            draw_lines(d, lines, f, lh, x, y + (-200 if up else 210), txt, sw=4)
        if shot.get("title"):
            f, lines, lh = fit_text(shot["title"], fnt_name, SAFE_R - SAFE_L, 200, start=84)
            draw_lines(d, lines, f, lh, cx, VIS_TOP + 80, txt, sw=6, hl=hl, hl_fill=acc)

    elif k == "orbit":
        center = shot.get("emoji", "🌍")
        paste_emoji(center, 300, cx, cy - 40, pin)
        n = int(shot.get("count", 6))
        R = 330
        for i in range(n):
            ang = lt * 1.3 + i * 2 * math.pi / n
            x, y = cx + R * math.cos(ang), cy - 40 + R * 0.45 * math.sin(ang)
            if shot.get("satellite"):
                paste_emoji(shot["satellite"], 90, x, y)
            else:
                d.ellipse([x - 18, y - 18, x + 18, y + 18], fill=acc)
        if shot.get("label"):
            f, lines, lh = fit_text(shot["label"], fnt_name, SAFE_R - SAFE_L, 220, start=88)
            draw_lines(d, lines, f, lh, cx, VIS_BOTTOM - 110, txt, sw=6, hl=hl, hl_fill=acc)

    elif k == "question":
        s = 1 + 0.06 * math.sin(lt * 5)
        qf = font("black", int(520 * s * max(0.1, pin)))
        d.text((cx, cy - 120), shot.get("mark", "?"), font=qf, fill=acc, anchor="mm",
               stroke_width=12, stroke_fill=(0, 0, 0))
        if shot.get("text"):
            f, lines, lh = fit_text(shot["text"], fnt_name, SAFE_R - SAFE_L, 300, start=96)
            draw_lines(d, lines, f, lh, cx, VIS_BOTTOM - 140, txt, sw=6, hl=hl, hl_fill=acc)
    elif k == "rating":
        n = int(shot.get("count", 5))
        f0 = float(shot.get("filled", 0))
        f1 = float(shot.get("to", f0))
        filled = lerp(f0, f1, ease_out((lt - 0.3) / 1.2))
        r = min(80, (SAFE_R - SAFE_L) / n / 2.2)
        gap = r * 2.3
        x0 = cx - gap * (n - 1) / 2
        y = cy - 60 if shot.get("label") else cy
        for i in range(n):
            p = ease_back((lt - 0.06 * i) / 0.3)
            if p <= 0:
                continue
            x = x0 + i * gap
            rr = r * p
            on = i < round(filled)
            col = st.get("cream", txt) if on else mix(st["bg1"], (0, 0, 0), 0.4)
            if on and shot.get("hot"):
                col = acc
            d.polygon(star_points(x + 4, y + 8, rr), fill=(0, 0, 0, 90))
            d.polygon(star_points(x, y, rr), fill=col)
        if shot.get("label"):
            f, lines, lh = fit_text(shot["label"], "black", SAFE_R - SAFE_L, 220, start=110)
            lab = ease_back((lt - 0.5) / 0.3)
            if lab > 0:
                tw = max(f.getlength(l) for l in lines) + 70
                th = len(lines) * lh + 30
                box = [cx - tw / 2, y + 150, cx + tw / 2, y + 150 + th]
                d.rounded_rectangle(box, radius=26, fill=acc)
                draw_lines(d, lines, f, lh, cx, y + 150 + th / 2, (25, 25, 35), sw=0)

    elif k == "slots":
        items = shot["items"][:5]
        n = len(items)
        span = max(0.6, dur - 0.6)
        shown = min(n, int(max(0, lt - 0.2) / (span / n)) + (1 if lt > 0.2 else 0))
        if shot.get("all"):
            shown = n
        r = 64
        gap = min(190, (SAFE_R - SAFE_L) / n)
        x0 = cx - gap * (n - 1) / 2
        y = VIS_TOP + 90
        for i, ch in enumerate(items):
            x = x0 + i * gap
            if i < shown:
                p = ease_back((lt - 0.2 - i * span / n) / 0.25) if not shot.get("all") else 1
                d.ellipse([x - r, y - r, x + r, y + r], fill=st.get("cream", txt))
                paste_emoji(ch, 84, x, y, max(0.1, p))
            else:
                dashed_circle(d, x, y, r - 4, (200, 205, 220))
                d.text((x, y), "?", font=font("black", 64), fill=(220, 224, 235), anchor="mm")
        if shown:
            cur = items[shown - 1]
            p = ease_back((lt - 0.2 - (shown - 1) * span / n) / 0.3) if not shot.get("all") else pin
            R = 230
            medallion(canvas, cx, cy + 140, R, st)
            paste_emoji(cur, 300, cx, cy + 140 + 8 * math.sin(lt * 3), max(0.1, p))
        if shot.get("label"):
            f, lines, lh = fit_text(shot["label"], "black", SAFE_R - SAFE_L, 160, start=80)
            draw_lines(d, lines, f, lh, cx, VIS_BOTTOM - 40, txt, sw=0)

    elif k == "board":
        cards = shot["cards"][:3]
        bx0, bx1 = SAFE_L - 20, SAFE_R + 60
        by0, by1 = cy - 330, cy + 330
        soft_shadow(canvas, [bx0, by0, bx1, by1], 30)
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=30, fill=(110, 74, 42))
        d.rounded_rectangle([bx0 + 22, by0 + 22, bx1 - 22, by1 - 22], radius=18, fill=st.get("cork", (150, 105, 62)))
        rng = random.Random(7)
        for _ in range(140):
            x, y = rng.uniform(bx0 + 30, bx1 - 30), rng.uniform(by0 + 30, by1 - 30)
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(125, 86, 50))
        tag = shot.get("tag", "")
        if tag:
            tf = font("black", 40)
            tw = tf.getlength(tag) + 50
            d.rounded_rectangle([cx - tw / 2, by0 + 30, cx + tw / 2, by0 + 90], radius=8, fill=(250, 248, 240))
            d.text((cx, by0 + 60), tag, font=tf, fill=(220, 60, 40), anchor="mm")
        pos = [(cx - 200, cy - 60, -6), (cx + 200, cy - 70, 5), (cx, cy + 170, -3)]
        if len(cards) == 2:
            pos = [(cx - 190, cy, -5), (cx + 190, cy - 10, 4)]
        if len(cards) == 1:
            pos = [(cx, cy, -3)]
        span = max(0.5, dur - 0.8)
        pts = []
        for i, c in enumerate(cards):
            t0 = 0.15 + i * span / len(cards) if not shot.get("all") else 0
            p = ease_back((lt - t0) / 0.3)
            x, y, rot = pos[i]
            pts.append((x, y - 130))
            if p <= 0:
                cw = 300
                card = Image.new("RGBA", (cw, cw + 40), (0, 0, 0, 0))
                cd = ImageDraw.Draw(card)
                cd.rounded_rectangle([6, 6, cw - 6, cw + 34], radius=10, outline=(240, 235, 220), width=5)
                cd.text((cw / 2, cw / 2 + 20), "?", font=font("black", 120), fill=(240, 235, 220), anchor="mm")
                card = card.rotate(rot, expand=True, resample=Image.BICUBIC)
                canvas.alpha_composite(card, (int(x - card.width / 2), int(y - card.height / 2)))
                continue
            cw = int(300 * lerp(0.5, 1, p))
            card = Image.new("RGBA", (cw, int(cw * 1.13)), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            cd.rectangle([0, 0, cw, int(cw * 1.13)], fill=(250, 248, 242))
            cd.rectangle([cw * 0.07, cw * 0.07, cw * 0.93, cw * 0.93], fill=mix(acc, (255, 255, 255), 0.55))
            em = emoji_img(c["emoji"], cw * 0.7)
            card.alpha_composite(em, (int(cw / 2 - em.width / 2), int(cw * 0.5 - em.height / 2)))
            if c.get("x") and lt > t0 + float(c.get("x_after", 0.6)):
                xp = ease_out((lt - t0 - float(c.get("x_after", 0.6))) / 0.25)
                m = cw * 0.1
                cd.line([(m, m), (lerp(m, cw - m, xp), lerp(m, cw - m, xp))], fill=(225, 40, 40), width=int(cw * 0.06))
                cd.line([(cw - m, m), (lerp(cw - m, m, xp), lerp(m, cw - m, xp))], fill=(225, 40, 40), width=int(cw * 0.06))
            card = card.rotate(rot, expand=True, resample=Image.BICUBIC)
            soft_shadow(canvas, [x - cw / 2, y - cw * 0.56, x + cw / 2, y + cw * 0.56], 8, blur=10)
            canvas.alpha_composite(card, (int(x - card.width / 2), int(y - card.height / 2)))
            d.ellipse([x - 12, y - cw * 0.56 - 12, x + 12, y - cw * 0.56 + 12], fill=(220, 50, 40))
        if len(pts) > 1 and lt > 0.5:
            for a, b in zip(pts, pts[1:]):
                d.line([a, b], fill=(210, 40, 40), width=5)

    elif k == "map":
        # Flat top-down "city/terrain" blocks scrolling past a hero icon.
        speed = float(shot.get("speed", 220))
        rng = random.Random(11)
        cols = [(70, 80, 100), (95, 105, 80), (110, 90, 70), (80, 75, 110), (60, 95, 100)]
        cell = 270
        off = (lt * speed) % cell
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        for gy in range(-1, H // cell + 2):
            for gx in range(-1, W // cell + 2):
                rr = random.Random(gx * 31 + (gy - int(lt * speed // cell)) * 17)
                x, y = gx * cell + 35, gy * cell + off + 35
                col = cols[rr.randrange(len(cols))]
                ld.rounded_rectangle([x, y, x + cell - 70, y + cell - 70], radius=10, fill=col)
                ld.rectangle([x + 20, y + 20, x + 60, y + 50], fill=mix(col, (0, 0, 0), 0.25))
                if rr.random() < 0.5:
                    ld.rectangle([x + 120, y + 90, x + 130, y + 100], fill=(255, 210, 120))
            for gx in range(-1, W // cell + 2):
                for k2 in range(0, cell, 50):
                    ld.line([(gx * cell + 17, gy * cell + off + k2), (gx * cell + 17, gy * cell + off + k2 + 25)],
                            fill=(120, 125, 140), width=3)
        canvas.alpha_composite(lay)
        dim = Image.new("RGBA", (W, H), (*st["bg1"], 70))
        canvas.alpha_composite(dim)
        hy = cy + 120
        hero = shot.get("hero", "🚗")
        rot = float(shot.get("rotate", -90))  # car emoji face left; -90 turns them to face up
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        spots = [(cx + 25 * math.sin(lt * 1.5), hy)]
        for i, fol in enumerate(shot.get("followers", [])):
            spots.append((cx + 40 * math.sin(lt * 2 + i) + (i % 2) * 60 - 30, hy + 220 + i * 170))
        for x, y in spots:
            gd.polygon([(x - 30, y - 50), (x + 30, y - 50), (x + 110, y - 330), (x - 110, y - 330)],
                       fill=(255, 245, 200, 40))
        canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
        for i, fol in enumerate(shot.get("followers", [])):
            x, y = spots[i + 1]
            im = emoji_img(fol, 120).rotate(rot, expand=True, resample=Image.BICUBIC)
            canvas.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2)))
        x, y = spots[0]
        im = emoji_img(hero, 150 * max(0.1, pin)).rotate(rot, expand=True, resample=Image.BICUBIC)
        canvas.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2)))
        if shot.get("label"):
            f, lines, lh = fit_text(shot["label"], "black", SAFE_R - SAFE_L, 150, start=76)
            draw_lines(ImageDraw.Draw(canvas), lines, f, lh, cx, VIS_TOP + 60, txt, sw=6)
    else:
        WARN.append(f"unknown shot kind {k!r}")


# ---------- captions ----------
def caption_chunks(words, max_words=3):
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        end_punct = re.search(r"[.,!?;:]$", w["w"])
        if len(cur) >= max_words or end_punct:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out = []
    for ci, ch in enumerate(chunks):
        start = words[ch[0]]["start"]
        end = words[chunks[ci + 1][0]]["start"] if ci + 1 < len(chunks) else words[ch[-1]]["end"] + 0.5
        out.append((start, end, ch))
    return out


def draw_caption_top(canvas, words, chunk, t, st, hl):
    """Small sentence-case caption near the top. Spoken words are bright,
    upcoming words are faint, key words sit on a blue pill."""
    start, end, idx = chunk
    d = ImageDraw.Draw(canvas, "RGBA")
    size = 66
    f = font("bold", size)
    toks = [words[i]["w"] for i in idx]
    maxw = SAFE_R - SAFE_L + 60
    while f.getlength(" ".join(toks)) > maxw and size > 44:
        size -= 2
        f = font("bold", size)
    if f.getlength(" ".join(toks)) > maxw:
        WARN.append(f"caption overflows safe area: {' '.join(toks)!r}")
    total = f.getlength(" ".join(toks))
    x = W / 2 - total / 2 - 20
    for j, i in enumerate(idx):
        w = words[i]
        piece = w["w"]
        pw = f.getlength(piece)
        spoken = t >= w["start"] - 0.03
        key = re.sub(r"[^\w%]", "", w["w"]).lower()
        if spoken and key in hl:
            p = ease_back((t - w["start"]) / 0.18)
            pad = 12 * p
            d.rounded_rectangle([x - pad, CAP_Y - size * 0.62, x + pw + pad, CAP_Y + size * 0.55],
                                radius=14, fill=(*st["accent2"], 255))
        if spoken:
            d.text((x + 2, CAP_Y + 4), piece, font=f, fill=(0, 0, 0, 120), anchor="lm")
            d.text((x, CAP_Y), piece, font=f, fill=(*st["text"], 255), anchor="lm")
        else:
            d.text((x, CAP_Y), piece, font=f, fill=(*st["text"], 55), anchor="lm")
        x += pw + f.getlength(" ")


def draw_caption(canvas, words, chunk, t, st, hl):
    if st.get("layout") == "top":
        return draw_caption_top(canvas, words, chunk, t, st, hl)
    start, end, idx = chunk
    d = ImageDraw.Draw(canvas)
    p = ease_back((t - start) / 0.18)
    size = int(96 * lerp(0.75, 1.0, p))
    f = font("black", size)
    toks = [words[i]["w"] for i in idx]
    txt = " ".join(toks).upper()
    maxw = SAFE_R - SAFE_L
    while f.getlength(txt) > maxw and size > 50:
        size -= 4
        f = font("black", size)
    if f.getlength(txt) > maxw:
        WARN.append(f"caption overflows safe area: {txt!r}")
    total = f.getlength(txt)
    x = (SAFE_L + SAFE_R) / 2 - total / 2
    # backing plate
    pad = 26
    d2 = ImageDraw.Draw(canvas, "RGBA")
    d2.rounded_rectangle([x - pad, CAP_Y - size * 0.72, x + total + pad, CAP_Y + size * 0.62],
                         radius=28, fill=(0, 0, 0, 120))
    for j, i in enumerate(idx):
        w = words[i]
        piece = w["w"].upper() + (" " if j < len(idx) - 1 else "")
        active = w["start"] <= t < (words[i + 1]["start"] if i + 1 < len(words) else w["end"] + 0.3)
        key = re.sub(r"[^\w%]", "", w["w"]).lower()
        col = st["accent"] if (key in hl or active and key in hl) else st["text"]
        if active and key not in hl:
            col = mix(st["text"], st["accent2"], 0.6)
        d.text((x, CAP_Y), piece, font=f, fill=col, anchor="lm", stroke_width=8, stroke_fill=(0, 0, 0))
        x += f.getlength(piece)


# ---------- timeline ----------
def shot_times(shots, words, total):
    times = []
    for i, s in enumerate(shots):
        st = 0.0 if i == 0 else words[min(s["from_word"], len(words) - 1)]["start"] - 0.08
        times.append(max(0.0, st))
    out = []
    for i, s in enumerate(shots):
        out.append((times[i], times[i + 1] if i + 1 < len(times) else total, s))
    return out


def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main():
    proj = sys.argv[1]
    draft = "--draft" in sys.argv
    script = json.load(open(os.path.join(proj, "script.json")))
    words = json.load(open(os.path.join(proj, "words.json")))
    spec = json.load(open(os.path.join(proj, "shots.json")))
    style = spec.get("style", "cosmos")
    st = STYLES[style]
    apply_layout(st)
    hl = {re.sub(r"[^\w%]", "", h).lower() for h in script.get("highlight", [])}
    voice = os.path.join(proj, "voice.mp3")
    vdur = probe_duration(voice)
    total = round(vdur + 0.7, 2)
    shots = shot_times(spec["shots"], words, total)
    caps = caption_chunks(words, 4 if st.get("layout") == "top" else 3)
    bg = Background(st, seed=hash(script.get("title", "")) & 0xFFFF)
    out_dir = os.path.join(proj, "out")
    os.makedirs(out_dir, exist_ok=True)
    nframes = int(total * FPS)
    ow, oh = (540, 960) if draft else (W, H)
    silent = os.path.join(out_dir, "draft.mp4" if draft else "video_silent.mp4")
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{ow}x{oh}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                            "-preset", "veryfast" if draft else "medium", "-crf", "26" if draft else "18",
                            "-pix_fmt", "yuv420p", silent], stdin=subprocess.PIPE)
    cut_times = [s for s, _, _ in shots][1:]
    for fi in range(nframes):
        t = fi / FPS
        frame = bg.frame(t).convert("RGBA")
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for s0, s1, shot in shots:
            if s0 <= t < s1:
                draw_shot(layer, shot, t - s0, s1 - s0, st, hl)
                # punch-in on cut + slow push
                lt = t - s0
                z = 1 + 0.10 * (1 - ease_out(lt / 0.25)) + 0.035 * clamp(lt / max(1, s1 - s0))
                if abs(z - 1) > 0.002:
                    big = layer.resize((int(W * z), int(H * z)), Image.BILINEAR)
                    l2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    l2.alpha_composite(big, (0, 0), (int((big.width - W) / 2), int((big.height - H) / 2)))
                    layer = l2
                break
        frame.alpha_composite(layer)
        # Flatten first: ImageDraw only blends translucent fills on RGB images.
        frame = frame.convert("RGB")
        for c in caps:
            if c[0] <= t < c[1]:
                draw_caption(frame, words, c, t, st, hl)
                break
        d = ImageDraw.Draw(frame, "RGBA")
        d.rectangle([0, 0, int(W * t / total), 12], fill=(*st["accent"], 255))
        for ct in cut_times:
            if 0 <= t - ct < 0.1:
                d.rectangle([0, 0, W, H], fill=(255, 255, 255, int(110 * (1 - (t - ct) / 0.1))))
        img = frame
        if draft:
            img = img.resize((ow, oh), Image.BILINEAR)
        enc.stdin.write(img.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("video encode failed")

    report = {"style": style, "duration": total, "shots": [[round(a, 2), round(b, 2), s.get("kind")]
                                                          for a, b, s in shots],
              "warnings": sorted(set(WARN))}
    for a, b, s in shots:
        if b - a < 0.8:
            report["warnings"].append(f"shot at {a:.2f}s is only {b - a:.2f}s long")
        if b - a > 8:
            report["warnings"].append(f"shot at {a:.2f}s holds {b - a:.1f}s (consider splitting)")
    json.dump(report, open(os.path.join(out_dir, "render_report.json"), "w"), indent=1)
    if draft:
        print(json.dumps(report, indent=1))
        return

    # ----- audio mix -----
    bed = os.path.join(out_dir, "music.wav")
    wh = os.path.join(out_dir, "whoosh.wav")
    music.music(style, total, bed)
    music.whoosh(wh)
    inputs = ["-i", silent, "-i", voice, "-i", bed]
    filt = ["[2:a]volume=0.22[bed]", "[1:a]apad,atrim=0:%s,asplit=2[v1][vsc]" % total,
            "[bed][vsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[duck]"]
    mixins = ["[v1]", "[duck]"]
    for i, ct in enumerate(cut_times):
        inputs += ["-i", wh]
        ms = max(0, int((ct - 0.2) * 1000))
        filt.append(f"[{3 + i}:a]adelay={ms}|{ms},volume=0.35[w{i}]")
        mixins.append(f"[w{i}]")
    filt.append("".join(mixins) + f"amix=inputs={len(mixins)}:normalize=0,"
                "loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    final = os.path.join(out_dir, "final.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt),
                    "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", "-t", str(total), "-movflags", "+faststart", final], check=True)
    # Upload copy under 3 MB: the Drive connector caps each call at ~3.1 MB of file.
    up = os.path.join(out_dir, "upload.mp4")
    vk = max(300, int((2.85e6 * 8 / total - 96000) / 1000))
    for ps in (1, 2):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", final, "-c:v", "libx264", "-preset", "slow",
               "-b:v", f"{vk}k", "-pass", str(ps), "-passlogfile", os.path.join(out_dir, "x264")]
        cmd += (["-an", "-f", "mp4", os.devnull] if ps == 1 else
                ["-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", up])
        subprocess.run(cmd, check=True)
    for f in os.listdir(out_dir):
        if f.startswith("x264"):
            os.remove(os.path.join(out_dir, f))
    report["upload_bytes"] = os.path.getsize(up)
    if report["upload_bytes"] > 3_000_000:
        report["warnings"].append(f"upload.mp4 is {report['upload_bytes']} bytes (>3 MB)")
    json.dump(report, open(os.path.join(out_dir, "render_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))
    print("final:", final, "upload:", up)


if __name__ == "__main__":
    main()
