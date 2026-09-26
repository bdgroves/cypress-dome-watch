"""Detect cypress-dome candidates in a canopy height model (CHM).

A dome is a roughly circular patch of forest whose canopy rises toward the
center. Method: smooth the CHM at dome scale, find local maxima, grow each
peak into a region above a relative height threshold, and keep regions that
are round enough and the right size.

Run directly for a synthetic demo.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.measure import regionprops
from skimage.segmentation import watershed


def detect_domes(chm: np.ndarray, res_m: float = 1.0, sigma_m: float = 15.0,
                 min_diam_m: float = 40.0, max_diam_m: float = 600.0,
                 min_height_m: float = 6.0, min_circularity: float = 0.6) -> list[dict]:
    smooth = ndi.gaussian_filter(np.nan_to_num(chm), sigma_m / res_m)
    min_sep = max(1, int(min_diam_m / res_m / 2))
    peaks = peak_local_max(smooth, min_distance=min_sep, threshold_abs=min_height_m)
    markers = np.zeros(smooth.shape, dtype=int)
    for n, (r, c) in enumerate(peaks, start=1):
        markers[r, c] = n
    # a pixel belongs to a dome if it is above ~half the dome's peak height
    forest = smooth > min_height_m / 2
    labels = watershed(-smooth, markers, mask=forest)
    domes = []
    for rp in regionprops(labels, intensity_image=smooth):
        peak = rp.intensity_max
        core = rp.image & (rp.image_intensity > 0.5 * peak)
        area = core.sum() * res_m ** 2
        diam = 2 * np.sqrt(area / np.pi)
        perim = max(regionprops(core.astype(int))[0].perimeter * res_m, 1e-9) if core.any() else 1e-9
        circ = 4 * np.pi * area / perim ** 2
        if min_diam_m <= diam <= max_diam_m and circ >= min_circularity:
            r, c = rp.centroid
            domes.append({"row": round(float(r), 1), "col": round(float(c), 1), "diameter_m": round(float(diam), 1),
                          "peak_height_m": round(float(peak), 1), "circularity": round(float(circ), 2)})
    return domes


def synthetic_chm(size: int = 800, seed: int = 7) -> tuple[np.ndarray, list[tuple]]:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:size, :size]
    chm = rng.normal(2.0, 0.8, (size, size)).clip(0)  # low prairie / dwarf cypress
    truth = []
    for _ in range(9):
        r, c = rng.integers(80, size - 80, 2)
        rad, h = rng.uniform(40, 110), rng.uniform(14, 26)
        d = np.hypot(yy - r, xx - c) / rad
        chm = np.maximum(chm, h * np.clip(1 - d ** 2, 0, None) + rng.normal(0, 1, chm.shape) * (d < 1))
        truth.append((r, c, 2 * rad))
    return chm, truth


if __name__ == "__main__":
    chm, truth = synthetic_chm()
    found = detect_domes(chm)
    print(f"planted {len(truth)} domes, detected {len(found)}")
    for d in found:
        print(" ", d)
