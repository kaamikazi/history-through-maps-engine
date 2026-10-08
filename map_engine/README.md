# History Through Maps - map engine

Turns an **episode file** (what happens, when) plus a **style file** (how it looks) into an MP4.
All map shapes are Natural Earth (public domain). Fonts are SIL Open Font License.

## One-time setup
1. Install Python 3.10+ and ffmpeg (ffmpeg must be on your PATH).
2. `pip install -r requirements.txt`
3. `python get_data.py`   (downloads about 50 MB of Natural Earth files into `data/`)

## The look: brand styles
The channel identity is the repo https://github.com/kaamikazi/History-C (antique engraved atlas).
- `styles/lamplight.json`  dark walnut theme - use this for **videos**
- `styles/paper.json`      light paper theme - for **thumbnails and stills**
Colours come from `brand/tokens.json` (copied from that repo) by name, e.g. `"@ink"`, `"@territory"`.
The old `cinematic.json` and `antique.json` are kept but are no longer used for uploads.

## Make things
```
# one test frame (fast)
python map_engine.py episodes/ep03_radcliffe_line.json --style styles/lamplight.json --still 40 --scale 0.5 --out out/test.png

# full video, 1080p (slow: about 2 frames a second)      add  --scale 0.6667  for a 720p draft
python map_engine.py episodes/ep03_radcliffe_line.json --style styles/lamplight.json --out out/ep03_lamplight_1080p.mp4

# thumbnail 1280x720 (OLD look only - a brand thumbnail with the cartouche is not built yet)
python thumbnail.py episodes/ep03_radcliffe_line.json styles/cinematic.json out/thumb.png --text "THE LINE THAT|SPLIT BENGAL"
```

## Add the voice (narration)
The voice reads the caption text aloud (Google Gemini text-to-speech, voice "Charon").
```
# 1. make one voice clip per caption, then one narration.wav as long as the video
python make_voice.py episodes/ep03_radcliffe_line.json --env "E:/arts and stuff/TTS automation/.env"

# 2. put it into a finished video (makes ..._voice.mp4, the original is kept)
python add_voice.py out/ep03_lamplight_1080p.mp4 out/voice/ep03_radcliffe_line/narration.wav
```
- It also writes `out/voice/<episode>/<episode>.srt`: subtitles for YouTube (Studio > Subtitles > Upload file).
  Brand styles show no caption boxes on screen, so upload this file with every video.
- Before the voice exists you can make rough subtitles from the caption times:
  `python make_voice.py episodes/ep03_radcliffe_line.json --subtitles-only`
- Clips are saved in `out/voice/<episode>/` and only re-made when a caption's text changes.
- `make_voice.py` prints a timing check. If a line is TOO LONG, give that caption more time in the episode JSON.
- The free Gemini key allows only about 10 voice requests a day. If it stops, run it again tomorrow
  (finished clips are kept), or turn on billing in Google AI Studio.
- `add_voice.py` sets the loudness to -14 LUFS, the level YouTube plays at.

## Folders
- `map_engine.py`   the engine (comments explain each part)
- `brand_parts.py`  the brand pieces: hatching, small-capital text, lower third, chapter card, sting, end screen
- `brand/`          tokens.json: the brand colours (source: History-C repo)
- `styles/`         lamplight.json, paper.json (brand); cinematic.json, antique.json (old)
- `episodes/`       one JSON per episode
- `fonts/`          fonts + licences
- `out/`            your renders

## Writing a new episode
Copy `episodes/ep03_radcliffe_line.json`. The parts:
- `regions`  named shapes, picked with selectors: `admin0:India`, `admin1:India/West Bengal`, `union:a+b`
- `lines`    a border between two shapes, drawn as an animated line
- `camera`   keyframes: time, centre [lon, lat], height in degrees (smaller = more zoomed in)
- `events`   each has a type and a start time `t` (seconds):

| type | what it does | main fields |
|---|---|---|
| `caption` | one spoken line (narration + subtitles; not drawn in brand styles) | `text`, `dur` |
| `fill` | colours a region. Brand colours: `territory` (the one red region), `second` (verdigris), `contested` (dashed + hatched) | `region`, `color`, `dur`, `out` |
| `line` | draws a border on, like an engraver | `name`, `dur` |
| `label` | map label: `city`, `region` or `water` | `text`, `lon`, `lat`, `out`, optional `size`, `dx`, `dy` |
| `stamp` | date-and-place kicker, top left, e.g. "Anno 1947 · Bengal" | `text`, `dur` |
| `year` | date wipe: the year counts from one date to the next | `from`, `to`, `dur`, `prefix`, `hold` |
| `lower_third` | plate naming a place/date (kicker max 3 words, headline max 8) | `kicker`, `headline`, optional `year`, `pos` |
| `chapter` | full-screen chapter card | `number`, `title` (use `
` for 2 lines), `years`, `dur` |
| `sting` | 2.5 s logo sting (put it at about 0:20, after the cold open) | `dur` |
| `cite` | short source line at the bottom while a fact is on screen | `text`, `dur` |
| `endscreen` | last 15-20 s: plates for YouTube's end-screen videos + subscribe | `next`, `dur` |
| `title` | big title card | `title`, `subtitle`, `kicker`, `dim` |

Brand video formula (brand/strategy.md): cold open 0-20 s (one map, one date, no logo) -> sting ->
chapters, each starting with a chapter card -> return to the present (same crop as the first map) -> end screen.

Rules from the brand: one red territory per frame; a number on screen always has its unit and year;
dates and places first; say "historians estimate" / "contested" where it is.

Remember: the base map uses modern outlines. A video about 1850 needs researched historical borders, drawn from cited sources.
