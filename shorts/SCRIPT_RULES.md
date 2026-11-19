# Script rules

- **Length:** 90–110 spoken words. That's 30–40 s at the default voice rate (+6%).
- **Line 1 is the hook question.** Ask something specific and surprising in under 12 words. No "Did you know".
- **Body:** 3–5 short sentences. Give one concrete fact per sentence, using numbers, names and comparisons.
- **The twist:** about 60–70% of the way in, flip the obvious answer ("But here's the thing…" or similar, in your own words).
- **Loop line:** the last line should lead back into the first line, so the end makes the viewer want to rewatch. Example: the last line ends on a setup the hook answers.
- **No calls to action** ("like and subscribe") and no filler.
- **Facts:** check every claim against at least one reliable source (NASA, ESA, NIH, peer-reviewed journals, Britannica, major museums, national science agencies, major newspapers). Put the URLs in `sources`. If a number can't be confirmed, cut it or soften it.
- **Originality:** write it yourself. Never reuse another creator's script, hook or structure word for word.
- **Title:** under 60 characters including ` #shorts`. Make it curious and specific, it must not give the answer away, and it must end with `#shorts`.

## script.json

```json
{
  "date": "2026-11-19",
  "topic": "short topic name",
  "style": "cosmos",
  "title": "Curious title here #shorts",
  "lines": ["Hook question?", "Fact.", "Fact.", "Twist.", "Loop line"],
  "highlight": ["keywords", "numbers", "to", "colour"],
  "sources": ["https://...", "https://..."],
  "description": "One or two catchy sentences. #science #space #shorts",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "category": "Science & Technology"
}
```
Optional fields are `voice` (an edge-tts voice name, default `en-US-AndrewNeural`) and `rate` (default `+6%`).
