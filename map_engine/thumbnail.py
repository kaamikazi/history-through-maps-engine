"""
thumbnail.py - makes a 1280x720 YouTube thumbnail from the map engine.

    python thumbnail.py episodes/ep03_radcliffe_line.json styles/cinematic.json out/thumb.png --text "THE LINE THAT|SPLIT BENGAL"

It renders one clean map frame (no captions, credits or draft tag), then adds big
title text.  Use '|' in --text to start a new line.
"""
import argparse, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import map_engine as me

ap = argparse.ArgumentParser()
ap.add_argument("episode"); ap.add_argument("style"); ap.add_argument("out")
ap.add_argument("--t", type=float, default=64.0, help="time (seconds) of the frame to use")
ap.add_argument("--text", default="THE LINE THAT|SPLIT BENGAL")
ap.add_argument("--data", default=str(me.HERE / "data"))
a = ap.parse_args()

ep = json.loads(Path(a.episode).read_text(encoding="utf-8"))
st = json.loads(Path(a.style).read_text(encoding="utf-8"))
# strip everything that is not the map itself
ep["events"] = [e for e in ep["events"] if e["type"] in ("fill", "line", "label")]
ep["camera"] = [{"t": 0, "center": [85.6, 23.4], "height": 8.3}]  # push the map to the right, leave room for text
ep["draft_tag"] = False; ep.pop("credit", None); ep.pop("channel_tag", None)
r = me.Renderer(ep, st, me.World(a.data), scale=1280 / 1920)
img = Image.fromarray(r.draw(a.t)).convert("RGB")

fonts = Path(me.HERE) / "fonts"
fonts = Path(me.HERE) / "fonts"
fill = st["title"]["color"]
lines = a.text.split("|")
d = ImageDraw.Draw(img)
size = 160
while True:  # shrink the font until the longest line fits in the left half of the frame
    font = ImageFont.truetype(str(fonts / st["fonts"]["title"]), size)
    if max(d.textlength(l, font=font) for l in lines) <= 640 or size < 40:
        break
    size -= 4
y = 70
for line in lines:
    d.text((50, y), line, font=font, fill=fill, stroke_width=8, stroke_fill=st["colors"]["title_dim"])
    y += int(size * 0.92)
img.save(a.out)
print("Saved", a.out)
