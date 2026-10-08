# Episode 2 plan: Dhaka, century by century

Status: PLAN ONLY. Nothing built or rendered. Waiting for approval.
Checked: 2026-10-09. Every source below is also in `source_log.csv` (marked CANDIDATE).

Legend: [OK] = checked against the named source. [TO VERIFY] = not yet checked, do not use on screen until it is.

---

## 1. What data we need (city extent by period)

| Period | What to show | Best source | Status |
|---|---|---|---|
| Before 1600 (Sultanate / pre-Mughal) | Small core by the Buriganga and Dulai canal, 1.55 km2 | Rahman et al. 2016 (area figure; boundary in Fig 1/4) | [OK] area figure, from the paper |
| Earliest dated building | Binat Bibi Mosque, 1457 | Rahman et al. 2016 Table 2, citing Dani 1962 | [OK] as "according to Dani, cited by Rahman et al." |
| 17th c. (Mughal capital) | Mughal city, 12.93 km2 | Rahman et al. 2016, Fig 4 polygon | [OK] area figure |
| Capital founded | 1608 or 1610 (sources disagree) | Banglapedia vs. others | [TO VERIFY] - pick one source and say "c. 1610" |
| 1717 | Capital moved to Murshidabad, growth stops | Rahman et al. 2016, citing Dani 1962 | [OK] as cited claim |
| 1780 | Rennell's survey map (show the actual old map) | Rennell, Bengal Atlas (public domain) | [OK] map is PD; scan choice [TO VERIFY] |
| 1840 | Taylor's map of Dacca (show old map) | Taylor 1840, British Library scan (PD) | [OK] licence |
| 1859 | Shrunken city, 5.4 km2 (about 58% smaller than Mughal) | Rahman et al. 2016, Fig 5 (from Surveyor General's map 1859) | [OK] area figures |
| 1905 / 1911 | New civil station at Ramna (capital of Eastern Bengal and Assam) | Allen 1912 gazetteer (PD) | [TO VERIFY] dates and extent |
| 1950s | Built-up area on US Army Map Service sheet NF 46-1 | AMS 1955/1960 (US federal work) | [TO VERIFY] scan rights + date |
| 1975, 1990, 2000, 2020 | Built-up area from satellites | GHSL GHS-BUILT-S R2023A (CC BY 4.0) | [OK] licence; our threshold choice must be stated |
| Today | Megacity size | Rahman et al. quote 1,528 km2 / 14.5 million (Dewan & Corner 2013) - this is an older figure | [TO VERIFY] use a current published figure instead |
| Population per period | Optional on-screen counter | Census of India 1872-1941 via Allen 1912 (PD); Bangladesh census | [TO VERIFY] every number |

Important honesty points for the script:
- The 1600 / 1700 / 1859 shapes are a *reconstruction from texts* (Rahman et al.), not a survey.
- The 1975+ shapes come from *satellite data*. They are a different method, so the jump between 1950s and 1975 must not be shown as exact growth.
- Do not compute any areas ourselves from our drawn shapes. Only show the published numbers.

## 2. Sources and licences (monetized-channel check)

Usable:
- **Rahman, Zaman & Hafiz (2016)**, City Territ Archit 3:7, doi:10.1186/s40410-016-0036-y. **CC BY 4.0** (stated in the PDF). We may redraw its boundaries with credit + "changes made". Avoid Fig 7 (contains a Geological Survey of Bangladesh map).
- **GHSL built-up surface, European Commission JRC**. **CC BY 4.0** (copyright.txt in the data folder). Credit: "GHSL, European Commission JRC".
- **Rennell 1780 map, Taylor 1840 map, Allen 1912 gazetteer**: public domain (old works).
- **OpenStreetMap** (rivers at city scale): **ODbL**, credit "(c) OpenStreetMap contributors".
- **Wikidata** (landmark coordinates): **CC0**.
- **Natural Earth** (only for the wide "where is Dhaka" shot): public domain.

Avoid / be careful:
- **David Rumsey Map Collection scans**: CC BY-NC-SA = **non-commercial**. The big Rennell scan on Wikimedia Commons came from Rumsey, so use a different scan (Internet Archive or the Spanish BVPB copy, which is CC BY - to verify).
- **Banglapedia, Dani (1962), Dewan & Corner (2013)**: copyrighted. Facts can be cited, but do not copy their maps or text.
- **Alamy / stock "1924 Dacca city plan"**: paid stock, do not use.
- **Edinburgh (Geddes papers) 1911 maps**: rights not stated online - ask the archive first.

## 3. How we would draw it in the engine

The engine today is built for country-scale maps (Natural Earth, shapes picked by country name).
Dhaka is a city: the whole Mughal city is about 10 km long, so we need detailed local shapes.

New things needed (small, one at a time, each with simple comments):

1. **GeoJSON regions.** New selector `file:data/ep02/mughal_1700.geojson`, so a region can come from
   a shape we traced. Uses Python's built-in `json` + shapely, no new install.
2. **City-scale base map.** A local rivers/water layer loaded from a GeoJSON file (from OpenStreetMap),
   because Natural Earth has almost nothing inside one city.
3. **`morph` event.** Smoothly change the city fill from one period's shape to the next
   (cross-fade, and a dashed "ghost" outline of the old extent so shrinking in 1859 is visible).
4. **`image` event.** Fade in a scanned old map (Rennell 1780, Taylor 1840) pinned to 3 known points
   (e.g. Lalbagh Fort, Dhakeshwari Temple, a river bend), then fade back to the clean map.
5. **`counter` event.** On-screen number that counts up, e.g. "1.55 km2 -> 12.93 km2", with the
   source shown under it.
6. **`cite` event.** A small source line shown while a fact is on screen
   (e.g. "Area: Rahman et al. 2016, CC BY 4.0").
7. **Scale bar** (km), so viewers can judge size at city zoom.

How we would make the shapes:
- Georeference Rahman Fig 4 and Fig 5 using landmarks with Wikidata (CC0) coordinates, trace the
  outline as GeoJSON, and log it as "redrawn from Rahman et al. 2016".
- Optional, better: email the authors and ask for their GIS boundary file.
- GHSL: download only the tile covering Dhaka, turn the grid into an outline with a stated rule
  (e.g. "cells at least 20% built-up"), and say that rule in the description.

## 4. Questions for you before building
1. OK to rely mainly on Rahman et al. 2016 for 1600-1859?
2. Should the old maps (Rennell / Taylor) appear on screen, or only our clean redrawings?
3. Include population numbers, or extent only?
4. Should I email the authors for their boundary file?
