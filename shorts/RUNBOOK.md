# Daily Short runbook (fully automatic, no questions)

Run in a cloud session with this repo checked out. Make every decision yourself and never ask the user anything.

## 0. Setup (every run, about 1 min)

```bash
cd <repo> && git checkout claude/daily-youtube-shorts-automation-0mvbt2 && git pull
pip install -q edge-tts
ln -sfn "$PWD/shorts" ~/faceless-shorts      # log lives at ~/faceless-shorts/_published.md
```

## 1. Find the idea

1. Search the web for what's trending and being shared right now in science, space, the human body, history, survival and "what if" questions.
2. Pick the one topic with the strongest viral potential. It needs:
   - a scroll-stopping curiosity hook,
   - a surprising answer,
   - and it must fit in 30–40 s.
3. Read `_published.md` and never repeat a topic that's already in it.

## 2. Choose the style

Read `styles/GUIDE.md`. **flat** is the default; it matches the owner's sample. Read the chosen `styles/<style>/STYLE.md` in full.

## 3. Write the script

- Follow `SCRIPT_RULES.md`: about 100 words, hook question first, a twist, and a last line that loops back to the start.
- Verify every fact and put the source URLs in `script.json`. Write it yourself; never copy another creator.
- Title: under 60 characters, ending in `#shorts`.
- Project folder: `projects/<YYYY-MM-DD>-<slug>/`.

## 4. Make the video

Default AI voice and built-in music.

```bash
P=shorts/projects/<date-slug>
python3 shorts/tools/tts.py $P                       # voice.mp3 + words.json
# write $P/shots.json using word indices from words.json (see SHOTS.md)
python3 shorts/tools/render.py $P --draft            # read the warnings
python3 shorts/tools/qa.py $P sheet draft            # open out/contact_sheet.png, look at EVERY frame
# fix anything wrong (text boxes, overlaps, empty or ugly frames, wrong visual for the line), re-draft
python3 shorts/tools/render.py $P                    # final
python3 shorts/tools/qa.py $P check                  # must exit 0
python3 shorts/tools/qa.py $P sheet final            # look again
```

Never publish a video you haven't checked frame by frame.

## 5. Hand it to Drive

Upload `out/final.mp4` to the Google Drive folder **YouTube Shorts** in My Drive. Create the folder if it's missing. Name the file exactly as the title without " #shorts", plus `.mp4`.

Use the Google Drive connector's `create_file`:
- `base64Content` = `sha256:<hash>:<abs path>` file reference
- `contentMimeType` = `video/mp4`
- `disableConversionToGoogleType` = true

## 6. Publish it

1. Use Zapier Google Drive **Find a File**. Search by that exact name with video files only, in folder "YouTube Shorts". Retry every 2 min for up to 20 min.
2. Use Zapier YouTube **Upload Video**. For the video field, pass the `file` value from the Drive search result, not the download link. Settings:
   - privacy `public`
   - title unchanged
   - description: 1–2 sentences plus 3–5 hashtags
   - 5 tags
   - category: best fit (usually Science & Technology or Education, never the default)
   - made_for_kids `false`

## 7. Log it

Append a row to `_published.md`: `| date | topic | style | title | https://youtube.com/shorts/<id> |`.

Commit the project's `script.json`, `shots.json`, `words.json` and the log, then push the branch. Media files are git-ignored.

## 8. Report

End with a short message: the title, the link, and what you fixed during QA.

If any step fails, name the step and the reason, and do NOT publish a half-finished video.
