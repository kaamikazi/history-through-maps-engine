"""
brand_parts.py - the "History Through Maps" brand pieces used by map_engine.py.

The brand (github.com/kaamikazi/History-C) looks like an antique engraved atlas.
This file holds the parts that make that look:

  load_style()   reads a style file and swaps "@token" names for real colours from tokens.json
  text_path()    turns text into a shape, with letter-spacing ("tracking") for small capitals
  PathText       a piece of text that can be moved and faded each frame
  Group          a set of drawings that fade in and out together
  Hatcher        engraved hatching: thin parallel lines clipped to a shape
  make_lower_third / make_chapter_card / make_sting / make_end_screen / make_title_card
                 the on-screen "plates" from the brand templates (sizes copied from the templates)

All overlay positions are in PIXELS of a 1920x1080 frame, with y going DOWN
(exactly like the brand's SVG templates, so numbers can be copied across).
Line widths: 1 px at 1080p = 0.72 points, which is what matplotlib wants (PT below).
"""

import json
import math
from pathlib import Path

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, PathPatch, Polygon as MplPolygon, Rectangle
from matplotlib.path import Path as MPath
from matplotlib.textpath import TextPath, text_to_path
from matplotlib.transforms import Affine2D

PT = 0.72  # multiply a width in pixels (at 1080p) by this to get matplotlib points


# --------------------------------------------------------------------------
# 1.  STYLE FILES AND COLOUR TOKENS
# --------------------------------------------------------------------------
def load_style(path):
    """Read a style JSON. If it names a tokens file, every text value like "@ink"
    is replaced by that token's colour for the style's theme ("light" or "dark")."""
    path = Path(path)
    style = json.loads(path.read_text(encoding="utf-8"))
    if "tokens_file" not in style:
        return style  # an older style with plain colours: nothing to do
    tokens = json.loads((path.parent / style["tokens_file"]).read_text(encoding="utf-8"))
    theme = style.get("theme", "dark")
    colours = {}
    for tok in tokens["color"]["tokens"]:
        v = tok["value"]
        colours[tok["name"]] = v[theme] if isinstance(v, dict) else v

    def resolve(x):
        if isinstance(x, str) and x.startswith("@"):
            name = x[1:]
            val = colours[name]
            while isinstance(val, str) and val.startswith("{"):  # e.g. "{verdigris}" points at another token
                val = colours[val.strip("{}")]
            return val
        if isinstance(x, dict):
            return {k: resolve(v) for k, v in x.items()}
        if isinstance(x, list):
            return [resolve(v) for v in x]
        return x

    style = resolve(style)
    style["palette"] = colours  # keep the full list too, handy for the plates below
    return style


# --------------------------------------------------------------------------
# 2.  TEXT AS SHAPES (so we can space letters out, like the brand's small capitals)
# --------------------------------------------------------------------------
def _width(s, fp):
    w, _, _ = text_to_path.get_text_width_height_descent(s, fp, ismath=False)
    return w


def _advance(piece, fp):
    """How far the pen moves after drawing `piece`. Measured between two x's,
    because a space on its own has no ink and would measure as 0 wide."""
    return _width("x" + piece + "x", fp) - _width("xx", fp)


def text_path(text, font_file, size, tracking=0.0, line_height=None, ha="left"):
    """Turn `text` into ONE matplotlib Path measured in pixels.

    size        letter size in pixels (the same number as font-size in the brand's SVGs)
    tracking    extra pixels between letters (letter-spacing in the SVGs)
    line_height pixels from one line's baseline to the next (for "\\n" in the text)
    ha          "left", "center" or "right": which end of each line sits at x = 0

    The point (0, 0) is the start of the FIRST line's baseline, and y grows downwards.
    """
    fp = FontProperties(fname=str(font_file), size=size)
    lh = line_height or size * 1.15
    verts, codes = [], []
    for row, line in enumerate(text.split("\n")):
        pieces = [line] if tracking == 0 else list(line)  # tracked text: one letter at a time
        line_verts, line_codes, x = [], [], 0.0
        for i, piece in enumerate(pieces):
            if piece.strip():
                tp = TextPath((0, 0), piece, size=size, prop=fp)
                v = tp.vertices.copy()
                v[:, 0] += x
                v[:, 1] = -v[:, 1]  # fonts draw upwards; our overlay goes downwards
                line_verts.append(v)
                line_codes.append(tp.codes)
            x += _advance(piece, fp) + (tracking if i < len(pieces) - 1 else 0)
        shift = {"left": 0.0, "center": -x / 2, "right": -x}[ha]
        for v, c in zip(line_verts, line_codes):
            v[:, 0] += shift
            v[:, 1] += row * lh
            verts.append(v)
            codes.append(c)
    if not verts:
        return MPath(np.zeros((1, 2)), [MPath.MOVETO])
    return MPath(np.concatenate(verts), np.concatenate(codes))


class PathText:
    """Text drawn as a shape on the overlay. It can move (for labels that follow the map),
    fade, and change its words (for the counting year)."""

    def __init__(self, ov, text, font_file, size, color, x=0, y=0, tracking=0.0, ha="left",
                 line_height=None, zorder=5, halo=None, halo_w=0):
        self.ov, self.font_file, self.size = ov, font_file, size
        self.tracking, self.ha, self.line_height = tracking, ha, line_height
        self.text = text
        self.patch = PathPatch(self._make(text), fc=color, ec="none", lw=0, zorder=zorder)
        if halo:  # a soft outline behind the letters so they read over busy maps
            import matplotlib.patheffects as pe
            self.patch.set_path_effects([pe.withStroke(linewidth=halo_w, foreground=halo)])
        ov.add_patch(self.patch)
        self.move(x, y)

    def _make(self, text):
        return text_path(text, self.font_file, self.size, self.tracking, self.line_height, self.ha)

    def move(self, x, y):
        """Put the start of the baseline at pixel (x, y)."""
        self.patch.set_transform(Affine2D().translate(x, y) + self.ov.transData)

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self.patch.set_path(self._make(text))

    def set_alpha(self, a):
        self.patch.set_alpha(a)
        self.patch.set_visible(a > 0.002)


class Group:
    """Several drawings that fade together. Each keeps its own base opacity."""

    def __init__(self):
        self.items = []

    def add(self, artist, alpha=1.0):
        artist.set_alpha(0)
        self.items.append((artist, alpha))
        return artist

    def set_alpha(self, a):
        for art, base in self.items:
            art.set_alpha(a * base)
            if hasattr(art, "set_visible"):
                art.set_visible(a > 0.002)


# --------------------------------------------------------------------------
# 3.  ENGRAVED HATCHING
# --------------------------------------------------------------------------
class Hatcher:
    """Thin parallel lines clipped to a shape, like the lines on an engraved map.

    The lines are fixed to the MAP (they move with it when the camera pans) but are
    re-spaced as the camera zooms, so on screen they stay about `spacing_px` apart.
    Trick used: lines sit at multiples of a spacing that is a power of 2. Every other
    line ("odd" lines) fades out as we zoom out, until the spacing doubles.

    angle_deg is the direction of the lines, measured from horizontal.
    """

    def __init__(self, ax, clip_patch, angle_deg, spacing_px, width_px, color, zorder, shape_bounds=None):
        self.spacing_px = spacing_px
        self.c, self.s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
        self.bounds = shape_bounds  # (xmin, ymin, xmax, ymax) of the shape, to skip far-away lines
        self.even = LineCollection([], colors=color, linewidths=width_px * PT, zorder=zorder)
        self.odd = LineCollection([], colors=color, linewidths=width_px * PT, zorder=zorder)
        for lc in (self.even, self.odd):
            lc.set_clip_path(clip_patch)
            ax.add_collection(lc)

    def set_clip(self, clip_patch):
        for lc in (self.even, self.odd):
            lc.set_clip_path(clip_patch)

    def _uv(self, x, y):
        """Turn map x, y into (u across the lines, v along the lines)."""
        return x * self.c + y * self.s, -x * self.s + y * self.c

    def update(self, view, px_per_unit, alpha, reveal=1.0):
        """Redraw for this frame.
        view        (x0, x1, y0, y1): what the camera sees, in map units
        px_per_unit how many 1080p pixels one map unit is right now
        reveal      0..1: how much of the shape is hatched (for the "hatch in" animation)"""
        if alpha <= 0.002:
            self.even.set_visible(False)
            self.odd.set_visible(False)
            return
        x0, x1, y0, y1 = view
        if self.bounds is not None:  # only the part of the view that touches the shape
            bx0, by0, bx1, by1 = self.bounds
            x0, x1, y0, y1 = max(x0, bx0), min(x1, bx1), max(y0, by0), min(y1, by1)
            if x0 >= x1 or y0 >= y1:
                self.even.set_visible(False)
                self.odd.set_visible(False)
                return
        level = math.log2(self.spacing_px / px_per_unit)
        base = math.floor(level)
        frac = level - base
        step = 2.0 ** base

        us, vs = zip(*[self._uv(x, y) for x in (x0, x1) for y in (y0, y1)])
        umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
        if reveal < 1.0 and self.bounds is not None:
            bx0, by0, bx1, by1 = self.bounds
            bu = [self._uv(x, y)[0] for x in (bx0, bx1) for y in (by0, by1)]
            umax = min(umax, min(bu) + reveal * (max(bu) - min(bu)))
        k = np.arange(math.ceil(umin / step), math.floor(umax / step) + 1)
        if len(k) > 4000:  # safety: never draw an absurd number of lines
            k = k[:4000]
        u = k * step
        # each line goes from (u, vmin) to (u, vmax), turned back into map x, y
        p0 = np.column_stack([u * self.c - vmin * self.s, u * self.s + vmin * self.c])
        p1 = np.column_stack([u * self.c - vmax * self.s, u * self.s + vmax * self.c])
        segs = np.stack([p0, p1], axis=1)
        is_even = (k % 2) == 0
        self.even.set_segments(segs[is_even])
        self.odd.set_segments(segs[~is_even])
        self.even.set_alpha(alpha)
        self.odd.set_alpha(alpha * (1.0 - frac))
        self.even.set_visible(True)
        self.odd.set_visible(True)


# --------------------------------------------------------------------------
# 4.  OVERLAY PLATES (sizes copied from the brand templates, 1920x1080 frame)
# --------------------------------------------------------------------------
def _rect(ov, g, x, y, w, h, fc="none", ec="none", lw_px=0.0, z=5, alpha=1.0):
    r = Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw_px * PT, zorder=z)
    ov.add_patch(r)
    return g.add(r, alpha)


def _line(ov, g, x0, y0, x1, y1, color, lw_px, z=5, alpha=1.0):
    (ln,) = ov.plot([x0, x1], [y0, y1], color=color, lw=lw_px * PT, zorder=z, solid_capstyle="butt")
    return g.add(ln, alpha)


def _text(ov, g, fonts, key, text, size, color, x, y, tracking=0.0, ha="left", line_height=None, z=6):
    t = PathText(ov, text, fonts[key], size, color, x, y, tracking, ha, line_height, zorder=z)
    return g.add(t)


def double_frame(ov, g, P, z=5):
    """The brand's double rule around the whole frame, with the gold north tick on top."""
    _rect(ov, g, 56, 56, 1808, 968, ec=P["ink"], lw_px=4, z=z)
    _rect(ov, g, 76, 76, 1768, 928, ec=P["ink"], lw_px=1.5, z=z)
    tick = MplPolygon([(960, 36), (972, 56), (960, 76), (948, 56)], closed=True, fc=P["gold"], ec=P["ink"],
                      lw=2 * PT, zorder=z + 0.1)
    ov.add_patch(tick)
    g.add(tick)


def make_lower_third(ov, fonts, P, e):
    """Lower third (templates/lower-third.html): kicker + headline on a double-ruled plate,
    with an optional red year box on the right."""
    g = Group()
    year = e.get("year")
    w = 1000 if year else 760
    x, y = (96, 808) if e.get("pos", "left") == "left" else (1920 - 96 - w, 808)
    _rect(ov, g, x, y, w, 168, fc=P["ground-raised"], ec=P["ink"], lw_px=3)
    _rect(ov, g, x + 10, y + 10, w - 20, 148, ec=P["ink"], lw_px=1.2)
    if year:
        _rect(ov, g, x + w - 248, y, 248, 168, fc=P["madder"], z=5.1)
        _rect(ov, g, x + w - 238, y + 10, 228, 148, ec=P["ground-raised"], lw_px=1.2, z=5.2)
        _text(ov, g, fonts, "display", str(year), 72, P["ground-raised"], x + w - 124, y + 106, ha="center")
    _text(ov, g, fonts, "caps", e["kicker"], 28, P["ink-muted"], x + 34, y + 58, tracking=6)
    _line(ov, g, x + 34, y + 76, x + w - (282 if year else 34), y + 76, P["ink"], 1.2, z=5.3)
    _text(ov, g, fonts, "display", e["headline"], 56, P["ink"], x + 34, y + 138)
    return g


def make_chapter_card(ov, fonts, P, e):
    """Chapter card (templates/chapter-card.html): rings, double frame, chapter number,
    title in the italic display face, and the years in small capitals."""
    g = Group()
    _rect(ov, g, 0, 0, 1920, 1080, fc=P["ground"], z=8)
    for r in (160, 260, 360, 460):
        c = Circle((960, 540), r, fc="none", ec=P["hairline"], lw=2 * PT, zorder=8.1)
        ov.add_patch(c)
        g.add(c)
    _line(ov, g, 960, 80, 960, 1000, P["hairline"], 2, z=8.1)
    _line(ov, g, 500, 540, 1420, 540, P["hairline"], 2, z=8.1)
    double_frame(ov, g, P, z=8.2)
    _rect(ov, g, 560, 330, 800, 420, fc=P["ground"], z=8.3)
    _text(ov, g, fonts, "caps", e["number"], 40, P["madder"], 960, 396, tracking=12, ha="center", z=8.5)
    _line(ov, g, 880, 426, 1040, 426, P["ink"], 2, z=8.4)
    _line(ov, g, 880, 434, 1040, 434, P["ink"], 2, z=8.4)
    lines = e["title"].split("\n")
    first = 548 if len(lines) > 1 else 606
    _text(ov, g, fonts, "display", e["title"], 116, P["ink"], 960, first, ha="center", line_height=116, z=8.5)
    if e.get("years"):
        _text(ov, g, fonts, "caps", e["years"], 36, P["ink-muted"], 960, first + (len(lines) - 1) * 116 + 60,
              tracking=10, ha="center", z=8.5)
    return g


def make_title_card(ov, fonts, P, e):
    """Opening title: kicker, double rule, title in the italic display face, one line under it."""
    g = Group()
    _rect(ov, g, 0, 0, 1920, 1080, fc=P["ground"], z=1, alpha=e.get("dim", 0.6))
    if e.get("kicker"):
        _text(ov, g, fonts, "caps", e["kicker"], 32, P["madder"], 960, 430, tracking=10, ha="center")
    _line(ov, g, 870, 456, 1050, 456, P["ink"], 2, z=2)
    _line(ov, g, 870, 464, 1050, 464, P["ink"], 2, z=2)
    _text(ov, g, fonts, "display", e["title"], 120, P["ink"], 960, 590, ha="center")
    if e.get("subtitle"):
        _text(ov, g, fonts, "body_italic", e["subtitle"], 38, P["ink-muted"], 960, 660, ha="center")
    return g


def make_end_screen(ov, fonts, P, e):
    """End screen: two video plates and a round subscribe plate. YouTube's own end-screen
    elements are placed on top of these in YouTube Studio."""
    g = Group()
    _rect(ov, g, 0, 0, 1920, 1080, fc=P["ground"], z=8)
    double_frame(ov, g, P, z=8.2)
    _text(ov, g, fonts, "caps", e.get("kicker", "Next map"), 32, P["madder"], 960, 176, tracking=10, ha="center", z=8.5)
    _line(ov, g, 870, 200, 1050, 200, P["ink"], 2, z=8.3)
    _line(ov, g, 870, 208, 1050, 208, P["ink"], 2, z=8.3)
    if e.get("next"):
        _text(ov, g, fonts, "display", e["next"], 72, P["ink"], 960, 290, ha="center", z=8.5)
    for x in (176, 1168):  # two 16:9 plates, 576 x 324
        _rect(ov, g, x, 370, 576, 324, fc=P["ground-raised"], ec=P["ink"], lw_px=3, z=8.3)
        _rect(ov, g, x + 10, 380, 556, 304, ec=P["ink"], lw_px=1.2, z=8.4)
    for r, lw in ((96, 3), (86, 1.2)):  # subscribe plate in the middle
        c = Circle((960, 532), r, fc=P["ground-raised"] if lw == 3 else "none", ec=P["ink"], lw=lw * PT, zorder=8.3)
        ov.add_patch(c)
        g.add(c)
    _text(ov, g, fonts, "display", "History Through Maps", 44, P["ink"], 960, 850, ha="center", z=8.5)
    _text(ov, g, fonts, "caps", "Every border has a story", 22, P["ink-muted"], 960, 892, tracking=7, ha="center", z=8.5)
    return g


def draw_mark(ov, P, cx, cy, scale, z=6):
    """The medallion logo, finished (not animated), centred at pixel (cx, cy).
    scale = pixels per logo unit (the logo drawing is 120 units wide)."""
    def pt(x, y):
        return cx + (x - 60) * scale, cy + (y - 64) * scale

    def add(p):
        ov.add_patch(p)
        return p

    add(Circle(pt(60, 64), 54 * scale, fc=P["ground-raised"], ec=P["ink"], lw=3 * scale * PT, zorder=z))
    add(Circle(pt(60, 64), 48 * scale, fc="none", ec=P["ink"], lw=1 * scale * PT, zorder=z))
    add(Circle(pt(60, 64), 41 * scale, fc=P["map-land"], ec="none", zorder=z))
    clip = Circle(pt(60, 64), 41 * scale, transform=ov.transData)
    terr = add(MplPolygon([pt(*p) for p in MARK_TERRITORY], closed=True, fc=P["territory"], ec="none", zorder=z + 0.1))
    terr.set_clip_path(clip)
    # 45-degree hatching over the red territory, 4 logo units apart
    xs, ys = zip(*[pt(*p) for p in MARK_TERRITORY])
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    gap = 4 * scale * math.sqrt(2)
    hatch = LineCollection([[(x, y1), (x + (y1 - y0), y0)] for x in np.arange(x0 - (y1 - y0), x1, gap)],
                           colors=P["madder"], linewidths=1 * scale * PT, zorder=z + 0.2)
    hatch.set_clip_path(MplPolygon([pt(*p) for p in MARK_TERRITORY], closed=True, transform=ov.transData))
    ov.add_collection(hatch)
    a = np.linspace(0, 2 * math.pi, 120)
    grat = [np.column_stack([60 + 18 * np.cos(a), 64 + 41 * np.sin(a)]),
            [(60, 23), (60, 105)], [(19, 64), (101, 64)], [(22, 46), (98, 46)], [(22, 82), (98, 82)]]
    for g in grat:
        (ln,) = ov.plot(*zip(*[pt(x, y) for x, y in g]), color=P["ink"], lw=1.2 * scale * PT, zorder=z + 0.3)
        ln.set_clip_path(clip)
    (ol,) = ov.plot(*zip(*[pt(*p) for p in MARK_TERRITORY + [MARK_TERRITORY[0]]]), color=P["ink"],
                    lw=1.6 * scale * PT, zorder=z + 0.3, solid_joinstyle="round")
    ol.set_clip_path(clip)
    add(Circle(pt(60, 64), 41 * scale, fc="none", ec=P["ink"], lw=2 * scale * PT, zorder=z + 0.4))
    add(MplPolygon([pt(60, 1), pt(66, 10), pt(60, 17), pt(54, 10)], closed=True, fc=P["gold"], ec=P["ink"],
                   lw=1 * scale * PT, zorder=z + 0.4))


def make_thumbnail_card(ov, fonts, P, kicker, title):
    """Thumbnail cartouche (templates/thumbnail.html). The template is 1280x720 and our overlay is
    1920x1080, so every number from the template is multiplied by K = 1.5."""
    K = 1.5
    g = Group()
    _rect(ov, g, 40 * K, 60 * K, 520 * K, 600 * K, fc=P["ground-raised"], ec=P["ink"], lw_px=3 * K, z=6)
    _rect(ov, g, 52 * K, 72 * K, 496 * K, 576 * K, ec=P["ink"], lw_px=1.2 * K, z=6.1)
    tick = MplPolygon([(300 * K, 51 * K), (306 * K, 60 * K), (300 * K, 69 * K), (294 * K, 60 * K)], closed=True,
                      fc=P["gold"], ec=P["ink"], lw=1.5 * K * PT, zorder=6.2)
    ov.add_patch(tick)
    g.add(tick)
    _text(ov, g, fonts, "caps", kicker, 30 * K, P["madder"], 84 * K, 150 * K, tracking=6 * K, z=6.3)
    _line(ov, g, 84 * K, 172 * K, 516 * K, 172 * K, P["ink"], 1.5 * K, z=6.3)
    _line(ov, g, 84 * K, 178 * K, 516 * K, 178 * K, P["ink"], 1.5 * K, z=6.3)
    _text(ov, g, fonts, "display", title, 104 * K, P["ink"], 84 * K, 290 * K, line_height=106 * K, z=6.3)
    draw_mark(ov, P, (84 + 30) * K, (540 + 32) * K, 0.5 * K, z=6.4)  # small logo: 60 x 64 in the template
    _text(ov, g, fonts, "display", "History Through Maps", 32 * K, P["ink"], 160 * K, 582 * K, z=6.3)
    _text(ov, g, fonts, "caps", "Every border has a story", 15 * K, P["ink-muted"], 160 * K, 610 * K,
          tracking=5 * K, z=6.3)
    g.set_alpha(1.0)
    return g


# ---- the sting: the medallion is engraved, the red territory hatches in, the wordmark settles ----
# Medallion shapes copied from assets/logos/mark-on-dark.svg (a 120 x 120 drawing, centre 60, 64).
MARK_TERRITORY = [(62, 30), (90, 42), (98, 66), (80, 74), (84, 98), (62, 106), (52, 84), (68, 68), (56, 52)]


class Sting:
    """2.5-second opening sting, drawn from the logo's own shapes and animated in steps."""

    def __init__(self, ov, fonts, P, e):
        self.ov, self.e, self.P = ov, e, P
        self.S = 3.0                # logo size: 1 logo unit = 3 pixels (medallion 324 px wide)
        self.cx, self.cy = 960, 470  # where the logo's centre (60, 64) goes
        self.bg = Group()
        # The background sits just under chapter cards (z 7.9), so a card can fade in over it.
        _rect(ov, self.bg, 0, 0, 1920, 1080, fc=P["ground"], z=7.9)

        def pt(x, y):  # logo units -> frame pixels
            return self.cx + (x - 60) * self.S, self.cy + (y - 64) * self.S

        self.pt = pt
        # filled discs (fade in)
        self.discs = Group()
        for r, fc in ((54, P["ground-raised"]), (41, P["map-land"])):
            c = Circle(pt(60, 64), r * self.S, fc=fc, ec="none", zorder=20.1)
            ov.add_patch(c)
            self.discs.add(c)
        self.globe_clip = Circle(pt(60, 64), 41 * self.S, transform=ov.transData)
        # red territory + its hatching (hatching is drawn line by line)
        self.terr = MplPolygon([pt(*p) for p in MARK_TERRITORY], closed=True, fc=P["territory"], ec="none", zorder=20.2)
        self.terr.set_clip_path(self.globe_clip)
        ov.add_patch(self.terr)
        self.terr.set_alpha(0)
        xs, ys = zip(*[pt(*p) for p in MARK_TERRITORY])
        self.hatch = LineCollection([], colors=P["ground"], linewidths=1.0 * self.S * PT, zorder=20.3)
        self.hatch.set_clip_path(MplPolygon([pt(*p) for p in MARK_TERRITORY], closed=True, transform=ov.transData))
        ov.add_collection(self.hatch)
        self.hatch_box = (min(xs), max(xs), min(ys), max(ys))
        # lines that get "engraved" (drawn on progressively): (points, width, start, end)
        self.traces = []

        def circle_pts(r, n=180):
            a = np.linspace(-math.pi / 2, 1.5 * math.pi, n)
            return np.column_stack([60 + r * np.cos(a), 64 + r * np.sin(a)])

        def ellipse_pts(rx, ry, n=180):
            a = np.linspace(-math.pi / 2, 1.5 * math.pi, n)
            return np.column_stack([60 + rx * np.cos(a), 64 + ry * np.sin(a)])

        self._trace(circle_pts(54), 3, 0.00, 0.60)
        self._trace(circle_pts(48), 1, 0.15, 0.75)
        self._trace(circle_pts(41), 2, 0.30, 0.90)
        for pts in (ellipse_pts(18, 41), [(60, 23), (60, 105)], [(19, 64), (101, 64)],
                    [(22, 46), (98, 46)], [(22, 82), (98, 82)]):
            self._trace(pts, 1.2, 0.55, 1.15, clip=True)
        self._trace(MARK_TERRITORY + [MARK_TERRITORY[0]], 1.6, 1.05, 1.55, clip=True)
        # gold north diamond and the wordmark
        self.extra = Group()
        tick = MplPolygon([pt(60, 1), pt(66, 10), pt(60, 17), pt(54, 10)], closed=True, fc=P["gold"],
                          ec=P["ink"], lw=1 * self.S * PT, zorder=20.6)
        ov.add_patch(tick)
        self.extra.add(tick)
        self.word = Group()
        self.w1 = _text(ov, self.word, fonts, "display", "History Through Maps", 76, P["ink"], 960, 770, ha="center", z=20.7)
        self.w2 = _text(ov, self.word, fonts, "caps", "Every border has a story", 26, P["ink-muted"], 960, 822,
                        tracking=8, ha="center", z=20.7)

    def _trace(self, pts, width, t0, t1, clip=False):
        xy = np.array([self.pt(x, y) for x, y in pts], float)
        # resample evenly along the length, so drawing speed is steady
        seg = np.hypot(*np.diff(xy, axis=0).T)
        cum = np.concatenate([[0], np.cumsum(seg)])
        (ln,) = self.ov.plot([], [], color=self.P["ink"], lw=width * self.S * PT, zorder=20.4,
                             solid_capstyle="round", solid_joinstyle="round")
        if clip:
            ln.set_clip_path(self.globe_clip)
        self.traces.append((ln, xy, cum, t0, t1))

    def draw(self, t, fade_fn, smooth_fn):
        e = self.e
        local = t - e["t"]
        dur = e.get("dur", 2.5)
        al = fade_fn(t, e["t"], 0.15, e["t"] + dur - 0.3, 0.3)  # the logo fades in fast, out at the end
        # The plain background stays solid 0.7 s longer, then fades: time for a chapter card to cover it.
        self.bg.set_alpha(fade_fn(t, e["t"], 0.15, e["t"] + dur + 0.7, 0.4))
        self.discs.set_alpha(al * smooth_fn(local / 0.4))
        for ln, xy, cum, t0, t1 in self.traces:
            p = smooth_fn((local - t0) / (t1 - t0))
            n = np.searchsorted(cum, p * cum[-1])
            part = xy[: max(n, 1) + 1] if p > 0 else xy[:0]
            ln.set_data(part[:, 0], part[:, 1])
            ln.set_alpha(al)
            ln.set_visible(al > 0.002)
        tp = smooth_fn((local - 1.0) / 0.4)
        self.terr.set_alpha(al * tp)
        self.terr.set_visible(al * tp > 0.002)
        # hatch lines at 45 degrees, 4 logo units apart, appearing left to right over 0.8 s
        x0, x1, y0, y1 = self.hatch_box
        reveal = smooth_fn((local - 1.0) / 0.8)
        gap = 4 * self.S * math.sqrt(2)
        xs = np.arange(x0 - (y1 - y0), x0 - (y1 - y0) + reveal * (x1 - x0 + (y1 - y0)), gap)
        self.hatch.set_segments([[(x, y1), (x + (y1 - y0), y0)] for x in xs])
        self.hatch.set_alpha(al)
        self.hatch.set_visible(al > 0.002 and reveal > 0)
        self.extra.set_alpha(al * smooth_fn((local - 1.5) / 0.3))
        wa = smooth_fn((local - 1.4) / 0.7)
        self.word.set_alpha(al * wa)
        rise = (1 - wa) * 14  # the wordmark settles upward by 14 px as it appears
        self.w1.move(960, 770 + rise)
        self.w2.move(960, 822 + rise)
