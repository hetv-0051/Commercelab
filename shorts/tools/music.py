#!/usr/bin/env python3
"""Built-in music and sound effects, synthesized from scratch (no samples).

music(style, seconds, path)   -> background bed for a style
whoosh(path) / pop(path)      -> transition sound effects
"""
import wave

import numpy as np

SR = 44100

STYLE_MUSIC = {
    # root midi note, scale degrees for chords (progression), bpm, character
    "cosmos": dict(root=45, prog=[[0, 3, 7, 10], [-4, 0, 3, 7], [-2, 2, 5, 9], [-5, -1, 2, 7]],
                   bpm=84, pulse=0.25, arp=True, bright=0.55),
    "lab": dict(root=48, prog=[[0, 4, 7, 11], [-3, 0, 4, 7], [-7, -3, 0, 4], [-5, -1, 2, 5]],
                bpm=112, pulse=0.5, arp=True, bright=0.9),
    "archive": dict(root=38, prog=[[0, 3, 7], [-4, 0, 3], [-7, -3, 0], [-5, -1, 2]],
                    bpm=72, pulse=0.35, arp=False, bright=0.4),
    "flat": dict(root=50, prog=[[0, 4, 7, 11], [-5, -1, 2, 5], [-3, 0, 4, 7], [-7, -3, 0, 4]],
                 bpm=96, pulse=0.4, arp=True, bright=0.7),
    "alert": dict(root=40, prog=[[0, 3, 7], [1, 4, 8], [0, 3, 7], [-2, 2, 5]],
                  bpm=122, pulse=0.7, arp=True, bright=0.6),
}


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _env(n, a, r):
    e = np.ones(n)
    a = max(1, min(n, int(a * SR)))
    r = max(1, min(n - a, int(r * SR)))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r)
    return e


def _pad(freqs, n, bright, rng):
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for f in freqs:
        for det, pan in ((-0.12, 0.2), (0.0, 0.5), (0.12, 0.8)):
            ff = f * 2 ** (det / 12)
            ph = rng.uniform(0, 2 * np.pi)
            s = np.sin(2 * np.pi * ff * t + ph)
            s += bright * 0.35 * np.sin(4 * np.pi * ff * t + ph)
            s += bright * 0.15 * np.sin(6 * np.pi * ff * t + ph)
            out[:, 0] += s * (1 - pan)
            out[:, 1] += s * pan
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.2 * t)
    return out * lfo[:, None] / (len(freqs) * 3)


def _pluck(f, n, bright):
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + 0.4 * bright * np.sin(4 * np.pi * f * t)
    return s * np.exp(-t * 7)


def _kick(n):
    t = np.arange(n) / SR
    f = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def _hat(n, rng):
    t = np.arange(n) / SR
    s = rng.standard_normal(n)
    s = np.diff(s, prepend=0)  # crude high-pass
    return s * np.exp(-t * 60) * 0.25


def music(style, seconds, path, seed=7):
    cfg = STYLE_MUSIC.get(style, STYLE_MUSIC["cosmos"])
    rng = np.random.default_rng(seed)
    n = int((seconds + 1) * SR)
    out = np.zeros((n, 2))
    beat = 60 / cfg["bpm"]
    bar = beat * 4
    nb = int(np.ceil(seconds / bar)) + 1
    for b in range(nb):
        chord = cfg["prog"][b % len(cfg["prog"])]
        s0 = int(b * bar * SR)
        ln = int(bar * SR)
        if s0 >= n:
            break
        ln = min(ln, n - s0)
        freqs = [_hz(cfg["root"] + 12 + c) for c in chord]
        p = _pad(freqs, ln, cfg["bright"], rng) * _env(ln, 0.4, 0.4)[:, None]
        out[s0:s0 + ln] += p * 0.9
        # bass
        bl = ln
        tb = np.arange(bl) / SR
        bass = np.sin(2 * np.pi * _hz(cfg["root"] + chord[0]) * tb) * _env(bl, 0.02, 0.3)
        out[s0:s0 + bl] += (bass * 0.35)[:, None]
        for k in range(4 if cfg["arp"] else 0):
            for half in (0, 1):
                st = s0 + int((k * beat + half * beat / 2) * SR)
                if st >= n:
                    continue
                note = chord[(k * 2 + half) % len(chord)] + 24
                pl = min(int(beat * SR), n - st)
                pan = 0.3 + 0.4 * ((k + half) % 2)
                pk = _pluck(_hz(cfg["root"] + note), pl, cfg["bright"]) * 0.18
                out[st:st + pl, 0] += pk * (1 - pan)
                out[st:st + pl, 1] += pk * pan
        for k in range(4):
            st = s0 + int(k * beat * SR)
            if st >= n:
                continue
            kl = min(int(0.4 * SR), n - st)
            out[st:st + kl] += (_kick(kl) * cfg["pulse"] * 0.6)[:, None]
            ht = st + int(beat / 2 * SR)
            if ht < n and cfg["pulse"] > 0.3:
                hl = min(int(0.08 * SR), n - ht)
                out[ht:ht + hl] += (_hat(hl, rng) * cfg["pulse"])[:, None]
    # fade in/out
    out *= _env(n, 1.0, 2.0)[:, None]
    _write(path, out[: int(seconds * SR)])


def whoosh(path, dur=0.45, seed=3):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    # sweep a simple resonant band by mixing differently smoothed copies
    k = np.linspace(40, 4, n).astype(int)
    cs = np.cumsum(noise)
    sm = np.array([(cs[i] - cs[max(0, i - k[i])]) / k[i] for i in range(n)])
    s = noise - sm
    env = np.sin(np.pi * t / dur) ** 2
    s = s * env
    pan = np.linspace(0.2, 0.8, n)
    _write(path, np.stack([s * (1 - pan), s * pan], 1) * 0.5)


def pop(path, dur=0.12):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 900 - 500 * t / dur
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)
    _write(path, np.stack([s, s], 1) * 0.6)


def _write(path, x):
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.89
    pcm = (x * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    import sys
    music(sys.argv[1], float(sys.argv[2]), sys.argv[3])
