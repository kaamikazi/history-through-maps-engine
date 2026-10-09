# Plan: documentary features for the engine ("their format, our look")

Status: PLAN ONLY. Nothing built. Waiting for approval.
Checked: 2026-10-09. Reference video: Kings and Generals, "How Old Is Indian Civilization?"
(youtube.com/watch?v=rVT9cmsI3cE). I could only read its title and channel: YouTube showed a
CAPTCHA, which I did not solve. What follows is based on the channel's well-known general format,
NOT a frame-by-frame study of that video. If you paste its description/chapter list or
transcript here, I can match the structure more closely.

Decision (2026-10-09): take their FORMAT, keep OUR engraved-atlas LOOK (brand book stays valid).

---

## 1. What we take, and what we never take

Take (format and techniques, not protected): long-form narrated documentary (15-30 min), clear
chapters, territories that change over time, movement arrows for migrations / campaigns / trade,
battle and army markers, illustrations to show people and places, terrain, year counters,
sources in the description.

Never take: their artwork, music, intro/sting, map designs, icons, script or narration, and no
tracing of their maps. Topics are researched by us from our own cited sources. Our look stays
the engraved atlas (Lamplight / Paper), which is also what makes us look different from them.

## 2. New features (in suggested build order)

### Phase A - needed for any long documentary
1. **`route` event - movement arrows.** Waypoints in lon/lat, smoothed into a curve, engraved on
   progressively with an arrowhead at the tip (the brand's map-style already defines the route
   arrow). Solid ink = documented route; dashed = uncertain or disputed route. Optional label
   along the route ("c. 1500 BCE?" style labels must carry a source).
2. **`marker` event - map symbols.** Battle cross, site ring (for archaeological sites),
   capital, and an **army counter** (small engraved plate with name and size, e.g.
   "Bengal army - c. 50,000 (est.)" with unit and year, per brand rule). A counter can travel
   along a `route`.
3. **Parallel rendering.** Today's speed is about 2 frames a second, so a 20-minute video would
   take about 5 hours. Render chapters in separate processes on the 16 CPU cores, then join them
   with ffmpeg: about 30-45 minutes instead. Same output, just faster.
4. **YouTube description generator.** Builds the description from the episode: hook line,
   chapter timestamps (from `chapter` events), sources (from `source_log.csv` rows for that
   video), music credits, About text (brand/strategy.md).

### Phase B - territories over time (also needed for Episode 2, Dhaka)
5. **GeoJSON regions**: selector `file:data/<episode>/<name>.geojson`, so we can use shapes we
   drew from cited sources (historical borders, city extents).
6. **`territory` timeline event**: one territory with a list of periods, each with a shape.
   Between periods, land GAINED hatches in (the brand's engraving motion) and land LOST fades
   to a dashed "ghost" outline. We do NOT invent in-between borders by morphing shapes, because
   that would show borders that never existed. Honest and on-brand.

### Phase C - pictures and terrain
7. **`image` event - illustration plate.** A public-domain / CC0 artwork in a double-ruled
   cartouche over the dimmed map, with a slow pan/zoom, and an on-screen credit line
   (artist, title, date, collection, licence) as the brand requires. Optional toning into the
   brand palette (logged as "changes made").
8. **`map_overlay` event**: a scanned old map pinned to 3 known points and faded over the base
   map (from the Episode 2 plan: Rennell 1780, Taylor 1840).
9. **Terrain**: Natural Earth 1:10m shaded relief, cropped to the region and blended softly
   into the land under the hatching. Later, optionally, engraved-style hachures.

### Phase D - sound
10. **Music bed + sting sound in `add_voice.py`**: `--music file` placed 18-20 dB under the
    narration (brand rule), fading in and out; `--sting-sfx file` at the sting time.

## 3. Sources for these features (licence checked 2026-10-09)

| Need | Source | Licence | Use? |
|---|---|---|---|
| Terrain | Natural Earth 10m shaded relief (SR_HR 42 MB / SR_LR 24 MB) | Public domain: "All versions of Natural Earth raster + vector map data ... are in the public domain" | Yes |
| Illustrations | The Met Open Access | CC0 for public-domain works (check the OA icon on each item) | Yes |
| Illustrations | Cleveland Museum of Art Open Access | CC0, "without fees or restriction" | Yes |
| Illustrations / old maps | Wikimedia Commons | Per file. Always check where the scan came from (the Rumsey lesson) | Per item |
| Site / place coordinates | Wikidata | CC0 | Yes |
| Music / sound effects | YouTube Audio Library | Monetizable, no Content ID claims; Creative Commons tracks need the artist credited in the description | Yes (you download it in YouTube Studio) |
| Ready-made historical borders | aourednik/historical-basemaps (GitHub) | GPL-3.0, but built from "diverse sources" incl. old student sites whose rights are unclear | **No** - licence chain not clean; we draw our own from cited sources |
| Old map scans | David Rumsey collection | CC BY-NC-SA (non-commercial) | **No** |
| Anything from Kings and Generals | their videos | copyrighted | **No** |

## 4. How we would test it
A neutral **feature demo episode** (`episodes/ep00_feature_demo.json`) with made-up placeholder
text and no historical claims, so we can check every new event without fact-checking a script.
Real episodes then use the features once their facts are sourced.

## 5. Questions for you
1. Build in the order A -> B -> C -> D, committing and showing test frames after each phase?
2. For Phase C art: is it OK to tone artworks into the brand colours, or show them as they are?
3. Is a feature-demo episode with placeholder text OK for testing?
