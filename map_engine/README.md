# History Through Maps - map engine

Turns an **episode file** (what happens, when) plus a **style file** (how it looks) into an MP4.
All map shapes are Natural Earth (public domain). Fonts are SIL Open Font License.

## One-time setup
1. Install Python 3.10+ and ffmpeg (ffmpeg must be on your PATH).
2. `pip install -r requirements.txt`
3. `python get_data.py`   (downloads about 100 MB of Natural Earth files into `data/`)

## Make things
```
# one test frame (fast)
python map_engine.py episodes/ep03_radcliffe_line.json --style styles/cinematic.json --still 50 --scale 0.5 --out out/test.png

# full video, 1080p (slow, about 40 min)      add  --scale 0.6667  for a 720p draft
python map_engine.py episodes/ep03_radcliffe_line.json --style styles/cinematic.json --out out/ep03_cinematic.mp4

# thumbnail 1280x720
python thumbnail.py episodes/ep03_radcliffe_line.json styles/cinematic.json out/thumb.png --text "THE LINE THAT|SPLIT BENGAL"
```
Swap `cinematic` for `antique` to change the look.

## Folders
- `map_engine.py`   the engine (comments explain each part)
- `styles/`         cinematic.json, antique.json  (colours, fonts, sizes)
- `episodes/`       one JSON per episode
- `fonts/`          fonts + licences
- `out/`            your renders

## Writing a new episode
Copy `episodes/ep03_radcliffe_line.json`. The parts:
- `regions`  named shapes, picked with selectors: `admin0:India`, `admin1:India/West Bengal`, `union:a+b`
- `lines`    a border between two shapes, drawn as an animated line
- `camera`   keyframes: time, centre [lon, lat], height in degrees (smaller = more zoomed in)
- `events`   `fill`, `line`, `label`, `caption`, `stamp`, `title`, each with a start time `t`

Remember: the base map uses modern outlines. A video about 1850 needs researched historical borders, drawn from cited sources.
