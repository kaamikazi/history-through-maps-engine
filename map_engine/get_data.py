"""
get_data.py - downloads the Natural Earth map files the engine needs (public domain).

Run it once:   python get_data.py
It saves the files into the 'data' folder next to this script.

Optional hill shading (terrain) for brand styles, about 24 MB more:
               python get_data.py --relief
"""
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master"
FILES = {
    "10m_cultural": ["ne_10m_admin_0_countries", "ne_10m_admin_1_states_provinces"],
    "10m_physical": ["ne_10m_rivers_lake_centerlines"],
}
# Natural Earth 1:10m shaded relief, medium size (public domain), from Natural Earth's own download server
RELIEF_URL = "https://naciscdn.org/naturalearth/10m/raster/SR_LR.zip"

data = Path(__file__).resolve().parent / "data"
data.mkdir(exist_ok=True)


def download(url, target):
    """Download to a temporary name first, so a broken download never looks finished."""
    part = target.with_name(target.name + ".part")
    print("Downloading", target.name)
    urllib.request.urlretrieve(url, part)
    part.replace(target)


for folder, stems in FILES.items():
    for stem in stems:
        for ext in ("shp", "dbf", "shx"):
            target = data / f"{stem}.{ext}"
            if not target.exists():
                download(f"{BASE}/{folder}/{stem}.{ext}", target)

if "--relief" in sys.argv:
    tif = data / "SR_LR.tif"
    if not tif.exists():
        zip_path = data / "SR_LR.zip"
        if not zip_path.exists():
            download(RELIEF_URL, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            # take ONLY the picture out of the zip, by its plain file name (nothing else is unpacked)
            member = next(n for n in z.namelist() if n.lower().endswith("sr_lr.tif"))
            with z.open(member) as src, open(tif, "wb") as dst:
                dst.write(src.read())
        zip_path.unlink()  # the zip is no longer needed
    print("Hill shading picture:", tif)

print("Done. Natural Earth data is in", data)
