"""Inputs for the least-cost distance and path benchmark (OP=cost), made once per resolution, untimed:
data/cost/friction_<res>m.tif  friction = 1 + slope in degrees / 5 (slope from gdaldem, Horn), -9999 no-data;
data/cost/friction0_<res>m.tif the same with the start cell set to 0 (terra costDist target);
data/cost/src_<res>m.tif, dst_<res>m.tif  1 at the start / end cell, 0 elsewhere (WhiteboxTools source and
destination rasters); data/cost/start_ice.shp, end_ice.shp, start_ice.csv, end_ice.csv (one point each: Reykjavik
and Akureyri, EPSG:3413). Usage: python prep_cost.py ice10 (needs gdaldem on PATH). The wrappers read COST_SITE,
COST_START and COST_END (config.sh)."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio

SITES = {"_ice": ((1122385.0, -2618715.0), (1206305.0, -2388085.0), "EPSG:3413")}  # Reykjavik -> Akureyri
out = Path("data/cost")
out.mkdir(parents=True, exist_ok=True)
for sfx, (start, end, epsg) in SITES.items():
    for name, (x, y) in (("start", start), ("end", end)):
        (out / f"{name}{sfx}.csv").write_text(f"id,x,y\n1,{x},{y}\n")
        subprocess.run(["ogr2ogr", "-q", "-f", "ESRI Shapefile", str(out / f"{name}{sfx}.shp"),
                        str(out / f"{name}{sfx}.csv"), "-oo", "X_POSSIBLE_NAMES=x", "-oo", "Y_POSSIBLE_NAMES=y",
                        "-a_srs", epsg, "-overwrite"], check=True)
for res in sys.argv[1:]:
    START, END, _ = SITES["_ice"]
    dem = f"data/elev_{res}m.tif"
    slope = out / f"slope_{res}m.tif"
    subprocess.run(["gdaldem", "slope", "-q", "-compute_edges", dem, str(slope)], check=True)
    with rasterio.open(dem) as d, rasterio.open(slope) as s:
        z = d.read(1, masked=True)
        sl = s.read(1).astype("float32")
        prof = d.profile
        rows = [d.index(*p) for p in (START, END)]
    fr = np.where(np.ma.getmaskarray(z), -9999, 1 + np.clip(sl, 0, 90) / 5).astype("float32")
    assert all(fr[r, c] > 0 for r, c in rows), "start or end on no-data"
    prof.update(dtype="float32", nodata=-9999, compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(out / f"friction_{res}m.tif", "w", **prof) as f:
        f.write(fr, 1)
    fr0 = fr.copy()
    fr0[rows[0]] = 0
    with rasterio.open(out / f"friction0_{res}m.tif", "w", **prof) as f:
        f.write(fr0, 1)
    pb = dict(prof, dtype="uint8", nodata=None)
    for name, (r, c) in (("src", rows[0]), ("dst", rows[1])):
        a = np.zeros(fr.shape, np.uint8)
        a[r, c] = 1
        with rasterio.open(out / f"{name}_{res}m.tif", "w", **pb) as f:
            f.write(a, 1)
    slope.unlink()
    print(res, "ok", fr[fr > 0].min(), fr.max())
# GRASS: the friction rasters are imported once into project/PERMANENT as friction_<res>m (r.in.gdal), see
# 01_data.sh.
