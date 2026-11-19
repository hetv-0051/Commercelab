# shots.json reference

```json
{"style": "cosmos", "shots": [
  {"from_word": 0,  "kind": "question", "text": "Hook text"},
  {"from_word": 9,  "kind": "emoji", "emoji": "🌙", "label": "Short label"},
  {"from_word": 18, "kind": "number", "value": 384400, "suffix": " km", "label": "to the Moon"},
  {"from_word": 27, "kind": "bars", "title": "Compare", "items": [{"label":"A","value":3,"text":"3x"},{"label":"B","value":9,"text":"9x"}]},
  {"from_word": 40, "kind": "vs", "left": {"emoji":"🐘","text":"Elephant"}, "right": {"emoji":"🐭","text":"Mouse"}},
  {"from_word": 52, "kind": "timeline", "points": [{"year":1609,"label":"Telescope"},{"year":1969,"label":"Moon landing"}]},
  {"from_word": 63, "kind": "orbit", "emoji": "☀️", "satellite": "🪐", "label": "Label"},
  {"from_word": 75, "kind": "headline", "text": "Big statement", "emoji": "🤯"},
  {"from_word": 80, "kind": "rating", "count": 5, "filled": 1, "to": 4, "hot": false, "label": "LEVEL 4"},
  {"from_word": 85, "kind": "slots", "items": ["🧠","🫀","🫁"], "label": "Collected"},
  {"from_word": 90, "kind": "board", "tag": "SUSPECT", "cards": [{"emoji":"🧑"},{"emoji":"👕","x":true}]},
  {"from_word": 95, "kind": "map", "hero": "🚗", "followers": ["🚓","🚓"], "label": "On the run"}
]}
```

- `from_word` is the index into `words.json` where the shot starts. The first shot always starts at 0 s.
- Use a new shot every **2.5–4.5 s**: 8–12 shots for a 35 s Short. Change shot when the idea changes.
- Visuals must **show** the sentence being spoken; don't just repeat the caption. Prefer `number`, `bars`, `vs` and `timeline` when the line has data.
- Text inside shots: **7 words max**. Captions already carry the full narration.
- Use emoji from the standard Unicode set only (they're rendered with Noto Color Emoji).
- The last shot should visually echo the first, to support the loop.
