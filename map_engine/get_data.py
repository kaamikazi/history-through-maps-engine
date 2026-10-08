"""
get_data.py - downloads the Natural Earth map files the engine needs (public domain).

Run it once:   python get_data.py
It saves the files into the 'data' folder next to this script.
"""
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master"
FILES = {
    "10m_cultural": ["ne_10m_admin_0_countries", "ne_10m_admin_1_states_provinces"],
    "10m_physical": ["ne_10m_rivers_lake_centerlines"],
}

data = Path(__file__).resolve().parent / "data"
data.mkdir(exist_ok=True)
for folder, stems in FILES.items():
    for stem in stems:
        for ext in ("shp", "dbf", "shx"):
            target = data / f"{stem}.{ext}"
            if target.exists():
                continue
            print("Downloading", target.name)
            urllib.request.urlretrieve(f"{BASE}/{folder}/{stem}.{ext}", target)
print("Done. Natural Earth data is in", data)
