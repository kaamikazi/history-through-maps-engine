# History Through Maps - map engine

Turns an **episode file** (what happens, when) plus a **style file** (how it looks) into an MP4.
All map shapes are Natural Earth (public domain). Fonts are SIL Open Font License.

## One-time setup
1. Install Python 3.10+ and ffmpeg (ffmpeg must be on your PATH).
2. `pip install -r requirements.txt`
3. `python get_data.py`   (downloads about 50 MB of Natural Earth files into `data/`)
4. `python get_data.py --relief`   (optional, 24 MB download: hill shading for the brand styles)

## The look: brand styles
The channel identity is the repo https://github.com/kaamikazi/History-C (antique engraved atlas).
- `styles/lamplight.json`  dark walnut theme - use this for **videos**
- `styles/paper.json`      light paper theme - for **thumbnails and stills**
Colours come from `brand/tokens.json` (copied from that repo) by name, e.g. `"@ink"`, `"@territory"`.
The old `cinematic.json` and `antique.json` are kept but are no longer used for uploads.

Territory edges: the brand styles use `"fill_edges": "soft"` - territories are painted as a see-through
watercolour wash with a soft, slightly ragged edge (like a hand-coloured atlas), stopping crisply at the
coast; in a `territory` timeline, gained land spreads outward from the old border. Set `"fill_edges": "hard"`
in the style for the engraved look instead (hatching + ink outline). Note: brand-book.md says "no gradients,
no blur"; soft edges were asked for on 2026-10-09, so update the brand book if this becomes the house look.

## Make things
```
# one test frame (fast)
python map_engine.py episodes/ep03_radcliffe_line.json --style styles/lamplight.json --still 40 --scale 0.5 --out out/test.png

# full video, 1080p. --jobs 6 renders 6 parts at once (6 CPU cores, about 1 GB memory each) and joins them.
# Without --jobs it does about 2 frames a second.      add  --scale 0.6667  for a 720p draft
python map_engine.py episodes/ep03_radcliffe_line.json --style styles/lamplight.json --jobs 6 --out out/ep03_lamplight_1080p.mp4

# YouTube description: hook, chapter timestamps, sources from source_log.csv, About text,
# plus a "check before uploading" list (anything still marked to verify)
python make_description.py episodes/ep03_radcliffe_line.json

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

# 2b. ... with a music bed (19 dB under the voice) and the sting sound at the sting's time
python make_sting_sound.py          (once: makes out/audio/sting.wav - our own sound, no licence needed)
python add_voice.py out/ep03_lamplight_1080p.mp4 out/voice/ep03_radcliffe_line/narration.wav --music music/track.mp3 --sting-sfx out/audio/sting.wav --episode episodes/ep03_radcliffe_line.json
```
- It also writes `out/voice/<episode>/<episode>.srt`: subtitles for YouTube (Studio > Subtitles > Upload file).
  Brand styles show no caption boxes on screen, so upload this file with every video.
- Before the voice exists you can make rough subtitles from the caption times:
  `python make_voice.py episodes/ep03_radcliffe_line.json --subtitles-only`
- Clips are saved in `out/voice/<episode>/` and only re-made when a caption's text changes.
- `make_voice.py` prints a timing check. If a line is TOO LONG, give that caption more time in the episode JSON.
- The free Gemini key allows only about 10 voice requests a day. If it stops, run it again tomorrow
  (finished clips are kept), or turn on billing in Google AI Studio.
- `add_voice.py` sets the voice to -14 LUFS (YouTube's level), music 19 dB under it (brand: 18-20 dB),
  and keeps peaks under about -1 dB. Music must be cleared for monetized use (e.g. YouTube Audio Library):
  log it in source_log.csv and in the episode's `music` list, so make_description.py credits it.

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
- `regions`  named shapes, picked with selectors: `admin0:India`, `admin1:India/West Bengal`, `union:a+b`,
             or `file:episodes/shapes/<episode>/<name>.geojson` for a shape WE drew from cited sources
             (lon/lat GeoJSON; keep a "source" note in each file's properties and log it in source_log.csv)
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
| `territory` | one territory through several periods: gained land hatches in, lost land fades and leaves a dashed ghost border (no invented in-between borders) | `periods` [{t, region}], `color`, `change`, `ghost`, `out` |
| `image` | an artwork in an engraved plate over the dimmed map, slow pan/zoom, credit line. `tone: false` keeps original colours | `file`, `credit`, `dur`, `pan` {from:[cx,cy,zoom], to:[...]}, `pos`, `plate` [w,h] |
| `map_overlay` | a scanned old map pinned to 3+ known points and faded over the map | `file`, `points` [[x px, y px, lon, lat], ...], `alpha`, `tone`, `out` |
| `route` | arrow engraved along a path (migration, campaign, trade). Dashed if `uncertain` | `points` [[lon,lat],...], `dur`, `id`, `uncertain`, `out` |
| `troops` | formation of soldier figures we drew (`infantry`, `archers`, `cavalry`) in a side's colour, with a banner; faces the way its route goes. The figures are a picture, not the army's size: put the sourced number in `label` | `kind`, `rows`, `cols`, `color` ("@territory" / "@verdigris"), `lon`/`lat` or `follow`, `facing`, `label`, `size_px`, `out` |
| `portrait` | a general's / ruler's portrait (public domain, logged) in an engraved oval medallion with name, dates and credit; sits beside a place or follows a route, with a leader line | `file`, `name`, `dates`, `credit`, `lon`/`lat` or `follow`, `offset` [dx, dy], `face` [x, y], `zoom`, `size_px`, `tone`, `out` |
| `marker` | map symbol: `battle`, `site`, `capital` or `army` (plate with `name` + `size`) | `kind`, `lon`/`lat` or `follow` (a route `id`), `label`, `out` |
| `endscreen` | last 15-20 s: plates for YouTube's end-screen videos + subscribe | `next`, `dur` |
| `title` | big title card | `title`, `subtitle`, `kicker`, `dim` |

Pictures go in `assets/<episode>/`. Only public-domain / CC0 / openly licensed pictures, each logged in
source_log.csv (the brand also asks for the artist, title, date and collection in the `credit`).

Episode fields used by `make_description.py`: `source_video` (the name used in source_log.csv),
`hook` (first line), `opening_title` (name of the 0:00 chapter), `chapters_extra` ([{t, title}]), `music`.

`episodes/ep00_feature_demo.json` shows every feature with placeholder text (never publish it).

Brand video formula (brand/strategy.md): cold open 0-20 s (one map, one date, no logo) -> sting ->
chapters, each starting with a chapter card -> return to the present (same crop as the first map) -> end screen.

Rules from the brand: one red territory per frame; a number on screen always has its unit and year;
dates and places first; say "historians estimate" / "contested" where it is.

Remember: the base map uses modern outlines. A video about 1850 needs researched historical borders, drawn from cited sources.
