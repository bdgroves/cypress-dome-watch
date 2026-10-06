# 🌳 CYPRESS-DOME-WATCH

**Reading water depth from the shape of a forest.**

Across Big Cypress National Preserve, bald cypress grow in round domes: short trees at the dry edges, the tallest at the deep, wet center. Seen from above, a dome's height profile is a readout of the water beneath it. CYPRESS-DOME-WATCH finds these domes automatically in LiDAR canopy height, tracks how long each one holds water through the seasons, and asks whether domes acted as refuges during the February 2026 Big Cypress fire.

**🌐 Live site: [brooksgroves.com/cypress-dome-watch](https://brooksgroves.com/cypress-dome-watch/)**

> Part of the GeoAI & Remote Sensing Lab · sibling of [ANOLE-WATCH](https://github.com/bdgroves/Anole-watch) and [ALPINE-WATCH](https://github.com/bdgroves/Alpine-watch)

---

## Status: 🌿 working

| Piece | State |
|---|---|
| 3DEP LiDAR tile finder (`src/find_lidar.py`) + "Find LiDAR tiles" Action | ✅ written: run it from the Actions tab |
| Dome detector (`src/detect_domes.py`): smoothed local maxima + circularity | ✅ finds 7 of 9 planted domes in a synthetic test canopy (overlapping domes merge; tune next) |
| Landing page (`docs/index.html`) | ✅ placeholder |
| Canopy height model pipeline (`src/build_chm.py`): picks tiles near a target, streams them through PDAL (ground → DTM, everything else → height above ground), mosaics, detects domes | ✅ built — run **Build canopy model** from Actions |
| Map page: canopy height over satellite imagery, dome circles, Kirby Storter Boardwalk ground-truth pin | ✅ |

### Third run (Oct 6, 2026): streamed, 36 km²

The canopy model no longer downloads tiles. The same 2018 West Everglades topobathymetric survey is in the USGS Entwine Point Tile archive on AWS, so `src/chm_ept.py` streams it a 1 km square at a time (36 chunks in parallel on Actions, workflow **Canopy model (streamed)**): one PDAL pass per chunk, bathymetric bottom (class 40) counted as ground, height above the nearest ground points, tallest return per 1 m cell. The window is 6 × 6 km, centred 2 km south of the Kirby Storter Boardwalk so it sits fully inside the survey.

- 89% of cells have returns; median canopy 1.4 m, 95th percentile 15.6 m, tallest 29.9 m
- **166 dome candidates** (up from 12), with a radial height profile each (`profile_m`: mean canopy in rings of 0.2 radius out to 1.6 radii)
- **150 of them rise more than 2 m from rim to centre**; the median rise is about 6 m. The site now shows the average dome.

Next: Sentinel-1 radar (C-band double bounce lights up flooded forest) for a water time series per dome, then compare hydroperiod with the dome's shape.

### Second run (Sep 27, 2026): 4 tiles, isolation test on

12 candidates, down from 27. Every strand chunk is gone; what's left are small, round, isolated tree islands (59–80 m across, 10–14 m tall) scattered through the prairie, which is what cypress domes look like. Nearest to the boardwalk: 78 m across, 13.9 m tall, 100 m from the trailhead.

### First real run (Sep 27, 2026)

Three tiles of the 2018 West Everglades topobathymetric survey around the Kirby Storter Boardwalk: median canopy 0.4 m (open prairie), 95th percentile 12.8 m, tallest 29.7 m, 27 candidates. Two lessons:

- **One tile is mostly empty.** Tile e1495n0430 has points in only ~20% of its cells, even after counting bathymetric bottom (class 40) as ground. It's a gap in the survey itself (likely the project edge), not a processing bug. The per-tile coverage check in `chm_meta.json` now reports this.
- **Strands aren't domes.** A cypress strand chopped up by the watershed looks like a chain of round domes. Candidates now have to pass an isolation test: at most 25% forest on a ring 1.3–2 radii out. Trade-off: a real dome touching a strand can get dropped too.

### First look at the LiDAR (Sep 2026)

The test area is covered by **375 point-cloud tiles, about 82 GB**, from three 2018 USGS 3DEP collections:

| Collection | Tiles |
|---|---|
| FL_Southeast_2018_D18_SUPPLEMENTAL | 168 |
| FL_Peninsular_FDEM_2018_D19_DRRA (Collier County) | 162 |
| FL_WestEvergladesNP_2018_B18 | 45 |

Tiles run ~220 MB each, so the plan is to start with a handful over domes visible in aerial imagery rather than downloading everything. Full list: `data/lidar_tiles.json`.
| Sentinel-2 NDWI per dome · fire-refugia comparison | ⬜ later |

## Data sources

- **USGS 3DEP LiDAR** (The National Map API): canopy height model
- **Sentinel-2 SR**: NDWI standing-water time series per dome
- **NASA UAVSAR**: water under the canopy (stretch goal)
- **Feb 2026 Big Cypress fire perimeter**: fire-refugia test

## Run it

```bash
pixi install
pixi run find-lidar   # lists 3DEP LiDAR tiles for Big Cypress → data/lidar_tiles.json
pixi run demo         # runs the dome detector on a synthetic canopy
TARGET=25.8679,-81.1540 TILES=3 pixi run build   # real LiDAR → docs/data/ (needs ~1 GB disk per tile)
```

## Build prompt (for the next session)

> Help me build out CYPRESS-DOME-WATCH. Download a few 3DEP LiDAR tiles from data/lidar_tiles.json, build a 1 m canopy height model with PDAL, and run src/detect_domes.py on it. Tune the smoothing and circularity thresholds against domes I can see in aerial imagery. Then add a Sentinel-2 NDWI time series per detected dome, and compare pre/post-fire NDVI against the February 2026 Big Cypress fire perimeter to test the fire-refugia idea.
