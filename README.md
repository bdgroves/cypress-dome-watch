# 🌳 CYPRESS-DOME-WATCH

**Reading water depth from the shape of a forest.**

Across Big Cypress National Preserve, bald cypress grow in round domes: short trees at the dry edges, the tallest at the deep, wet center. Seen from above, a dome's height profile is a readout of the water beneath it. CYPRESS-DOME-WATCH finds these domes automatically in LiDAR canopy height, tracks how long each one holds water through the seasons, and asks whether domes acted as refuges during the February 2026 Big Cypress fire.

**🌐 Live site: [brooksgroves.com/cypress-dome-watch](https://brooksgroves.com/cypress-dome-watch/)**

> Part of the GeoAI & Remote Sensing Lab · sibling of [ANOLE-WATCH](https://github.com/bdgroves/Anole-watch) and [ALPINE-WATCH](https://github.com/bdgroves/Alpine-watch)

---

## Status: 🌱 scaffold

| Piece | State |
|---|---|
| 3DEP LiDAR tile finder (`src/find_lidar.py`) + "Find LiDAR tiles" Action | ✅ written: run it from the Actions tab |
| Dome detector (`src/detect_domes.py`): smoothed local maxima + circularity | ✅ finds 7 of 9 planted domes in a synthetic test canopy (overlapping domes merge; tune next) |
| Landing page (`docs/index.html`) | ✅ placeholder |
| Canopy height model pipeline (`src/build_chm.py`): picks tiles near a target, streams them through PDAL (ground → DTM, everything else → height above ground), mosaics, detects domes | ✅ built — run **Build canopy model** from Actions |
| Map page: canopy height over satellite imagery, dome circles, Kirby Storter Boardwalk ground-truth pin | ✅ |

### First real run (Sep 27, 2026)

Three tiles of the 2018 West Everglades topobathymetric survey around the Kirby Storter Boardwalk: median canopy 0.4 m (open prairie), 95th percentile 12.8 m, tallest 29.7 m, 27 candidates. Two lessons:

- **Flooded ground isn't "ground."** In a topobathymetric survey, the floor under standing water is class 40 (bathymetric bottom), so one tile came out almost blank. The DTM now uses classes 2 and 40, and water returns (9, 41, 45) are dropped.
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
