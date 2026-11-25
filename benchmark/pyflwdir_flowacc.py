"""Flow accumulation with pyflwdir: priority-flood fill + D8 flow direction, upstream cells."""

import sys
import time

import pyflwdir
import rasterio

dem_path, out_path = sys.argv[1], sys.argv[2]

t0 = time.perf_counter()
with rasterio.open(dem_path) as src:
    dem = src.read(1)
    profile = src.profile
    nodata = src.nodata if src.nodata is not None else -9999.0
t_read = time.perf_counter()
flw = pyflwdir.from_dem(dem, nodata=nodata, transform=profile["transform"], latlon=False)
acc = flw.upstream_area(unit="cell")
t_comp = time.perf_counter()
profile.update(dtype=acc.dtype, nodata=-9999, compress="deflate", tiled=True, blockxsize=256, blockysize=256, BIGTIFF="YES")
with rasterio.open(out_path, "w", **profile) as dst:
    dst.write(acc, 1)
t_end = time.perf_counter()
print(
    f"read={t_read - t0:.1f}s compute={t_comp - t_read:.1f}s "
    f"write={t_end - t_comp:.1f}s total={t_end - t0:.1f}s"
)
