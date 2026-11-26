"""Sanity check of the flow accumulation outputs at one resolution, in row strips (2.14B-cell grids):
python fa_check.py <res> <acc.tif>...  For each file: land cells (valid in the DEM) without a value, sea cells with a
value, the largest accumulation (absolute value: r.watershed marks cells that may get flow from outside the DEM as
negative) and the cells with more than 1000 cells upstream. Missing files are listed as such."""

import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

res, files = sys.argv[1], sys.argv[2:]
dem = rasterio.open(f"data/elev_{res}m.tif")
STRIP = 1024
for f in files:
    if not Path(f).exists():
        print(f"{f}: missing (run did not finish or was not run)", flush=True)
        continue
    s = rasterio.open(f)
    if s.shape != dem.shape:
        print(f"{f}: shape {s.shape} vs {dem.shape}", flush=True)
        continue
    no_val = sea_val = big = 0
    mx = 0.0
    for y in range(0, dem.height, STRIP):
        w = Window(0, y, dem.width, min(STRIP, dem.height - y))
        land = dem.read_masks(1, window=w) > 0  # 255 = valid, 0 = no-data
        a = s.read(1, window=w, masked=True).astype("float64").filled(np.nan)
        val = np.isfinite(a)
        no_val += int((land & ~val).sum())
        sea_val += int((~land & val).sum())
        if val.any():
            mx = max(mx, float(np.nanmax(np.abs(a))))
            big += int((np.abs(a[val]) > 1000).sum())
    print(f"{f}: land cells without value {no_val:,}, sea cells with value {sea_val:,}, max {mx:,.0f}, "
          f"cells > 1000 {big:,}", flush=True)
