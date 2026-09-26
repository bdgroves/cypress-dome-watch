# 🌳 CYPRESS-DOME-WATCH

**Reading water depth from the shape of a forest.**

Across Big Cypress National Preserve, bald cypress grow in round domes: short trees at the dry edges, the tallest at the deep, wet center. Seen from above, a dome's height profile is a readout of the water beneath it. CYPRESS-DOME-WATCH finds these domes automatically in LiDAR canopy height, tracks how long each one holds water through the seasons, and asks whether domes acted as refuges during the February 2026 Big Cypress fire.

> Part of the GeoAI & Remote Sensing Lab · sibling of [ANOLE-WATCH](https://github.com/bdgroves/Anole-watch) and [ALPINE-WATCH](https://github.com/bdgroves/Alpine-watch)

---

## Status: 🌱 scaffold

| Piece | State |
|---|---|
| 3DEP LiDAR tile finder (`src/find_lidar.py`) + "Find LiDAR tiles" Action | ✅ written: run it from the Actions tab |
| Dome detector (`src/detect_domes.py`): smoothed local maxima + circularity | ✅ finds 7 of 9 planted domes in a synthetic test canopy (overlapping domes merge; tune next) |
| Landing page (`docs/index.html`) | ✅ placeholder |
| Real canopy height model from LiDAR | ⬜ next |
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
```

## Build prompt (for the next session)

> Help me build out CYPRESS-DOME-WATCH. Download a few 3DEP LiDAR tiles from data/lidar_tiles.json, build a 1 m canopy height model with PDAL, and run src/detect_domes.py on it. Tune the smoothing and circularity thresholds against domes I can see in aerial imagery. Then add a Sentinel-2 NDWI time series per detected dome, and compare pre/post-fire NDVI against the February 2026 Big Cypress fire perimeter to test the fire-refugia idea.
