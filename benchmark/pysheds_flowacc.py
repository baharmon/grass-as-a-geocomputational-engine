"""Flow accumulation with pysheds: condition DEM, flow direction, accumulation.

Usage: pysheds_flowacc.py <dem.tif> <out.tif> [routing]   (routing: d8, default, or mfd)
"""

import sys
import time

import numpy as np
from pysheds.grid import Grid
from pysheds.sview import Raster, ViewFinder

dem_path, out_path = sys.argv[1], sys.argv[2]
routing = sys.argv[3] if len(sys.argv) > 3 else "d8"
# PYSHEDS_DTYPE=float64 (2026-10-19 variant): run on a float64 DEM; the float32 run leaves pits on
# flats at 3 m and 1 m.
import os  # noqa: E402
dtype = os.environ.get("PYSHEDS_DTYPE", "float32")
# PYSHEDS_EPS: resolve_flats eps (default 1e-5). At 10 m the default leaves 468 pits and 147 flat
# cells where the main rivers stop (largest accumulation 0.75 of TauDEM's); eps=1e-7 resolves all flats.
eps = float(os.environ.get("PYSHEDS_EPS", "1e-5"))

t0 = time.perf_counter()
grid = Grid.from_raster(dem_path)
dem = grid.read_raster(dem_path)
# pysheds excludes NaN cells but treats a numeric no-data value (e.g. -9999) as very low terrain,
# so the sea would be filled and routed. Use NaN for no-data.
if not np.isnan(dem.nodata) or dtype != "float32":
    a = np.asarray(dem).astype(dtype)
    if not np.isnan(dem.nodata):
        a[a == dem.nodata] = np.nan
    dem = Raster(a, viewfinder=ViewFinder(affine=dem.affine, shape=dem.shape, crs=dem.crs, nodata=np.dtype(dtype).type(np.nan)))
t_read = time.perf_counter()
dem = grid.fill_pits(dem)
dem = grid.fill_depressions(dem)
dem = grid.resolve_flats(dem, eps=eps)
fdir = grid.flowdir(dem, routing=routing)
acc = grid.accumulation(fdir, routing=routing)
t_comp = time.perf_counter()
grid.to_raster(acc, out_path)
t_end = time.perf_counter()
print(
    f"read={t_read - t0:.1f}s compute={t_comp - t_read:.1f}s "
    f"write={t_end - t_comp:.1f}s total={t_end - t0:.1f}s"
)
