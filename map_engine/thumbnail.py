"""
thumbnail.py - makes a 1280x720 YouTube thumbnail from the map engine.

Brand look (use the Paper style, as the brand asks for thumbnails):
    python thumbnail.py episodes/ep03_radcliffe_line.json styles/paper.json out/ep03_thumb.png --kicker "Anno 1947 · Bengal" --text "Bengal,|split in two"

It renders one clean map frame (no labels, captions, credits or draft tag) with the map pushed to
the right, then puts the brand cartouche on the left 44%: kicker, title, logo and wordmark.
Use '|' in --text to start a new line. Brand rule: the title is 4 words or fewer.

It also saves a tiny 168x94 copy (..._squint.png): the size YouTube shows in lists.
At that size the red territory and the title must both still be readable.

Old looks (cinematic / antique) still work for episodes that use their fill names.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import map_engine as me
from brand_parts import load_style, make_thumbnail_card

ap = argparse.ArgumentParser()
ap.add_argument("episode")
ap.add_argument("style")
ap.add_argument("out")
ap.add_argument("--t", type=float, default=80.0, help="time (seconds) of the map frame to use")
ap.add_argument("--text", default="Bengal,|split in two", help="title; '|' starts a new line")
ap.add_argument("--kicker", default="Anno 1947 · Bengal", help="small-capitals date and place (brand only)")
ap.add_argument("--center", default="85.6,23.4", help="map centre lon,lat (pushes the map right of the cartouche)")
ap.add_argument("--height", type=float, default=8.3, help="map zoom: height of the view in degrees")
ap.add_argument("--data", default=str(me.HERE / "data"))
a = ap.parse_args()

ep = json.loads(Path(a.episode).read_text(encoding="utf-8"))
st = load_style(a.style)
# keep only the map itself: fills and lines (no labels, captions, plates or credits)
ep["events"] = [e for e in ep["events"] if e["type"] in ("fill", "line")]
lon, lat = (float(v) for v in a.center.split(","))
ep["camera"] = [{"t": 0, "center": [lon, lat], "height": a.height}]
ep["draft_tag"] = False
ep.pop("credit", None)
ep.pop("channel_tag", None)

words = len(a.text.replace("|", " ").split())
if st.get("brand") and words > 4:
    print(f"WARNING: the title has {words} words; the brand allows 4 or fewer.")

r = me.Renderer(ep, st, me.World(a.data), scale=1280 / 1920)
if st.get("brand"):
    make_thumbnail_card(r.ov, r.font_files, r.palette, a.kicker, a.text.replace("|", "\n"))
img = Image.fromarray(r.draw(a.t)).convert("RGB")

if not st.get("brand"):  # old looks: big title text drawn with Pillow, as before
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
squint = Path(a.out).with_name(Path(a.out).stem + "_squint.png")
img.resize((168, 94), Image.LANCZOS).save(squint)
print("Saved", a.out, "and", squint)
