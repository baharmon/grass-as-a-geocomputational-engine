"""Flow accumulation with Whitebox Workflows (Python wheel of whitebox_next_gen; RustGIS and
GeoLibre run a fork of the same code, geolibre-rust): fill_depressions (fix flats) ->
d8_flow_accum or fd8_flow_accum, in cells.

Usage: wbng_flowacc.py <dem.tif> <out.tif> [d8|fd8] [r|m] [fill|natural|breach]
The fourth argument is read_raster's file_mode ('r' default, 'm' as documented by the package).
The fifth is the depression handling: fill = fill_depressions with its default flat resolution
(garbrecht_martz), natural = fill_depressions(flat_resolution="natural"), breach =
breach_depressions_least_cost(fill_deps=True).
WBNG_PROCS sets wbe.max_procs (no measurable effect; use RAYON_NUM_THREADS). Reading is lazy: the GeoTIFF is read inside
the first tool call, so 'read' shows ~0 s and 'compute' includes it.
"""

import os
import sys
import time

import whitebox_workflows as wbw

dem_path, out_path = sys.argv[1], sys.argv[2]
method = sys.argv[3] if len(sys.argv) > 3 else "d8"
mode = sys.argv[4] if len(sys.argv) > 4 else "r"
deps = sys.argv[5] if len(sys.argv) > 5 else "fill"

wbe = wbw.WbEnvironment()
if os.environ.get("WBNG_PROCS"):
    wbe.max_procs = int(os.environ["WBNG_PROCS"])
t0 = time.perf_counter()
dem = wbe.read_raster(dem_path, file_mode=mode)
t1 = time.perf_counter()
ds = wbe.hydrology.depressions_storage
if deps == "breach":
    filled = ds.breach_depressions_least_cost(dem=dem, fill_deps=True)
elif deps == "natural":
    filled = ds.fill_depressions(dem=dem, fix_flats=True, flat_resolution="natural")
else:
    filled = ds.fill_depressions(dem=dem, fix_flats=True)
if method == "fd8":
    acc = wbe.hydrology.flow_routing.fd8_flow_accum(dem=filled, out_type="cells", exponent=1.1)
else:
    acc = wbe.hydrology.flow_routing.d8_flow_accum(input=filled, out_type="cells")
t2 = time.perf_counter()
wbe.write_raster(acc, out_path)
t3 = time.perf_counter()
print(f"whitebox_workflows {wbw.__version__ if hasattr(wbw, '__version__') else '?'} {method} mode={mode} deps={deps} "
      f"read={t1 - t0:.1f}s compute={t2 - t1:.1f}s write={t3 - t2:.1f}s procs={wbe.max_procs}")
