"""Flow accumulation with RichDEM: fill depressions, resolve flats, flow accumulation.

Usage: richdem_flowacc.py <dem.tif> <out.tif> [method] [dir_out.tif]
method: D8 (default) or Freeman (MFD, exponent 1.1 as WBT FD8 and SAGA's MFD default).
dir_out (D8 only): flow direction from FlowProportions as the RichDEM neighbor index
1..8 (W, NW, N, NE, E, SE, S, SW), 0 = none, for compare_d8.py.
"""

import sys
import time

import numpy as np
import richdem as rd

dem_path, out_path = sys.argv[1], sys.argv[2]
method = sys.argv[3] if len(sys.argv) > 3 else "D8"
dir_path = sys.argv[4] if len(sys.argv) > 4 else None
exponent = 1.1 if method == "Freeman" else None
# Variants (2026-10-19, closest-setting search): RICHDEM_DTYPE=float64 casts the DEM before the fill
# (the float32 run leaves pits on flats at 3 m and 1 m); RICHDEM_EPS=1 fills with epsilon=True
# (each cell slightly above its spill neighbor) instead of ResolveFlats.
import os  # noqa: E402
dtype = os.environ.get("RICHDEM_DTYPE", "float32")
eps = os.environ.get("RICHDEM_EPS", "0") == "1"

t0 = time.perf_counter()
try:
    dem = rd.LoadGDAL(dem_path)
except Exception:
    dem = rd.LoadGDAL(dem_path, no_data=-9999)
# RichDEM does not treat NaN as no-data (a NaN no-data value never compares equal), so NaN cells
# would be filled and routed like terrain. Replace NaN with an explicit no-data value.
nan = np.isnan(dem)
if nan.any():
    dem[nan] = -9999
    dem.no_data = -9999
if dtype == "float64":
    gt, pr, nd = dem.geotransform, dem.projection, dem.no_data
    dem = rd.rdarray(np.asarray(dem, dtype=np.float64), no_data=nd)
    dem.geotransform, dem.projection = gt, pr
t_read = time.perf_counter()
if eps:
    rd.FillDepressions(dem, epsilon=True, in_place=True)
else:
    rd.FillDepressions(dem, epsilon=False, in_place=True)
    rd.ResolveFlats(dem, in_place=True)
acc = rd.FlowAccumulation(dem, method=method, exponent=exponent)
t_comp = time.perf_counter()
rd.SaveGDAL(out_path, acc)
if dir_path:
    props = np.asarray(rd.FlowProportions(dem, method="D8"))
    k = np.argmax(props[:, :, 1:], axis=2).astype(np.uint8) + 1
    k[props[:, :, 1:].max(axis=2) <= 0] = 0
    d = rd.rdarray(k, no_data=255)
    d.geotransform = dem.geotransform
    d.projection = dem.projection
    rd.SaveGDAL(dir_path, d)
t_end = time.perf_counter()
print(
    f"richdem {rd.__version__} method={method} dtype={dtype} eps={eps} read={t_read - t0:.1f}s "
    f"compute={t_comp - t_read:.1f}s write={t_end - t_comp:.1f}s total={t_end - t0:.1f}s"
)
