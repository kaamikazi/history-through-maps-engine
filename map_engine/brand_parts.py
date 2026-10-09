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


# --------------------------------------------------------------------------
# 5.  ROUTES (movement arrows) AND MAP MARKERS  - documentary features, phase A
# --------------------------------------------------------------------------
def smooth_curve(xy, samples=24):
    """Turn a few waypoints into a smooth curve that passes through every point
    (a "Catmull-Rom" curve). xy is an N x 2 array in map units."""
    xy = np.asarray(xy, float)
    if len(xy) < 3:
        t = np.linspace(0, 1, samples)[:, None]
        return xy[0] + (xy[-1] - xy[0]) * t
    p = np.vstack([xy[0] * 2 - xy[1], xy, xy[-1] * 2 - xy[-2]])  # extra point at each end
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for s in np.linspace(0, 1, samples, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s * s
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * s ** 3))
    out.append(xy[-1])
    return np.array(out)


class Route:
    """An arrow that is engraved along a path (a migration, a campaign, a trade route).
    Solid line = documented route. Dashed line = uncertain or disputed route.
    The arrowhead keeps the same size on screen at every zoom."""

    def __init__(self, ax, xy, style, color, uncertain=False, zorder=8.5):
        self.xy = smooth_curve(xy)
        seg = np.hypot(*np.diff(self.xy, axis=0).T)
        self.cum = np.concatenate([[0], np.cumsum(seg)])  # distance along the curve
        self.st = style
        ls = (0, tuple(style.get("dash_px", [10, 7]))) if uncertain else "solid"
        (self.line,) = ax.plot([], [], color=color, lw=style["width_px"] * PT, linestyle=ls, zorder=zorder,
                               solid_capstyle="round", dash_capstyle="butt")
        self.head = MplPolygon(np.zeros((3, 2)), closed=True, fc=color, ec="none", zorder=zorder + 0.1)
        ax.add_patch(self.head)
        self.progress = 0.0

    def point_at(self, p):
        """Position and direction on the curve after fraction p (0..1) of its length."""
        d = p * self.cum[-1]
        k = int(np.clip(np.searchsorted(self.cum, d), 1, len(self.cum) - 1))
        f = (d - self.cum[k - 1]) / max(self.cum[k] - self.cum[k - 1], 1e-12)
        pos = self.xy[k - 1] + (self.xy[k] - self.xy[k - 1]) * f
        direction = self.xy[k] - self.xy[k - 1]
        return pos, direction / max(np.hypot(*direction), 1e-12), k

    def update(self, p, alpha, px_per_unit):
        """Draw the first fraction p of the route, with the arrowhead at its tip."""
        self.progress = p
        if p <= 0 or alpha <= 0.002:
            self.line.set_visible(False)
            self.head.set_visible(False)
            return
        tip, dirn, k = self.point_at(p)
        L = self.st["head_px"] / px_per_unit                     # arrowhead length in map units
        back = tip - dirn * L * 0.7                               # the line stops inside the head
        pts = np.vstack([self.xy[:k], back])
        self.line.set_data(pts[:, 0], pts[:, 1])
        normal = np.array([-dirn[1], dirn[0]])
        self.head.set_xy([tip, tip - dirn * L + normal * L * 0.45, tip - dirn * L - normal * L * 0.45])
        for a in (self.line, self.head):
            a.set_alpha(alpha)
            a.set_visible(True)


class Marker:
    """A map symbol that keeps its size on screen: battle cross, site ring, capital,
    or an army counter (a small engraved plate). It can stay put or ride along a Route."""

    def __init__(self, ov, fonts, P, e, mstyle):
        self.ov = ov
        self.patches = []   # drawn around (0, 0), then moved into place every frame
        self.texts = []     # (PathText, dx, dy)
        kind = e.get("kind", "site")
        ms = mstyle[kind]
        col = ms.get("color", P["ink"])
        if kind == "battle":
            # a cross like the brand legend's battle symbol: tall upright, short crossbar
            s, w = ms["size_px"], ms["width_px"]
            upright = MPath.unit_rectangle().transformed(Affine2D().scale(w, s).translate(-w / 2, -s * 0.6))
            bar = MPath.unit_rectangle().transformed(Affine2D().scale(s * 0.62, w).translate(-s * 0.31, -s * 0.3))
            self._patch(PathPatch(MPath.make_compound_path(upright, bar), fc=col, ec=P["ground"], lw=1.2 * PT))
        elif kind == "site":  # hollow ring: a place known from archaeology
            self._patch(Circle((0, 0), ms["size_px"] / 2, fc="none", ec=col, lw=ms["width_px"] * PT))
        elif kind == "capital":  # ring with a dot inside
            self._patch(Circle((0, 0), ms["size_px"] / 2, fc="none", ec=col, lw=ms["width_px"] * PT))
            self._patch(Circle((0, 0), ms["size_px"] / 5, fc=col, ec="none"))
        elif kind == "army":  # engraved plate with the army's name and (estimated) size
            lines = [e.get("name", "")] + ([e["size"]] if e.get("size") else [])
            fs = ms["size_px"]
            heights = [fs, fs * 0.8]
            texts = []
            for i, txt in enumerate(lines):
                t = PathText(ov, txt, fonts["caps" if i == 0 else "body_italic"], heights[i],
                             P["ink"] if i == 0 else P["ink-muted"], ha="center",
                             tracking=2 if i == 0 else 0, zorder=7.2)
                texts.append(t)
            width = max(t.patch.get_path().get_extents().width for t in texts) + 2 * fs
            height = fs * (1.0 + 1.25 * len(lines))
            top = -height - fs * 0.9   # the plate floats just above the point
            self._patch(Rectangle((-width / 2, top), width, height, fc=P["ground-raised"], ec=P["ink"], lw=2.4 * PT), z=7.0)
            self._patch(Rectangle((-width / 2 + 5, top + 5), width - 10, height - 10, fc="none", ec=P["ink"], lw=1 * PT), z=7.1)
            self._patch(MplPolygon([(-fs * 0.4, top + height), (fs * 0.4, top + height), (0, 0)], closed=True,
                                   fc=P["ink"], ec="none"), z=7.1)  # little pointer down to the place
            y = top + fs * 1.45
            for t, h in zip(texts, heights):
                self.texts.append((t, 0, y))
                y += h * 1.4
        if e.get("label"):
            lab = PathText(ov, e["label"], fonts["caps"], ms.get("label_px", 24), P["ink"], tracking=3, zorder=7.2)
            if kind == "battle":  # battle labels sit above-right of the cross, clear of any place label
                self.texts.append((lab, ms["size_px"] * 0.45, -ms["size_px"] * 0.55))
            else:
                self.texts.append((lab, ms.get("size_px", 20) * 0.8 + 8, 9))

    def _patch(self, p, z=7.1):
        p.set_zorder(z)
        self.ov.add_patch(p)
        self.patches.append(p)

    def place(self, px, py):
        """Move the whole symbol so its point sits at overlay pixel (px, py)."""
        tr = Affine2D().translate(px, py) + self.ov.transData
        for p in self.patches:
            p.set_transform(tr)
        for t, dx, dy in self.texts:
            t.move(px + dx, py + dy)

    def set_alpha(self, a):
        for p in self.patches:
            p.set_alpha(a)
            p.set_visible(a > 0.002)
        for t, _, _ in self.texts:
            t.set_alpha(a)


# --------------------------------------------------------------------------
# 6.  PICTURES  - documentary features, phase C
# --------------------------------------------------------------------------
def load_picture(path, max_side=2400, tone=None):
    """Open an image file as an RGB array (0..1), shrunk so its longest side is at most
    `max_side` pixels (faster to draw). tone = (dark, light) colours: turn the picture into
    two brand colours (a "duotone", like an engraving printed in ink on paper)."""
    from PIL import Image
    from matplotlib.colors import to_rgb
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    arr = np.asarray(im, dtype=np.float32) / 255.0
    if tone:
        grey = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)  # brightness of each pixel
        dark, light = np.array(to_rgb(tone[0])), np.array(to_rgb(tone[1]))
        arr = dark + (light - dark) * grey[..., None]
    return np.clip(arr, 0, 1)


class ImagePlate:
    """An illustration (a public-domain or CC0 artwork) in a double-ruled plate over the dimmed
    map, with a slow pan/zoom ("Ken Burns" move) and a credit line, as the brand asks for.

    pan: {"from": [cx, cy, zoom], "to": [cx, cy, zoom]}
         cx, cy = which point of the picture is in the middle (0..1 across / down)
         zoom   = 1.0 shows the whole width or height (whichever fills the window), 1.3 is closer
    """

    def __init__(self, ov, fonts, P, e, base_dir):
        self.ov, self.e = ov, e
        tone = (P["ground-sunk"], P["ink"]) if e.get("tone", True) else None
        self.img = load_picture(base_dir / e["file"], tone=tone)
        self.ih, self.iw = self.img.shape[:2]
        w, h = e.get("plate", [1120, 720])
        pos = e.get("pos", "center")
        x = {"left": 96, "center": (1920 - w) / 2, "right": 1920 - 96 - w}[pos]
        y = (1080 - h) / 2 - 20
        self.g = Group()
        # layers 7.6-7.9: above map markers (7.0-7.2), below chapter cards (8+)
        _rect(ov, self.g, 0, 0, 1920, 1080, fc=P["ground"], z=7.6, alpha=e.get("dim", 0.6))
        _rect(ov, self.g, x, y, w, h, fc=P["ground-raised"], ec=P["ink"], lw_px=3, z=7.65)
        _rect(ov, self.g, x + 10, y + 10, w - 20, h - 20, ec=P["ink"], lw_px=1.2, z=7.9)
        # the picture window: inside the inner rule, leaving a strip at the bottom for the credit
        self.box = (x + 24, y + 24, w - 48, h - 48 - 40)
        bx, by, bw, bh = self.box
        self.clip = Rectangle((bx, by), bw, bh, transform=ov.transData)
        self.im = ov.imshow(self.img, extent=(bx, bx + bw, by + bh, by), origin="upper",
                            interpolation="bilinear", zorder=7.7, aspect="auto")
        self.im.set_clip_path(self.clip)
        self.g.add(self.im)
        _rect(ov, self.g, bx, by, bw, bh, ec=P["ink"], lw_px=1.2, z=7.75)
        if e.get("credit"):
            _text(ov, self.g, fonts, "body_italic", e["credit"], 22, P["ink-muted"], x + w / 2, y + h - 30,
                  ha="center", z=7.9)

    def draw(self, t, fade_fn, smooth_fn):
        e = self.e
        al = fade_fn(t, e["t"], 0.6, e["t"] + e["dur"], 0.6)
        self.g.set_alpha(al)
        if al <= 0.002:
            return
        pan = e.get("pan", {"from": [0.5, 0.5, 1.0], "to": [0.5, 0.5, 1.12]})
        u = smooth_fn((t - e["t"]) / max(e["dur"], 1e-6)) if e.get("ease", True) else \
            min(max((t - e["t"]) / e["dur"], 0), 1)
        cx, cy, zoom = [a + (b - a) * u for a, b in zip(pan["from"], pan["to"])]
        bx, by, bw, bh = self.box
        # scale so the picture COVERS the window at zoom 1, then zoom in from there
        s = max(bw / self.iw, bh / self.ih) * zoom
        w, h = self.iw * s, self.ih * s
        # keep the window inside the picture (no empty edges)
        left = min(max(bx + bw / 2 - cx * w, bx + bw - w), bx)
        top = min(max(by + bh / 2 - cy * h, by + bh - h), by)
        self.im.set_extent((left, left + w, top + h, top))


# --------------------------------------------------------------------------
# 7.  GENERALS AND TROOPS  - portraits in medallions, formations of soldier figures
# --------------------------------------------------------------------------
def _soldier_paths(kind):
    """One soldier figure, drawn by us (no outside art), in a box about 40 units tall.
    (0, 0) is between the feet; y goes DOWN (overlay pixels). Returns (filled shapes, lines)."""
    def poly(pts):
        return MPath(pts + [pts[0]], [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 1) + [MPath.CLOSEPOLY])

    def circle(cx, cy, r):
        return MPath.circle((cx, cy), r)

    fills, lines = [], []
    if kind == "cavalry":
        fills.append(poly([(-15, -10), (-13, -18), (6, -19), (12, -24), (17, -22), (13, -15), (10, -10)]))  # horse
        for x in (-12, -8, 5, 9):  # four legs
            fills.append(poly([(x, -11), (x + 2.5, -11), (x + 2.5, 0), (x, 0)]))
        fills.append(poly([(-4, -19), (2, -19), (1, -31), (-3, -31)]))  # rider's body
        fills.append(circle(-1, -34, 3.2))                               # rider's head
        lines.append([(4, -44), (-2, -22)])                              # lance
    else:
        fills.append(circle(0, -33, 3.6))                                     # head
        fills.append(poly([(-5, -28), (5, -28), (6.5, -12), (-6.5, -12)]))   # body
        fills.append(poly([(-5, -12), (-1.5, -12), (-2, 0), (-5.5, 0)]))     # legs
        fills.append(poly([(1.5, -12), (5, -12), (5.5, 0), (2, 0)]))
        if kind == "archers":
            a = np.linspace(-1.1, 1.1, 14)
            lines.append(list(zip(8 + 9 * np.cos(a), -20 + 13 * np.sin(a))))  # the bow
            lines.append([(8 + 9 * np.cos(-1.1), -20 + 13 * np.sin(-1.1)),
                          (8 + 9 * np.cos(1.1), -20 + 13 * np.sin(1.1))])     # bowstring
        else:  # infantry: shield and spear
            fills.append(MPath.unit_circle().transformed(Affine2D().scale(4.5, 7).translate(-6.5, -19)))
            lines.append([(7.5, -44), (7.5, 0)])
    return fills, lines


class Troops:
    """A formation of soldier figures (our own drawings) in one side's colour, with a banner.
    It keeps its size on screen, can stand still or march along a route, and turns to face
    the way it is going. Numbers of figures are only a picture of a force, never its size:
    the real (sourced) size belongs in a label like 'c. 50,000 (est.)'."""

    def __init__(self, ov, fonts, P, e, color):
        self.ov = ov
        kind = e.get("kind", "infantry")
        rows, cols = e.get("rows", 2), e.get("cols", 5)
        scale = e.get("size_px", 34) / 44.0          # figure height on screen
        gap_x, gap_y = 17 * scale * 1.6, 12 * scale * 1.6
        if kind == "cavalry":
            gap_x *= 1.5
        rng = np.random.default_rng(e.get("seed", 3))
        f_one, l_one = _soldier_paths(kind)
        fills, lines = [], []
        # back rows first, so front rows are drawn over them
        for r in range(rows):
            for c in range(cols):
                jx, jy = rng.uniform(-2, 2) * scale, rng.uniform(-1.5, 1.5) * scale
                ox = (c - (cols - 1) / 2) * gap_x + (r % 2) * gap_x / 2 + jx
                oy = (r - (rows - 1)) * gap_y + jy
                tr = Affine2D().scale(scale).translate(ox, oy)
                fills += [p.transformed(tr) for p in f_one]
                lines += [tr.transform(np.array(ln, float)) for ln in l_one]
        # banner at the front corner: a pole and a flag in the side's colour
        bx = (cols - 1) / 2 * gap_x + gap_x * 0.9
        pole = [(bx, 0), (bx, -62 * scale)]
        flag = MPath([(bx, -62 * scale), (bx + 22 * scale, -57 * scale), (bx, -50 * scale), (bx, -62 * scale)],
                     [MPath.MOVETO, MPath.LINETO, MPath.LINETO, MPath.CLOSEPOLY])
        fills.append(flag)
        lines.append(np.array(pole))
        self.body = PathPatch(MPath.make_compound_path(*fills), fc=color, ec=P["ink"], lw=1.1 * PT, zorder=7.05)
        self.gear = LineCollection(lines, colors=P["ink"], linewidths=1.6 * PT, zorder=7.06)
        ov.add_patch(self.body)
        ov.add_collection(self.gear)
        self.texts = []
        if e.get("label"):  # e.g. "Army A - c. 0,000 (est.)": the sourced number goes here
            lab = PathText(ov, e["label"], fonts["caps"], 22, P["ink"], ha="center", tracking=2, zorder=7.2)
            self.texts.append((lab, 0, 30 * scale))

    def place(self, px, py, facing_left=False):
        flip = Affine2D().scale(-1 if facing_left else 1, 1)
        tr = flip + Affine2D().translate(px, py) + self.ov.transData
        self.body.set_transform(tr)
        self.gear.set_transform(tr)
        for t, dx, dy in self.texts:
            t.move(px + dx, py + dy)

    def set_alpha(self, a):
        for art in (self.body, self.gear):
            art.set_alpha(a)
            art.set_visible(a > 0.002)
        for t, _, _ in self.texts:
            t.set_alpha(a)


class Portrait:
    """A general's (or ruler's) portrait in an engraved oval medallion, with name and dates
    under it and a small credit line. It can sit beside a place on the map (with a thin leader
    line to that place) or follow a route, like the army it leads.
    The picture must be public domain / CC0 and logged; the credit is shown under the name."""

    def __init__(self, ov, fonts, P, e, base_dir):
        self.ov, self.e = ov, e
        tone = (P["ground-sunk"], P["ink"]) if e.get("tone", True) else None
        img = load_picture(base_dir / e["file"], max_side=900, tone=tone)
        h_img, w_img = img.shape[:2]
        R = e.get("size_px", 120) / 2                # medallion radius (height = size)
        rx, ry = R * 0.82, R                         # an upright oval
        self.parts = []                              # artists drawn around (0, 0)
        from matplotlib.patches import Ellipse
        self.clip = Ellipse((0, 0), 2 * rx, 2 * ry)
        # the picture: fill the oval ("cover"), centred on the face position given (0..1)
        cx, cy = e.get("face", [0.5, 0.35])
        s = max(2 * rx / w_img, 2 * ry / h_img) * e.get("zoom", 1.0)
        W, H = w_img * s, h_img * s
        left, top = -cx * W, -cy * H
        left, top = min(max(left, rx - W), -rx), min(max(top, ry - H), -ry)
        self.im = ov.imshow(img, extent=(left, left + W, top + H, top), origin="upper", zorder=7.31,
                            interpolation="bilinear", aspect="auto")
        for art in (Ellipse((0, 0), 2 * rx + 16, 2 * ry + 16, fc=P["ground-raised"], ec=P["ink"], lw=3 * PT, zorder=7.3),
                    Ellipse((0, 0), 2 * rx + 6, 2 * ry + 6, fc="none", ec=P["ink"], lw=1.2 * PT, zorder=7.32),
                    Ellipse((0, 0), 2 * rx, 2 * ry, fc="none", ec=P["ink"], lw=1.6 * PT, zorder=7.33)):
            ov.add_patch(art)
            self.parts.append(art)
        self.texts = []
        y = ry + 34
        name = PathText(ov, e.get("name", ""), fonts["caps"], 26, P["ink"], ha="center", tracking=4, zorder=7.35)
        self.texts.append((name, 0, y))
        if e.get("dates"):
            self.texts.append((PathText(ov, e["dates"], fonts["body_italic"], 20, P["ink-muted"], ha="center",
                                        zorder=7.35), 0, y + 24))
        if e.get("credit"):
            self.texts.append((PathText(ov, e["credit"], fonts["body_italic"], 15, P["ink-muted"], ha="center",
                                        zorder=7.35), 0, y + 46))
        # plate behind the name so it reads over any map
        self.plate = Rectangle((-max(rx + 40, 130), ry + 8), 2 * max(rx + 40, 130), 64 if e.get("credit") else 50,
                               fc=P["ground-raised"], ec=P["ink"], lw=1.2 * PT, zorder=7.29)
        ov.add_patch(self.plate)
        self.parts.append(self.plate)
        (self.leader,) = ov.plot([], [], color=P["ink"], lw=1.4 * PT, zorder=7.28)
        self.offset = e.get("offset", [-170, -150])  # where the medallion sits, relative to its place (pixels)

    def place(self, ax_px, ax_py):
        """ax_px, ax_py = the place on screen it belongs to (the army, the city)."""
        dx, dy = self.offset
        mx, my = ax_px + dx, ax_py + dy
        tr = Affine2D().translate(mx, my) + self.ov.transData
        for p in self.parts:
            p.set_transform(tr)
        self.im.set_transform(tr)
        self.clip.set_transform(tr)
        self.im.set_clip_path(self.clip)
        for t, x, y in self.texts:
            t.move(mx + x, my + y)
        self.leader.set_data([ax_px, mx], [ax_py, my])

    def set_alpha(self, a):
        for p in self.parts + [self.im, self.leader]:
            p.set_alpha(a)
            p.set_visible(a > 0.002)
        for t, _, _ in self.texts:
            t.set_alpha(a)
