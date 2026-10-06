"""Canopy height over a 6 x 6 km window, streamed from the 3DEP point-cloud archive.

The first version downloaded whole LiDAR tiles (~220 MB each), which capped the
study at a few square kilometres. The same 2018 West Everglades topobathymetric
survey sits in the USGS Entwine Point Tile archive on AWS, which PDAL can read a
window at a time, so the canopy model can grow without downloading any tiles.

    python src/chm_ept.py chunks          # list the chunk ids (JSON) for the Action matrix
    python src/chm_ept.py chunk 7         # one 1 km chunk -> data/chunks/chm_07.tif
    python src/chm_ept.py mosaic          # all chunks -> domes + web outputs in docs/data/

Each chunk is one PDAL pass: read the window, count bathymetric bottom (class 40)
as ground along with class 2 (under standing water the ground is class 40 in a
topobathymetric survey), drop noise and water returns, compute each point's height
above the nearest ground points, and keep the tallest per 1 m cell.

Env: CENTER="lat,lon" (default: 2 km south of the Kirby Storter Boardwalk, where the
6 km window sits fully inside the survey), SIZE_M=6000, CHUNK_M=1000.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.merge import merge

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "chunks"
WEB = ROOT / "docs" / "data"
PROJECT = os.environ.get("PROJECT", "FL_WestEvergladesNP_topobathymetric_2018")
EPT = f"https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{PROJECT}/ept.json"
CRS = "EPSG:26917"                  # UTM 17N, metres
CENTER = tuple(float(v) for v in os.environ.get("CENTER", "25.8498,-81.1540").split(","))
SIZE_M = float(os.environ.get("SIZE_M", "6000"))
CHUNK_M = float(os.environ.get("CHUNK_M", "1000"))
CELL = 1.0
NODATA = -9999.0
BOARDWALK = (25.8679, -81.1540)


def window():
    t = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    cx, cy = t.transform(CENTER[1], CENTER[0])
    x0 = np.floor((cx - SIZE_M / 2) / CHUNK_M) * CHUNK_M
    y0 = np.floor((cy - SIZE_M / 2) / CHUNK_M) * CHUNK_M
    n = int(SIZE_M // CHUNK_M)
    return x0, y0, n


def chunk_bounds(i):
    x0, y0, n = window()
    cx, cy = i % n, i // n
    return x0 + cx * CHUNK_M, y0 + cy * CHUNK_M, x0 + (cx + 1) * CHUNK_M, y0 + (cy + 1) * CHUNK_M


def do_chunk(i):
    import pdal
    bx0, by0, bx1, by1 = chunk_bounds(i)
    pad = 40.0
    to_merc = Transformer.from_crs(CRS, "EPSG:3857", always_xy=True)
    xs, ys = to_merc.transform([bx0 - pad, bx1 + pad, bx0 - pad, bx1 + pad],
                               [by0 - pad, by0 - pad, by1 + pad, by1 + pad])
    CHUNKS.mkdir(parents=True, exist_ok=True)
    out = CHUNKS / f"chm_{i:02d}.tif"
    pipe = [
        {"type": "readers.ept", "filename": EPT, "threads": 8,
         "bounds": f"([{min(xs)},{max(xs)}],[{min(ys)},{max(ys)}])"},
        {"type": "filters.expression",
         "expression": "Classification != 7 && Classification != 18 && Classification != 9 && "
                       "Classification != 41 && Classification != 45"},
        {"type": "filters.assign", "value": "Classification = 2 WHERE Classification == 40"},
        {"type": "filters.reprojection", "out_srs": CRS},
        {"type": "filters.crop", "bounds": f"([{bx0 - pad},{bx1 + pad}],[{by0 - pad},{by1 + pad}])"},
        {"type": "filters.hag_nn", "count": 3},
        {"type": "writers.gdal", "filename": str(out), "resolution": CELL, "dimension": "HeightAboveGround",
         "output_type": "max", "nodata": NODATA, "data_type": "float32",
         "bounds": f"([{bx0},{bx1 - CELL / 2}],[{by0},{by1 - CELL / 2}])"},
    ]
    n = pdal.Pipeline(json.dumps({"pipeline": pipe})).execute()
    with rasterio.open(out) as src:
        a = src.read(1)
    cov = float((a != NODATA).mean())
    print(f"= chunk {i:02d}: {n:,} points, {cov:.0%} of cells with returns", flush=True)


def radial_profile(chm, r, c, rad_px):
    """Mean canopy height in rings of 0.2 radius, from the centre out to 1.6 radii."""
    r0, r1 = int(max(0, r - 1.7 * rad_px)), int(min(chm.shape[0], r + 1.7 * rad_px + 1))
    c0, c1 = int(max(0, c - 1.7 * rad_px)), int(min(chm.shape[1], c + 1.7 * rad_px + 1))
    yy, xx = np.ogrid[r0:r1, c0:c1]
    d = np.hypot(yy - r, xx - c) / rad_px
    sub = chm[r0:r1, c0:c1]
    prof = []
    for a in np.arange(0, 1.6, 0.2):
        m = (d >= a) & (d < a + 0.2)
        prof.append(round(float(sub[m].mean()), 1) if m.any() else None)
    return prof


def mosaic():
    from build_chm import write_png
    from detect_domes import detect_domes
    files = sorted(CHUNKS.glob("chm_*.tif"))
    if not files:
        raise SystemExit("no chunks")
    srcs = [rasterio.open(p) for p in files]
    arr, tr = merge(srcs, nodata=NODATA)
    for s_ in srcs:
        s_.close()
    chm = arr[0].astype("float32")
    valid = chm != NODATA
    chm[~valid] = np.nan
    chm = np.clip(np.nan_to_num(chm, nan=0.0), 0, 45)
    print(f"= mosaic {chm.shape[1]} x {chm.shape[0]} m from {len(files)} chunks, "
          f"{valid.mean():.0%} with returns; p50 {np.percentile(chm[valid], 50):.1f} m, "
          f"p95 {np.percentile(chm[valid], 95):.1f} m", flush=True)
    domes = detect_domes(chm, res_m=CELL)
    to_ll = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    bx, by = to_utm.transform(BOARDWALK[1], BOARDWALK[0])
    feats = []
    for d in domes:
        x, y = tr * (d["col"] + 0.5, d["row"] + 0.5)
        lon, lat = to_ll.transform(x, y)
        rad = d["diameter_m"] / 2 / CELL
        prof = radial_profile(chm, d["row"], d["col"], rad)
        centre, rim = prof[0], prof[4]
        rise = round(centre - rim, 1) if centre is not None and rim is not None else None
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                      "properties": {**{k: d[k] for k in ("diameter_m", "peak_height_m", "circularity", "ring_forest")},
                                     "profile_m": prof, "centre_rise_m": rise,
                                     "km_from_boardwalk": round(float(np.hypot(x - bx, y - by)) / 1000, 2)}})
    feats.sort(key=lambda f: -f["properties"]["peak_height_m"])
    for i, f in enumerate(feats, 1):
        f["properties"] = {"id": i, **f["properties"]}
    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "domes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    bounds = write_png(chm, tr, CRS)
    v = chm[valid]
    rises = [f["properties"]["centre_rise_m"] for f in feats if f["properties"]["centre_rise_m"] is not None]
    (WEB / "chm_meta.json").write_text(json.dumps({
        "source": f"USGS 3DEP {PROJECT} (Entwine Point Tiles on AWS, streamed)",
        "window": {"center": CENTER, "size_m": SIZE_M, "chunks": len(files), "crs": CRS},
        "cell_m": CELL, "bounds": bounds, "coverage": round(float(valid.mean()), 3),
        "stats_m": {"p50": round(float(np.percentile(v, 50)), 1), "p95": round(float(np.percentile(v, 95)), 1),
                    "max": round(float(v.max()), 1)},
        "n_domes": len(feats),
        "domes_rising_to_centre": int(sum(r > 2 for r in rises)),
        "boardwalk": BOARDWALK,
    }, indent=2))
    print(f"= {len(feats)} dome candidates; {sum(r > 2 for r in rises)} rise more than 2 m from rim to centre")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "chunks"
    if cmd == "chunks":
        n = window()[2]
        print(json.dumps(list(range(n * n))))
    elif cmd == "chunk":
        do_chunk(int(sys.argv[2]))
    elif cmd == "mosaic":
        mosaic()
