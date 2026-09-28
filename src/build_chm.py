"""Download a few 3DEP LiDAR tiles, build a canopy height model, and find domes.

Pipeline (runs in GitHub Actions; needs ~1 GB of disk per tile):
  1. Ask The National Map for LiDAR tiles around TARGET and pick the N nearest
     tiles from one survey (so they share a CRS and acquisition).
  2. For each tile, two streaming PDAL passes (low memory):
       a. ground points (class 2)  -> DTM raster (min elevation per cell)
       b. all non-noise points     -> height above that DTM -> CHM (max per cell)
  3. Mosaic the CHMs, convert units to meters, run detect_domes.
  4. Write web outputs to docs/data/: domes.geojson, chm.png, chm_meta.json.

Target defaults to the Kirby Storter Boardwalk on the Tamiami Trail, which
runs from wet prairie into the rim of a cypress dome: a place you can check
the detector against with your own eyes.

Env vars: TARGET="lat,lon"  TILES=3
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
import requests
from matplotlib import colormaps
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.fill import fillnodata
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject

sys.path.insert(0, str(Path(__file__).parent))
from detect_domes import detect_domes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
WORK = ROOT / "data" / "work"
WEB = ROOT / "docs" / "data"
TNM = "https://tnmaccess.nationalmap.gov/api/v1/products"

TARGET = tuple(float(v) for v in os.environ.get("TARGET", "25.8679,-81.1540").split(","))
N_TILES = int(os.environ.get("TILES", "3"))
CELL_M = 1.0          # target cell size in meters
NODATA = -9999.0


def log(msg: str) -> None:
    print(msg, flush=True)


# ── 1. pick tiles ────────────────────────────────────────────────────────────
def pick_tiles() -> list[dict]:
    lat, lon = TARGET
    d = 0.03
    r = requests.get(TNM, params={
        "bbox": f"{lon - d},{lat - d},{lon + d},{lat + d}",
        "datasets": "Lidar Point Cloud (LPC)", "max": 200, "outputFormat": "JSON",
    }, timeout=120)
    r.raise_for_status()
    items = []
    for it in r.json().get("items", []):
        bb = it.get("boundingBox") or {}
        url = it.get("downloadLazURL") or it.get("downloadURL")
        if not bb or not url or not url.lower().endswith(".laz"):
            continue
        cx, cy = (bb["minX"] + bb["maxX"]) / 2, (bb["minY"] + bb["maxY"]) / 2
        items.append({
            "title": it["title"], "url": url, "size": it.get("sizeInBytes"),
            "project": it["title"].split()[4] if len(it["title"].split()) > 4 else "?",
            "date": it.get("publicationDate"), "bbox": bb,
            "dist_km": 111.2 * math.hypot(cy - lat, (cx - lon) * math.cos(math.radians(lat))),
        })
    if not items:
        raise SystemExit("no LiDAR tiles found near target")
    # the survey with a tile closest to the target wins; take its N nearest tiles
    best = min(items, key=lambda t: t["dist_km"])["project"]
    tiles = sorted((t for t in items if t["project"] == best), key=lambda t: t["dist_km"])[:N_TILES]
    log(f"survey {best}: using {len(tiles)} tiles")
    for t in tiles:
        log(f"  {t['title']}  {t['dist_km']:.2f} km  {(t['size'] or 0) / 1e6:.0f} MB")
    return tiles


def download(t: dict) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / t["url"].rsplit("/", 1)[-1]
    if out.exists() and out.stat().st_size > 0:
        return out
    log(f"  downloading {out.name}")
    with requests.get(t["url"], stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return out


# ── 2. PDAL passes ───────────────────────────────────────────────────────────
def pdal_summary(laz: Path) -> dict:
    out = subprocess.run(["pdal", "info", "--summary", str(laz)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)["summary"]


def unit_factors(summary: dict) -> tuple[float, float, str]:
    """Meters per horizontal unit and per vertical unit, from the file's CRS."""
    srs = summary.get("srs", {})
    wkt = srs.get("compoundwkt") or srs.get("wkt") or srs.get("horizontal") or ""
    h, v = 1.0, None
    try:
        crs = CRS.from_wkt(wkt)
        subs = crs.sub_crs_list or [crs]
        h = subs[0].axis_info[0].unit_conversion_factor
        if len(subs) > 1:
            v = subs[1].axis_info[0].unit_conversion_factor
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ could not parse CRS ({e}); assuming meters")
    if v is None:
        v = h  # a projected CRS in feet almost always carries elevations in feet too
    return h, v, wkt


def run_pipeline(stages: list) -> None:
    subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps({"pipeline": stages}),
                   text=True, check=True)


def build_tile(laz: Path) -> tuple[Path, float, float, str]:
    s = pdal_summary(laz)
    h, v, wkt = unit_factors(s)
    b = s["bounds"]
    bounds = f"([{b['minx']},{b['maxx']}],[{b['miny']},{b['maxy']}])"
    res = CELL_M / h  # 1 m expressed in the file's horizontal units
    WORK.mkdir(parents=True, exist_ok=True)
    dtm, dtm_filled, chm = (WORK / f"{laz.stem}_{k}.tif" for k in ("dtm", "dtmf", "chm"))
    log(f"  {laz.name}: {s.get('num_points', 0):,} pts, h-unit {h:.4f} m, v-unit {v:.4f} m")

    if not chm.exists():
        run_pipeline([
            str(laz),
            {"type": "filters.expression", "expression": "Classification == 2"},
            {"type": "writers.gdal", "filename": str(dtm), "resolution": res, "bounds": bounds,
             "output_type": "min", "window_size": 6, "nodata": NODATA, "data_type": "float32"},
        ])
        with rasterio.open(dtm) as src:
            prof, arr = src.profile, src.read(1)
        mask = (arr != NODATA).astype("uint8")
        arr = fillnodata(arr, mask=mask, max_search_distance=200)
        with rasterio.open(dtm_filled, "w", **prof) as dst:
            dst.write(arr, 1)
        run_pipeline([
            str(laz),
            {"type": "filters.expression", "expression": "Classification != 7 && Classification != 18"},
            {"type": "filters.hag_dem", "raster": str(dtm_filled)},
            {"type": "writers.gdal", "filename": str(chm), "resolution": res, "bounds": bounds,
             "dimension": "HeightAboveGround", "output_type": "max", "nodata": NODATA, "data_type": "float32"},
        ])
    return chm, h, v, wkt


# ── 3. mosaic + detect ───────────────────────────────────────────────────────
def main() -> None:
    tiles = pick_tiles()
    chms, hs, vs = [], set(), set()
    for t in tiles:
        chm, h, v, wkt = build_tile(download(t))
        chms.append(chm); hs.add(round(h, 6)); vs.add(round(v, 6))
    h, v = hs.pop(), vs.pop()

    srcs = [rasterio.open(p) for p in chms]
    mosaic, transform = merge(srcs, nodata=NODATA)
    crs = srcs[0].crs
    for s_ in srcs:
        s_.close()
    chm = mosaic[0].astype("float32")
    chm[chm == NODATA] = np.nan
    chm *= v                                   # vertical units -> meters
    p99 = float(np.nanpercentile(chm, 99))
    if p99 > 45:                               # no Big Cypress tree is 45 m tall: units were feet
        log(f"  ⚠ 99th percentile {p99:.1f} looks like feet; converting")
        chm *= 0.3048
    chm = np.clip(np.nan_to_num(chm, nan=0.0), 0, 45)
    res_m = abs(transform.a) * h
    log(f"CHM {chm.shape[1]}×{chm.shape[0]} cells at {res_m:.2f} m · p50 {np.percentile(chm, 50):.1f} m · "
        f"p95 {np.percentile(chm, 95):.1f} m · max {chm.max():.1f} m")

    domes = detect_domes(chm, res_m=res_m)
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    feats = []
    for i, d in enumerate(sorted(domes, key=lambda d: -d["peak_height_m"]), 1):
        x, y = transform * (d["col"] + 0.5, d["row"] + 0.5)
        lon, lat = to_ll.transform(x, y)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                      "properties": {"id": i, **{k: d[k] for k in ("diameter_m", "peak_height_m", "circularity")}}})
    log(f"detected {len(feats)} dome candidates")

    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "domes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    bounds = write_png(chm, transform, crs)
    (WEB / "chm_meta.json").write_text(json.dumps({
        "target": TARGET, "tiles": [{k: t[k] for k in ("title", "url", "date")} for t in tiles],
        "survey": tiles[0]["project"], "cell_m": round(res_m, 2), "bounds": bounds,
        "stats_m": {"p50": round(float(np.percentile(chm, 50)), 1), "p95": round(float(np.percentile(chm, 95)), 1),
                    "max": round(float(chm.max()), 1)},
        "n_domes": len(feats),
    }, indent=2))
    log("✓ wrote docs/data/domes.geojson, chm.png, chm_meta.json")


def write_png(chm: np.ndarray, transform, crs, max_px: int = 2400) -> list:
    """Colorized CHM warped to lat/lon for a Leaflet image overlay."""
    dst_crs = "EPSG:4326"
    h, w = chm.shape
    left, top = transform * (0, 0)
    right, bottom = transform * (w, h)
    dt, dw, dh = calculate_default_transform(crs, dst_crs, w, h, left=left, bottom=bottom, right=right, top=top)
    scale = max(1, max(dw, dh) / max_px)
    dw, dh = int(dw / scale), int(dh / scale)
    dt = dt * dt.scale(scale, scale)
    out = np.full((dh, dw), np.nan, dtype="float32")
    reproject(chm, out, src_transform=transform, src_crs=crs, dst_transform=dt, dst_crs=dst_crs,
              resampling=Resampling.average, dst_nodata=np.nan)
    t = np.clip(np.nan_to_num(out, nan=0) / 25.0, 0, 1)
    rgba = (colormaps["viridis"](t) * 255).astype("uint8")
    rgba[..., 3] = np.where(np.isnan(out), 0, (60 + 195 * np.sqrt(t))).astype("uint8")
    Image.fromarray(rgba, "RGBA").save(WEB / "chm.png", optimize=True)
    west, north = dt * (0, 0)
    east, south = dt * (dw, dh)
    return [[south, west], [north, east]]


if __name__ == "__main__":
    main()
