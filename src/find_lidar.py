"""List USGS 3DEP LiDAR point-cloud tiles covering Big Cypress National Preserve.

Uses The National Map (TNM) Access API. Writes data/lidar_tiles.json.
"""
import json
from pathlib import Path

import requests

TNM = "https://tnmaccess.nationalmap.gov/api/v1/products"
OUT = Path(__file__).resolve().parents[1] / "data" / "lidar_tiles.json"

# Test area in the heart of the dome country (lon/lat): west of Monroe Station
BBOX = (-81.20, 25.85, -81.00, 26.05)


def main() -> None:
    items, offset = [], 0
    while True:
        r = requests.get(TNM, params={
            "bbox": ",".join(map(str, BBOX)),
            "datasets": "Lidar Point Cloud (LPC)",
            "max": 100, "offset": offset, "outputFormat": "JSON",
        }, timeout=120)
        r.raise_for_status()
        js = r.json()
        batch = js.get("items", [])
        items += [{"title": i.get("title"), "url": i.get("downloadLazURL") or i.get("downloadURL"),
                   "size": i.get("sizeInBytes"), "date": i.get("publicationDate")} for i in batch]
        offset += len(batch)
        if not batch or offset >= js.get("total", 0):
            break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2))
    print(f"✓ {len(items)} LiDAR tiles → {OUT.name}")
    for i in items[:10]:
        print(" ", i["title"])


if __name__ == "__main__":
    main()
