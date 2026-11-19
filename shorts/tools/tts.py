#!/usr/bin/env python3
"""Generate the voiceover and per-word timings for a project.

Usage: python3 shorts/tools/tts.py <project_dir>

Reads <project_dir>/script.json ("voice_text" or the joined "lines", plus an
optional "voice" and "rate"), writes voice.mp3 and words.json
([{"w": "word", "start": s, "end": s}, ...]).
"""
import asyncio
import json
import os
import sys

# The session's HTTPS proxy re-signs TLS. edge-tts builds its SSL context from
# certifi, so point certifi at the proxy bundle for this process only.
import certifi

_CA = os.environ.get("SSL_CERT_FILE")
if not _CA and os.path.exists("/root/.ccr/ca-bundle.crt"):
    _CA = "/root/.ccr/ca-bundle.crt"
if _CA:
    certifi.where = lambda: _CA

import edge_tts  # noqa: E402
import edge_tts.communicate as _comm  # noqa: E402

_comm.certifi = certifi

DEFAULT_VOICE = "en-US-AndrewNeural"


async def synth(text, voice, rate, mp3_path):
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append({"w": ch["text"], "start": round(s, 3),
                              "end": round(s + ch["duration"] / 1e7, 3)})
    return words


def main():
    proj = sys.argv[1]
    script = json.load(open(os.path.join(proj, "script.json")))
    text = script.get("voice_text") or " ".join(script["lines"])
    voice = script.get("voice", DEFAULT_VOICE)
    rate = script.get("rate", "+6%")
    mp3 = os.path.join(proj, "voice.mp3")
    for attempt in range(4):
        try:
            words = asyncio.run(synth(text, voice, rate, mp3))
            break
        except Exception as e:  # network hiccup: retry
            print(f"tts attempt {attempt + 1} failed: {e}", file=sys.stderr)
            if attempt == 3:
                raise
    if not words:
        sys.exit("TTS returned no word timings")
    # Restore punctuation from the script so captions break at sentence ends.
    import re
    toks = text.split()
    ti = 0
    for w in words:
        core = re.sub(r"[^\w']", "", w["w"]).lower()
        for j in range(ti, min(ti + 4, len(toks))):
            if re.sub(r"[^\w']", "", toks[j]).lower() == core:
                w["w"] = toks[j]
                ti = j + 1
                break
    json.dump(words, open(os.path.join(proj, "words.json"), "w"), indent=1)
    print(f"voice.mp3 + {len(words)} words, ends {words[-1]['end']:.2f}s")


if __name__ == "__main__":
    main()
