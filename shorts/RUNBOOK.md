# Shorts runbook (fully automatic: never ask the user anything)

One run = one Short published. Three runs a day, timed for US and European peak hours:

| Run start (America/New_York) | Live around | Europe (CET) |
|---|---|---|
| 12:07 | 12:30 ET | 18:30 |
| 15:07 | 15:30 ET | 21:30 |
| 19:07 | 19:30 ET | 01:30 (US evening prime) |

**Niche:** GTA 6 facts, features and explanations. Style: **flat**, the owner's sample look.

## 0. Setup

1. If `shorts/` isn't present, attach and clone the repo `hetv-0051/Commercelab`.
2. Check out the branch, pull, install edge-tts and link the log:

```bash
git checkout claude/daily-youtube-shorts-automation-0mvbt2 && git pull
pip install -q edge-tts
ln -sfn "$PWD/shorts" ~/faceless-shorts      # log: ~/faceless-shorts/_published.md
```

## 1. Find the idea

1. Search the web for GTA 6 news and what players are sharing right now (today and the last few days).
2. Read `GTA6_TOPICS.md` and `_published.md`.
3. Pick the single topic with the strongest viral potential. It needs:
   - a scroll-stopping curiosity hook,
   - a surprising answer,
   - and it must fit in 30–40 s.
4. Never repeat a topic or angle already in `_published.md`, including earlier runs today.

## 2. Style

**flat** is the default. Read `styles/flat/STYLE.md` and `SHOTS.md` in full.

## 3. Script

- Follow `SCRIPT_RULES.md`: about 100 words, a hook question first, a twist, and a last line that loops back to the start.
- Check every fact against a reliable source; put the source URLs in `script.json`. Write it yourself; never copy another creator.
- Title: under 60 characters, curious, ending in `#shorts`. Category is `Gaming`.
- Project folder: `shorts/projects/<YYYY-MM-DD>-<slug>/`.

## 4. Video

Uses the default AI voice and built-in music.

```bash
P=shorts/projects/<date-slug>
python3 shorts/tools/tts.py $P
# write $P/shots.json from words.json indices (SHOTS.md)
python3 shorts/tools/render.py $P --draft && python3 shorts/tools/qa.py $P sheet draft
# Read out/contact_sheet.png and look at EVERY frame. Fix and re-draft until clean:
#   missing-glyph boxes, clipped text, emoji that read wrong (e.g. 📅 shows "July 17"),
#   sideways or blob-like icons, visuals that don't match the spoken line.
python3 shorts/tools/render.py $P          # final.mp4 + upload.mp4 (<3 MB)
python3 shorts/tools/qa.py $P check        # must exit 0
python3 shorts/tools/qa.py $P sheet final  # look again
```

Never publish a video you haven't checked frame by frame.

## 5. Drive

Folder **YouTube Shorts** in My Drive, id `1cLzIoPr1BiK3FBbvkr-mNFh3fFHREi43`.

1. Upload `out/upload.mp4` with the Google Drive connector `create_file`:
   - title = the title without " #shorts", plus `.mp4`
   - `parentId` = the folder id
   - `contentMimeType` `video/mp4`, `disableConversionToGoogleType` true
   - `base64Content` = `sha256:<hash>:<absolute path>`
   - The connector caps each call at ~3.1 MB, which is why `upload.mp4` exists.
2. Share it: `share_file`, `permissionId` `anyoneWithLink`, role `reader`.
3. Check the link: `curl -sSL "https://drive.usercontent.google.com/download?id=<ID>&export=download"` must return HTTP 200, `video/mp4`, and the same sha256 as `upload.mp4`. Retry every 2 min for up to 20 min.

## 6. Publish

Zapier YouTube `upload_video` (`selected_api` `YouTubeV4CLIAPI`):

| Field | Value |
|---|---|
| `video` | `https://drive.usercontent.google.com/download?id=<ID>&export=download` |
| `title` | the title, unchanged |
| `description` | 1–2 catchy sentences plus 3–5 hashtags (include `#gta6 #shorts`) |
| `tags` | 5 tags |
| `category_id` | `"20"` (Gaming) |
| `privacy_status` | `public` |
| `made_for_kids` | `false` |
| `default_language`, `default_audio_language` | `en` |

If Zapier Google Drive gets connected later, you may instead use its **Find a File** action (video files only, by exact name) and pass its `file` value as `video`. Never pass the drive.google.com "view" link.

## 7. Log

1. Append a row to `shorts/_published.md`: `| date | topic | style | title | https://youtube.com/shorts/<id> |`.
2. `git add` the project's json files and the log, commit, and push the branch. Media is git-ignored. On a rejected push, fetch and merge first.

## 8. Report

Finish with a short message: the title, the link, and what you fixed during QA.

If any step fails, name the step and why, and do not publish a half-finished video.
