"""
map_engine.py  -  History Through Maps animation engine
=======================================================

What it does
------------
Reads TWO small JSON files and turns them into an MP4 video:

  1. an EPISODE file  (what happens, and when)  e.g. episodes/ep03_radcliffe_line.json
  2. a STYLE file     (how it looks)            e.g. styles/antique.json or styles/cinematic.json

The same episode can be rendered in either style, so one set of data gives
you two different looks (or one look per channel).

All map shapes come from Natural Earth (public domain, no credit required).
Run  `python get_data.py`  once to download them.

Quick start
-----------
    pip install -r requirements.txt
    python get_data.py
    python map_engine.py episodes/ep03_radcliffe_line.json --style styles/cinematic.json --out out/ep03_cinematic.mp4

Handy options
-------------
    --scale 0.5          render at half size (960x540) for fast test runs
    --still 42           save ONE frame at t=42 seconds as a PNG (use --out x.png)
    --start 30 --end 50  render only part of the timeline

You need ffmpeg installed and available on the PATH to make MP4 files.
"""

import argparse
import json
import math
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")  # draw to memory, no window
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import shapefile  # pyshp: reads Natural Earth .shp files
from matplotlib.collections import LineCollection
from matplotlib.font_manager import FontProperties
from matplotlib.patches import PathPatch, Polygon as MplPolygon, Rectangle, Circle
from matplotlib.path import Path as MPath
from PIL import Image
from shapely.geometry import box, shape
from shapely.geometry.polygon import orient
from shapely.ops import linemerge, unary_union
from shapely import affinity

# The "History Through Maps" brand pieces (hatching, small-capital text, plates, sting).
from brand_parts import (PT, Hatcher, Marker, PathText, Route, Sting, load_style, make_chapter_card,
                         make_end_screen, make_lower_third, make_title_card)

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# 1.  PROJECTION
# --------------------------------------------------------------------------
# A map is flat, the Earth is not.  For a region like South Asia a very simple
# trick works well: keep latitude as it is, and squeeze longitude by cos(lat)
# so that shapes look right.  LAT0 is the latitude we squeeze for.
LAT0 = 24.0
XS = math.cos(math.radians(LAT0))


def proj_xy(lon, lat):
    """lon/lat in degrees -> flat map coordinates."""
    return lon * XS, lat


def proj_geom(geom):
    """Same idea for a whole shapely shape."""
    return affinity.scale(geom, xfact=XS, yfact=1.0, origin=(0, 0))


# --------------------------------------------------------------------------
# 2.  SMALL HELPERS (easing, fading)
# --------------------------------------------------------------------------
def smooth(x):
    """Smooth 0->1 curve (starts and ends gently)."""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def fade(t, t_in, dur_in, t_out=None, dur_out=0.8):
    """Opacity (0..1) of something that fades in at t_in and optionally out at t_out."""
    a = smooth((t - t_in) / max(dur_in, 1e-6))
    if t_out is not None:
        a *= 1.0 - smooth((t - t_out) / max(dur_out, 1e-6))
    return a


def geom_to_path(geom):
    """shapely polygon(s) -> one matplotlib Path (holes are supported)."""
    verts, codes = [], []
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        p = orient(p)  # outer ring counter-clockwise, holes clockwise
        for ring in [p.exterior, *p.interiors]:
            xy = np.asarray(ring.coords)
            c = np.full(len(xy), MPath.LINETO, dtype=np.uint8)
            c[0] = MPath.MOVETO
            c[-1] = MPath.CLOSEPOLY
            verts.append(xy)
            codes.append(c)
    if not verts:
        return MPath(np.zeros((1, 2)), [MPath.MOVETO])
    return MPath(np.concatenate(verts), np.concatenate(codes))


def lines_of(geom):
    """Any shapely line/polygon -> list of Nx2 arrays (for LineCollection)."""
    out = []

    def walk(g):
        if g.is_empty:
            return
        if g.geom_type == "LineString" or g.geom_type == "LinearRing":
            out.append(np.asarray(g.coords))
        elif g.geom_type == "Polygon":
            walk(g.exterior)
            for r in g.interiors:
                walk(r)
        elif hasattr(g, "geoms"):
            for x in g.geoms:
                walk(x)

    walk(geom)
    return out


def haversine_km(lonlat):
    """Length of a lon/lat polyline in kilometres."""
    p = np.radians(np.asarray(lonlat))
    dlon = np.diff(p[:, 0])
    dlat = np.diff(p[:, 1])
    a = np.sin(dlat / 2) ** 2 + np.cos(p[:-1, 1]) * np.cos(p[1:, 1]) * np.sin(dlon / 2) ** 2
    return float(np.sum(6371.0088 * 2 * np.arcsin(np.sqrt(a))))


# --------------------------------------------------------------------------
# 3.  MAP DATA  (Natural Earth shapefiles)
# --------------------------------------------------------------------------
class World:
    """Loads Natural Earth data inside a big box around the area we need."""

    CLIP = (50.0, 0.0, 112.0, 42.0)  # west, south, east, north (degrees)

    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        clip = box(*self.CLIP)
        self.countries = self._read("ne_10m_admin_0_countries", clip, "NAME")
        self.admin1 = self._read("ne_10m_admin_1_states_provinces", box(80, 15, 100, 32), "name", extra="admin")
        self.rivers = self._read("ne_10m_rivers_lake_centerlines", clip, "name")

    def _read(self, stem, clip, name_field, extra=None):
        path = self.dir / stem
        if not path.with_suffix(".shp").exists():
            sys.exit(f"Missing {stem}.shp - run  python get_data.py  first.")
        r = shapefile.Reader(str(path))
        fields = [f[0] for f in r.fields[1:]]
        rows = []
        for sr in r.iterShapeRecords():
            bb = sr.shape.bbox  # quick reject before the slow conversion
            if bb[2] < clip.bounds[0] or bb[0] > clip.bounds[2] or bb[3] < clip.bounds[1] or bb[1] > clip.bounds[3]:
                continue
            rec = dict(zip(fields, sr.record))
            g = shape(sr.shape.__geo_interface__)
            if not g.is_valid:
                g = g.buffer(0)
            g = g.intersection(clip)
            if g.is_empty:
                continue
            rows.append({"name": rec.get(name_field), "extra": rec.get(extra) if extra else None, "geom": g})
        return rows

    # ---- selectors:  "admin0:India", "admin1:India/West Bengal", "union:a+b" ----
    def select(self, spec):
        spec = spec.strip()
        if spec.startswith("union:"):
            parts = spec[len("union:"):].split("+")
            return unary_union([self.select(p) for p in parts])
        if spec.startswith("admin0:"):
            name = spec[len("admin0:"):]
            geoms = [c["geom"] for c in self.countries if c["name"] == name]
        elif spec.startswith("admin1:"):
            country, name = spec[len("admin1:"):].split("/")
            geoms = [a["geom"] for a in self.admin1 if a["name"] == name and a["extra"] == country]
        else:
            raise ValueError(f"Unknown selector: {spec}")
        if not geoms:
            raise ValueError(f"Nothing found for selector: {spec}")
        return unary_union(geoms)

    def border_between(self, spec_a, spec_b, start_hint):
        """
        The shared border of two shapes as ONE ordered polyline (lon/lat),
        starting at the end closest to `start_hint` = [lon, lat].
        Used for things like the Radcliffe Line (= today's India-Bangladesh border).
        """
        a, b = self.select(spec_a), self.select(spec_b)
        shared = a.boundary.intersection(b.buffer(1e-3))
        pieces = []

        def collect(g):
            if g.geom_type == "LineString":
                pieces.append(g)
            elif hasattr(g, "geoms"):
                for x in g.geoms:
                    collect(x)

        collect(shared)
        merged = linemerge(pieces)
        pieces = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
        pieces = [np.asarray(p.coords) for p in pieces if p.length > 0.02]  # drop tiny slivers

        # Chain the pieces: start nearest the hint, then always go to the nearest unused piece.
        cur = np.asarray(start_hint, float)
        chain = []
        while pieces:
            best = None
            for i, p in enumerate(pieces):
                for flip in (False, True):
                    pp = p[::-1] if flip else p
                    d = np.hypot(*(pp[0] - cur))
                    if best is None or d < best[0]:
                        best = (d, i, pp)
            _, i, pp = best
            chain.append(pp)
            cur = pp[-1]
            pieces.pop(i)
        return np.concatenate(chain)


# --------------------------------------------------------------------------
# 4.  THE RENDERER
# --------------------------------------------------------------------------
W0, H0 = 1920, 1080  # full-size video frame


class Renderer:
    def __init__(self, episode, style, world, scale=1.0, style_dir=HERE):
        self.ep, self.st, self.world = episode, style, world
        self.scale = scale
        self.W, self.H = int(W0 * scale), int(H0 * scale)
        self.fonts_dir = HERE / "fonts"
        # Brand styles (lamplight / paper) switch on the engraved-atlas look.
        self.brand = bool(style.get("brand"))
        # Brand styles name fonts by their job (display, caps, body...). Full file paths:
        self.font_files = {k: self.fonts_dir / v for k, v in style.get("fonts", {}).items()}
        self.palette = style.get("palette", {})  # every brand colour, by token name
        self.events = sorted(episode["events"], key=lambda e: e["t"])
        self.cam_keys = sorted(episode["camera"], key=lambda k: k["t"])
        self.duration = float(episode["duration"])
        self.fps = int(episode.get("fps", 30))

        self.fig = plt.figure(figsize=(W0 / 100, H0 / 100), dpi=100 * scale)
        self.fig.patch.set_facecolor(self.st["colors"]["sea"])
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_facecolor(self.st["colors"]["sea"])
        self.ax.axis("off")
        self.ov = self.fig.add_axes([0, 0, 1, 1], zorder=10)  # overlay for captions / titles
        self.ov.set_xlim(0, W0)
        self.ov.set_ylim(H0, 0)
        self.ov.axis("off")
        self.ov.patch.set_alpha(0)

        self._build_geometry()
        self._build_regions_and_lines()
        self._build_event_artists()
        self._build_decorations()

    # ---------- fonts ----------
    def font(self, key, size):
        return FontProperties(fname=str(self.fonts_dir / self.st["fonts"][key]), size=size)

    # ---------- base map ----------
    def _build_geometry(self):
        c = self.st["colors"]
        s = self.st
        # Two detail levels: coarse for wide shots, fine for close-ups
        self.lods = []
        for tol, min_h, max_h in ((0.02, 11.0, 999.0), (0.0035, 0.0, 11.0)):
            lod = {"min_h": min_h, "max_h": max_h, "artists": []}
            land_geoms = [proj_geom(x["geom"].simplify(tol)) for x in self.world.countries]
            land_union = unary_union(land_geoms)
            # water-lines (antique): ripples drawn in the sea around the coast
            if s.get("waterlines"):
                dists = s["waterlines"]["wide"] if tol > 0.01 else s["waterlines"]["close"]
                for i, d in enumerate(dists):
                    ring = land_union.buffer(d, resolution=4)
                    a = LineCollection(lines_of(ring), colors=c["waterline"], linewidths=s["waterlines"]["width"], zorder=1)
                    a.set_alpha(s["waterlines"]["alpha"] * (1 - i / (len(dists) + 1)))
                    self.ax.add_collection(a)
                    lod["artists"].append(a)
            land = PathPatch(geom_to_path(land_union), fc=c["land"], ec="none", zorder=2)
            self.ax.add_patch(land)
            lod["artists"].append(land)
            lod["land"] = land  # kept so the land hatching can be clipped to it
            # graticule (brand): thin lines every few degrees, like on an engraved atlas
            if s.get("graticule"):
                g = s["graticule"]
                step = dict(g["steps"]).get(min_h, 5)  # e.g. every 5 degrees wide, every 1 degree close
                west, south, east, north = World.CLIP
                grid = []
                for lon in np.arange(math.ceil(west / step) * step, east + 1e-9, step):
                    grid.append(np.array([proj_xy(lon, south), proj_xy(lon, north)]))
                for lat in np.arange(math.ceil(south / step) * step, north + 1e-9, step):
                    grid.append(np.array([proj_xy(west, lat), proj_xy(east, lat)]))
                gl = LineCollection(grid, colors=g["color"], linewidths=g["width_px"] * PT, alpha=g.get("alpha", 1), zorder=2.2)
                self.ax.add_collection(gl)
                lod["artists"].append(gl)
            # country borders (thin) and coastline (thicker)
            border_lines = []
            for g in land_geoms:
                border_lines += lines_of(g)
            b = LineCollection(border_lines, colors=c["border"], linewidths=s["widths"]["border"], zorder=6)
            self.ax.add_collection(b)
            lod["artists"].append(b)
            if s.get("glow"):
                for lw, al in ((s["widths"]["coast"] * 4, 0.10), (s["widths"]["coast"] * 2.2, 0.18)):
                    gl = LineCollection(lines_of(land_union.boundary), colors=c["coast"], linewidths=lw, alpha=al, zorder=6.5)
                    self.ax.add_collection(gl)
                    lod["artists"].append(gl)
            coast = LineCollection(lines_of(land_union.boundary), colors=c["coast"], linewidths=s["widths"]["coast"], zorder=7)
            self.ax.add_collection(coast)
            lod["artists"].append(coast)
            # rivers
            rv = [proj_geom(r["geom"].simplify(tol)) for r in self.world.rivers]
            rl = []
            for g in rv:
                rl += lines_of(g)
            riv = LineCollection(rl, colors=c["river"], linewidths=s["widths"]["river"], zorder=3, capstyle="round",
                                 alpha=s.get("river_alpha", 1.0))
            self.ax.add_collection(riv)
            lod["artists"].append(riv)
            self.lods.append(lod)

        # state / province outlines: only visible when zoomed in (alpha follows zoom)
        a1 = []
        for a in self.world.admin1:
            if a["extra"] in ("India", "Bangladesh"):
                a1 += lines_of(proj_geom(a["geom"].simplify(0.004)))
        self.admin1_art = LineCollection(a1, colors=c["admin1"], linewidths=s["widths"]["admin1"], linestyles=(0, (4, 3)), zorder=4)
        self.ax.add_collection(self.admin1_art)

        # engraved hatching over all land (brand). It is clipped to whichever land shape is showing.
        self.land_hatch = None
        self._lod_shown = None
        if s.get("land_hatch"):
            h = s["land_hatch"]
            self.land_hatch = Hatcher(self.ax, self.lods[0]["land"], h["angle"], h["spacing_px"], h["width_px"],
                                      h["color"], zorder=2.1)

    # ---------- named regions and lines from the episode ----------
    def _build_regions_and_lines(self):
        self.regions = {}
        for name, spec in self.ep.get("regions", {}).items():
            g = proj_geom(self.world.select(spec).simplify(0.003))
            self.regions[name] = g
        self.lines = {}
        for name, d in self.ep.get("lines", {}).items():
            ll = self.world.border_between(d["between"][0], d["between"][1], d["start"])
            ll = np.asarray(ll)
            xy = np.column_stack([ll[:, 0] * XS, ll[:, 1]])
            seg = np.hypot(*np.diff(xy, axis=0).T)
            cum = np.concatenate([[0], np.cumsum(seg)])
            km = haversine_km(ll)
            self.lines[name] = {"xy": xy, "cum": cum, "km": km}
            print(f"  line '{name}': {len(xy)} points, ~{km:,.0f} km (from simplified Natural Earth data)")

    # ---------- one artist per event ----------
    def _build_event_artists(self):
        c, s = self.st["colors"], self.st
        self.art = {}
        self.routes = {}  # route id -> (Route, its event), for markers that follow a route
        for i, e in enumerate(self.events):
            ty = e["type"]
            if ty == "fill":
                f = s["fills"][e["color"]]
                shape = self.regions[e["region"]]
                path = geom_to_path(shape)
                p = PathPatch(path, fc=f["color"], ec=f.get("edge", "none"),
                              lw=f.get("edge_width", 0), zorder=2.5 + i * 0.001)
                p.set_alpha(0)
                self.ax.add_patch(p)
                extra = {}
                if f.get("hatch"):  # brand: engraved lines over the territory, clipped to its shape
                    h = f["hatch"]
                    extra["hatch"] = Hatcher(self.ax, p, h["angle"], h["spacing_px"], h["width_px"], h["color"],
                                             zorder=2.6 + i * 0.001, shape_bounds=shape.bounds)
                if f.get("outline"):  # brand: the territory is always outlined in ink (dashed if contested)
                    o = PathPatch(path, fc="none", ec=f["outline"], lw=f.get("outline_px", 2) * PT,
                                  linestyle=(0, (6, 4)) if f.get("dashed") else "solid", joinstyle="round",
                                  zorder=2.7 + i * 0.001)
                    o.set_alpha(0)
                    self.ax.add_patch(o)
                    extra["outline"] = o
                self.art[i] = (p, f["alpha"], extra)
            elif ty == "line":
                ln = self.lines[e["name"]]
                ls = s["line"]
                layers = []
                for lw, al, col in ls["layers"]:
                    (h,) = self.ax.plot([], [], color=ls[col] if col in ls else col, lw=lw, alpha=al, zorder=8,
                                        solid_capstyle="round", solid_joinstyle="round")
                    layers.append((h, al))
                (tip,) = self.ax.plot([], [], marker="o", ms=ls["tip_size"], mfc=ls["tip"], mec=ls["tip_edge"], mew=1.5, zorder=9)
                self.art[i] = (layers, tip)
            elif ty == "label":
                kind = s["labels"][e.get("kind", "city")]
                x, y = proj_xy(e["lon"], e["lat"])
                m = None
                if kind.get("marker"):
                    (m,) = self.ax.plot([x], [y], marker=kind["marker"], ms=kind["marker_size"], mfc=kind["marker_fc"],
                                        mec=kind["marker_ec"], mew=1.4, zorder=10.5, alpha=0)
                if "tracking_px" in kind:
                    # Brand label: drawn on the overlay as a shape (so small capitals can be letter-spaced),
                    # and moved every frame to follow its place on the map.
                    t = PathText(self.ov, e["text"], self.font_files[kind["font"]], e.get("size", kind["size_px"]),
                                 kind["color"], tracking=kind["tracking_px"], ha=e.get("ha", kind.get("ha", "left")),
                                 line_height=kind.get("line_height"), zorder=2)
                    t.set_alpha(0)
                    dx, dy = e.get("dx", kind.get("dx", 0)), e.get("dy", kind.get("dy", 0))
                    self.art[i] = ("path", t, m, kind.get("alpha", 1.0), (x, y), (dx, dy))
                    continue
                size = e.get("size", kind["size"]) * 1.0
                text = e["text"]
                lines = text.split("\n")
                if kind.get("tracking"):  # wide letter-spacing, line by line
                    lines = ["   ".join(" ".join(w) for w in ln.split(" ")) for ln in lines]
                halo = [pe.withStroke(linewidth=kind.get("halo_w", 4), foreground=kind["halo"])] if kind.get("halo") else []
                dx, dy = e.get("dx", kind.get("dx", 0)), e.get("dy", kind.get("dy", 0))
                ha = e.get("ha", kind.get("ha", "left"))
                t = self.ax.annotate("\n".join(lines), (x, y), xytext=(dx, dy), textcoords="offset points",
                                     ha=ha, va="center", color=kind["color"], zorder=11, annotation_clip=False,
                                     fontproperties=self.font(kind["font"], size), path_effects=halo, linespacing=0.95)
                t.set_alpha(0)
                self.art[i] = (t, m, kind.get("alpha", 1.0))
            elif ty == "caption":
                # Brand styles show no caption boxes: the words are spoken (make_voice.py)
                # and uploaded to YouTube as subtitles instead.
                if s.get("captions", True):
                    self.art[i] = self._make_caption(e)
            elif ty == "stamp":
                k = s["stamp"]
                if "tracking_px" in k:  # brand kicker: small capitals, letter-spaced
                    t = PathText(self.ov, e["text"], self.font_files[k["font"]], k["size_px"], k["color"],
                                 k["x"], k["y"], tracking=k["tracking_px"], zorder=3)
                    t.set_alpha(0)
                else:
                    t = self.ov.text(k["x"], k["y"], e["text"], ha="left", va="center", color=k["color"], alpha=0,
                                     fontproperties=self.font(k["font"], k["size"]),
                                     path_effects=[pe.withStroke(linewidth=k.get("halo_w", 0), foreground=k.get("halo", "none"))] if k.get("halo") else [])
                self.art[i] = (t,)
            elif ty == "title":
                if self.brand:
                    self.art[i] = (make_title_card(self.ov, self.font_files, self.palette, e),)
                else:
                    self.art[i] = self._make_title(e)
            # ---- brand-only events ----
            elif ty == "year":  # date wipe: the year counts from one date to the next
                k = s["stamp"]
                t = PathText(self.ov, self._year_text(e, e["from"]), self.font_files[k["font"]], k["size_px"],
                             k["color"], k["x"], k["y"], tracking=k["tracking_px"], zorder=3)
                t.set_alpha(0)
                self.art[i] = (t,)
            elif ty == "lower_third":
                self._check_words(e, "kicker", 3)
                self._check_words(e, "headline", 8)
                self.art[i] = (make_lower_third(self.ov, self.font_files, self.palette, e),)
            elif ty == "chapter":
                self.art[i] = (make_chapter_card(self.ov, self.font_files, self.palette, e),)
            elif ty == "endscreen":
                self.art[i] = (make_end_screen(self.ov, self.font_files, self.palette, e),)
            elif ty == "sting":
                self.art[i] = (Sting(self.ov, self.font_files, self.palette, e),)
            elif ty == "route":  # an arrow engraved along a path (migration, campaign, trade)
                xy = [proj_xy(lon, lat) for lon, lat in e["points"]]
                col = self._colour(e.get("color", s["route"]["color"]))
                r = Route(self.ax, xy, s["route"], col, uncertain=e.get("uncertain", False))
                self.art[i] = (r,)
                if e.get("id"):
                    self.routes[e["id"]] = (r, e)  # so a marker can ride along it
            elif ty == "marker":  # battle cross, site ring, capital, or army counter
                self.art[i] = (Marker(self.ov, self.font_files, self.palette, e, s["markers"]),)
            elif ty == "cite":  # a short source line shown while a fact is on screen
                k = s["cite"]
                t = PathText(self.ov, e["text"], self.font_files[k["font"]], k["size_px"], k["color"],
                             k["x"], k["y"], ha="center", zorder=3)
                t.set_alpha(0)
                self.art[i] = (t,)

    def _colour(self, c):
        """An episode may name a brand colour ("@madder") or give a plain one ("#aa3322")."""
        return self.palette.get(c[1:], c) if isinstance(c, str) and c.startswith("@") else c

    def _route_progress(self, e, t):
        """How much of a route is drawn at time t (0..1), easing in and out."""
        return smooth((t - e["t"]) / max(e["dur"], 1e-6))

    @staticmethod
    def _year_text(e, year):
        return f"{e.get('prefix', '')}{int(round(year))}{e.get('suffix', '')}"

    @staticmethod
    def _check_words(e, key, limit):
        """The brand allows short lower thirds only. Warn (do not stop) when text is too long."""
        n = len(e.get(key, "").split())
        if n > limit:
            print(f"  WARNING: lower third at t={e['t']}: {key} has {n} words (brand limit {limit})")

    def _make_caption(self, e):
        k = self.st["caption"]
        wrapped = "\n".join(textwrap.wrap(e["text"], k.get("wrap", 58)))
        eff = [pe.withStroke(linewidth=k["halo_w"], foreground=k["halo"])] if k.get("halo") else []
        bbox = None
        if k.get("box"):
            bbox = dict(boxstyle="square,pad=0.7", fc=k["box"], ec=k.get("box_edge", "none"), lw=k.get("box_edge_w", 1))
        t = self.ov.text(W0 / 2, k["y"], wrapped, ha="center", va="center", color=k["color"], alpha=0, linespacing=1.25,
                         fontproperties=self.font(k["font"], k["size"]), path_effects=eff, bbox=bbox, zorder=5)
        return (t, k.get("box"), k.get("box_edge"))

    def _make_title(self, e):
        k = self.st["title"]
        dim = Rectangle((0, 0), W0, H0, fc=self.st["colors"]["title_dim"], ec="none", alpha=0, zorder=1)
        self.ov.add_patch(dim)
        t1 = self.ov.text(W0 / 2, H0 / 2 - k.get("title_dy", 20), e["title"], ha="center", va="center", color=k["color"], alpha=0,
                          fontproperties=self.font(k["font"], k["size"]), zorder=3)
        t2 = self.ov.text(W0 / 2, H0 / 2 + k.get("sub_dy", 95), e.get("subtitle", ""), ha="center", va="center", color=k["sub_color"], alpha=0,
                          fontproperties=self.font(k["sub_font"], k["sub_size"]), zorder=3)
        rule = self.ov.plot([W0 / 2 - 190, W0 / 2 + 190], [H0 / 2 + k.get("rule_dy", 50)] * 2, color=k["rule"], lw=k.get("rule_w", 3), alpha=0, zorder=3)[0]
        return (dim, t1, t2, rule)

    # ---------- paper / vignette / frame / compass / tags ----------
    def _build_decorations(self):
        s, c = self.st, self.st["colors"]
        W, H = self.W, self.H
        deco = s.get("deco", {})
        rng = np.random.default_rng(7)

        def noise(scales):
            acc = np.zeros((H, W))
            tot = 0
            for sc, wt in scales:
                small = rng.random((max(2, H // sc), max(2, W // sc))).astype("float32")
                im = Image.fromarray((small * 255).astype("uint8")).resize((W, H), Image.BICUBIC)
                acc += wt * np.asarray(im, float) / 255
                tot += wt
            return acc / tot

        if deco.get("paper"):  # blotchy aged-paper texture
            n = noise([(int(60 * self.scale) + 2, 1.0), (int(14 * self.scale) + 2, 0.7), (2, 0.5)])
            a = np.clip((n - 0.5) * deco["paper"], 0, deco.get("paper_max", 0.14))
            rgb = np.array(deco["paper_color"]) / 255.0
            img = np.dstack([np.broadcast_to(rgb, (H, W, 3)), a])
            self.fig.figimage(img, 0, 0, zorder=3, origin="upper")
        if deco.get("vignette"):
            yy, xx = np.mgrid[0:H, 0:W]
            r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / math.sqrt(2)
            a = deco["vignette"] * np.clip((r - 0.35) / 0.65, 0, 1) ** 1.6
            rgb = np.array(deco.get("vignette_color", [0, 0, 0])) / 255.0
            img = np.dstack([np.broadcast_to(rgb, (H, W, 3)), a])
            self.fig.figimage(img, 0, 0, zorder=4, origin="upper")
        if deco.get("grain"):
            n = noise([(1, 1.0)])
            a = np.clip(np.abs(n - 0.5) * deco["grain"], 0, 0.25)
            img = np.dstack([np.ones((H, W, 3)) * 0.9, a])
            self.fig.figimage(img, 0, 0, zorder=5, origin="upper")
        if deco.get("frame"):
            col = deco["frame"]
            self.ov.add_patch(Rectangle((20, 20), W0 - 40, H0 - 40, fc="none", ec=col, lw=3.2, zorder=2))
            self.ov.add_patch(Rectangle((34, 34), W0 - 68, H0 - 68, fc="none", ec=col, lw=1.0, zorder=2))
        if deco.get("compass"):
            self._compass(1790, 880, 78, deco["compass"])
        # channel tag top-right
        tag = self.ep.get("channel_tag")
        if tag and s.get("tag"):
            k = s["tag"]
            self.ov.text(W0 - k.get("x_off", 70), k.get("y", 70), tag, ha="right", va="center", color=k["color"],
                         fontproperties=self.font(k["font"], k["size"]), zorder=4)
        credit = self.ep.get("credit")
        if self.brand and s.get("credit"):
            # Brand: credit and draft note sit bottom-LEFT, because YouTube puts the channel
            # watermark bottom-right.
            k = s["credit"]
            if credit:
                PathText(self.ov, credit, self.font_files[k["font"]], k["size_px"], k["color"], k["x"], k["y"], zorder=3.5)
            if self.ep.get("draft_tag"):
                PathText(self.ov, "Draft preview: facts still to be verified", self.font_files[k["font"]], k["size_px"],
                         self.palette.get("madder", k["color"]), k["x"], k["y"] - 28, zorder=3.5)
            return
        if credit and s.get("credit"):
            k = s["credit"]
            self.ov.text(W0 - 70, H0 - 62, credit, ha="right", va="center", color=k["color"],
                         fontproperties=self.font(k["font"], k["size"]), zorder=4)
        if self.ep.get("draft_tag") and s.get("credit"):
            k = s["credit"]
            self.ov.text(70, H0 - 62, "DRAFT PREVIEW  -  facts to be verified in scripting", ha="left", va="center", color=k["color"],
                         fontproperties=self.font(k["font"], k["size"]), zorder=4)

    def _compass(self, cx, cy, r, colors):
        dark, light = colors
        for k in range(8):
            ang = math.radians(k * 45)
            L = r if k % 2 == 0 else r * 0.62
            tip = (cx + L * math.sin(ang), cy - L * math.cos(ang))
            for side, col in ((-1, dark), (1, light)):
                a2 = ang + side * math.radians(22.5 if k % 2 == 0 else 28)
                base = (cx + r * 0.2 * math.sin(a2), cy - r * 0.2 * math.cos(a2))
                self.ov.add_patch(MplPolygon([(cx, cy), tip, base], fc=col, ec=dark, lw=0.8, zorder=3))
        self.ov.add_patch(Circle((cx, cy), r * 0.5, fc="none", ec=dark, lw=0.9, zorder=3))
        self.ov.text(cx, cy - r - 16, "N", ha="center", va="center", color=dark, zorder=3,
                     fontproperties=self.font("label", 22))

    # ---------- camera ----------
    def camera_at(self, t):
        ks = self.cam_keys
        if t <= ks[0]["t"]:
            a = b = ks[0]
            u = 0
        elif t >= ks[-1]["t"]:
            a = b = ks[-1]
            u = 0
        else:
            for a, b in zip(ks[:-1], ks[1:]):
                if a["t"] <= t <= b["t"]:
                    break
            u = smooth((t - a["t"]) / (b["t"] - a["t"]))
        ca, cb = np.array(proj_xy(*a["center"])), np.array(proj_xy(*b["center"]))
        center = ca + (cb - ca) * u
        height = math.exp(math.log(a["height"]) + (math.log(b["height"]) - math.log(a["height"])) * u)
        return center, height

    # ---------- draw one frame ----------
    def draw(self, t):
        center, h = self.camera_at(t)
        w = h * W0 / H0
        self.ax.set_xlim(center[0] - w / 2, center[0] + w / 2)
        self.ax.set_ylim(center[1] - h / 2, center[1] + h / 2)
        for lod in self.lods:  # pick the detail level that fits the zoom
            vis = lod["min_h"] <= h < lod["max_h"]
            for a in lod["artists"]:
                a.set_visible(vis)
            if vis and self.land_hatch and self._lod_shown is not lod:
                self.land_hatch.set_clip(lod["land"])  # hatch only the land shape that is showing
                self._lod_shown = lod
        self.admin1_art.set_alpha(self.st.get("admin1_alpha", 0.6) * (1 - smooth((h - 6.0) / 6.0)))

        # What the camera sees (map units), and how many 1080p pixels one map unit is.
        # The hatching uses these to keep its lines evenly spaced on screen.
        view = (center[0] - w / 2, center[0] + w / 2, center[1] - h / 2, center[1] + h / 2)
        px_per_unit = H0 / h
        if self.land_hatch:
            self.land_hatch.update(view, px_per_unit, 1.0)
        to_overlay = self.ax.transData + self.ov.transData.inverted()  # map units -> overlay pixels

        for i, e in enumerate(self.events):
            ty, a = e["type"], self.art.get(i)
            if a is None:
                continue
            if ty == "fill":
                al = fade(t, e["t"], e.get("dur", 1.5), e.get("out"), e.get("out_dur", 1.5))
                a[0].set_alpha(al * a[1])
                extra = a[2]
                if "hatch" in extra:  # hatch lines appear line by line over "hatch_in" seconds
                    reveal = smooth((t - e["t"]) / self.st.get("hatch_in", 0.8))
                    extra["hatch"].update(view, px_per_unit, al, reveal)
                if "outline" in extra:
                    extra["outline"].set_alpha(al)
            elif ty == "line":
                layers, tip = a
                ln = self.lines[e["name"]]
                x = smooth_line = min(max((t - e["t"]) / e["dur"], 0), 1)
                target = x * ln["cum"][-1]
                k = np.searchsorted(ln["cum"], target)
                xy = ln["xy"][:k + 1].copy()
                if 0 < k < len(ln["xy"]):  # interpolate the last point for smooth drawing
                    f = (target - ln["cum"][k - 1]) / max(ln["cum"][k] - ln["cum"][k - 1], 1e-9)
                    xy[-1] = ln["xy"][k - 1] + (ln["xy"][k] - ln["xy"][k - 1]) * f
                if t < e["t"] or len(xy) < 2:
                    xy = np.zeros((0, 2))
                for hdl, al in layers:
                    hdl.set_data(xy[:, 0], xy[:, 1])
                drawing = e["t"] <= t < e["t"] + e["dur"]
                tip.set_data([xy[-1, 0]] if drawing and len(xy) else [], [xy[-1, 1]] if drawing and len(xy) else [])
            elif ty == "label":
                al = fade(t, e["t"], e.get("dur", 1.2), e.get("out"), e.get("out_dur", 1.2))
                if a[0] == "path":  # brand label: move it to where its place is on screen now
                    _, txt, marker, base, xy, (dx, dy) = a
                    px, py = to_overlay.transform(xy)
                    txt.move(px + dx, py + dy)
                    txt.set_alpha(al * base)
                    if marker is not None:
                        marker.set_alpha(al)
                    continue
                a[0].set_alpha(al * a[2])
                if a[1] is not None:
                    a[1].set_alpha(al)
            elif ty == "caption":
                al = fade(t, e["t"], 0.7, e["t"] + e["dur"], 0.7)
                txt, box_fc, box_ec = a
                txt.set_alpha(al)
                bp = txt.get_bbox_patch()
                if bp is not None:
                    from matplotlib.colors import to_rgba
                    fc = to_rgba(box_fc)
                    bp.set_facecolor((*fc[:3], fc[3] * al))
                    ec = to_rgba(box_ec or "#00000000")
                    bp.set_edgecolor((*ec[:3], ec[3] * al))
            elif ty == "stamp":
                a[0].set_alpha(fade(t, e["t"], 0.8, e["t"] + e["dur"], 0.8))
            elif ty == "title":
                al = fade(t, e["t"], e.get("fade", 1.0), e["t"] + e["dur"], e.get("fade", 1.0))
                if len(a) == 1:  # brand title card (one group that fades together)
                    a[0].set_alpha(al)
                    continue
                dim, t1, t2, rule = a
                dim.set_alpha(al * e.get("dim", 0.6))
                t1.set_alpha(al)
                t2.set_alpha(al)
                rule.set_alpha(al)
            # ---- brand-only events ----
            elif ty == "year":
                # count from e["from"] to e["to"] during "dur", then hold, then fade out
                u = smooth((t - e["t"]) / max(e["dur"], 1e-6))
                a[0].set_text(self._year_text(e, e["from"] + (e["to"] - e["from"]) * u))
                a[0].set_alpha(fade(t, e["t"], 0.5, e["t"] + e["dur"] + e.get("hold", 3.0), 0.6))
            elif ty in ("lower_third", "chapter", "endscreen", "cite"):
                a[0].set_alpha(fade(t, e["t"], 0.6, e["t"] + e["dur"], 0.6))
            elif ty == "sting":
                a[0].draw(t, fade, smooth)
            elif ty == "route":
                al = fade(t, e["t"], 0.3, e.get("out"), e.get("out_dur", 1.0))
                a[0].update(self._route_progress(e, t), al, px_per_unit)
            elif ty == "marker":
                if e.get("follow"):  # ride along a route: sit at the arrow's tip
                    route, re = self.routes[e["follow"]]
                    xy, _, _ = route.point_at(max(self._route_progress(re, t), 1e-6))
                else:
                    xy = proj_xy(e["lon"], e["lat"])
                px, py = to_overlay.transform(xy)
                a[0].place(px, py)
                a[0].set_alpha(fade(t, e["t"], e.get("dur", 0.6), e.get("out"), e.get("out_dur", 0.8)))

        self.fig.canvas.draw()
        return np.asarray(self.fig.canvas.buffer_rgba())


# --------------------------------------------------------------------------
# 5.  COMMAND LINE
# --------------------------------------------------------------------------
def render_in_parts(args, episode):
    """Render the video as several parts AT THE SAME TIME (one per CPU core), then join them.
    Each part is a separate copy of this program working on its own range of frames.
    The finished video is exactly the same as a normal render, just made faster."""
    import os
    import time
    fps = int(episode.get("fps", 30))
    end = args.end if args.end is not None else float(episode["duration"])
    n0, n1 = int(round(args.start * fps)), int(round(end * fps))
    jobs = max(1, min(args.jobs, n1 - n0))
    edges = [n0 + (n1 - n0) * k // jobs for k in range(jobs + 1)]  # frame numbers where parts meet
    out = Path(args.out)
    parts_dir = out.parent / f"_parts_{out.stem}"
    parts_dir.mkdir(parents=True, exist_ok=True)

    procs, logs, handles = [], [], []
    for k in range(jobs):
        part = parts_dir / f"part_{k:02d}.mp4"
        log = parts_dir / f"part_{k:02d}.log"
        cmd = [sys.executable, "-u", str(Path(__file__).resolve()), args.episode, "--style", args.style,
               "--out", str(part), "--data", args.data, "--scale", str(args.scale),
               "--frames", f"{edges[k]}:{edges[k + 1]}"]
        logs.append(log)
        handles.append(open(log, "w"))
        procs.append(subprocess.Popen(cmd, stdout=handles[-1], stderr=subprocess.STDOUT))
    print(f"Rendering {n1 - n0} frames in {jobs} parts at once ...")

    def frames_done():  # read the last "frame N/M" line of each part's log
        total = 0
        for log in logs:
            lines = [l for l in log.read_text(errors="ignore").splitlines() if "frame " in l]
            if lines:
                total += int(lines[-1].split("frame ")[1].split("/")[0])
        return total

    started = time.time()
    while any(p.poll() is None for p in procs):
        time.sleep(15)
        done = frames_done()
        mins = (time.time() - started) / 60
        print(f"  about {done}/{n1 - n0} frames done ({mins:.1f} min)", flush=True)
    for h in handles:  # Windows cannot delete a file that is still open
        h.close()
    failed = [k for k, p in enumerate(procs) if p.returncode != 0]
    if failed:
        sys.exit(f"Part(s) {failed} failed - see the .log files in {parts_dir}")

    # join the parts without re-encoding (they were all made with the same settings)
    listing = parts_dir / "parts.txt"
    # names in this list are read relative to the list file itself, so give bare file names
    lines = [f"file 'part_{k:02d}.mp4'" for k in range(jobs)]
    listing.write_text("\n".join(lines) + "\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    for f in parts_dir.iterdir():  # the parts were only temporary
        f.unlink()
    parts_dir.rmdir()
    print("Saved", out)


def main():
    ap = argparse.ArgumentParser(description="Render a History Through Maps episode.")
    ap.add_argument("episode", help="episode JSON file")
    ap.add_argument("--style", required=True, help="style JSON file")
    ap.add_argument("--out", required=True, help="output .mp4 (or .png with --still)")
    ap.add_argument("--data", default=str(HERE / "data"), help="folder with Natural Earth shapefiles")
    ap.add_argument("--scale", type=float, default=1.0, help="1.0 = 1920x1080, 0.5 = 960x540 (fast preview)")
    ap.add_argument("--still", type=float, help="save a single frame at this time (seconds)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--jobs", type=int, default=1,
                    help="render in this many parts at once (each uses one CPU core and about 1 GB of memory)")
    ap.add_argument("--frames", help=argparse.SUPPRESS)  # used internally by --jobs: exact frames "first:last"
    args = ap.parse_args()

    episode = json.loads(Path(args.episode).read_text(encoding="utf-8"))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if args.jobs > 1 and args.still is None:
        render_in_parts(args, episode)
        return

    style = load_style(args.style)  # also turns brand names like "@ink" into colours
    print("Loading Natural Earth data ...")
    world = World(args.data)
    print("Building scene ...")
    r = Renderer(episode, style, world, scale=args.scale)

    if args.still is not None:
        frame = r.draw(args.still)
        Image.fromarray(frame).convert("RGB").save(args.out)
        print("Saved", args.out)
        return

    if args.frames:  # one part of a --jobs render
        n0, n1 = (int(x) for x in args.frames.split(":"))
    else:
        end = args.end if args.end is not None else r.duration
        n0, n1 = int(round(args.start * r.fps)), int(round(end * r.fps))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{r.W}x{r.H}",
           "-r", str(r.fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
           "-movflags", "+faststart", args.out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(n0, n1):
        frame = r.draw(n / r.fps)
        ff.stdin.write(frame.tobytes())
        if (n - n0) % 30 == 0:
            print(f"  frame {n - n0 + 1}/{n1 - n0}  (t={n / r.fps:.1f}s)", flush=True)
    ff.stdin.close()
    ff.wait()
    print("Saved", args.out)


if __name__ == "__main__":
    main()
