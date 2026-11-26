"""Resampling (OP=resample) in xarray (rioxarray, GDAL-based) and TopoToolbox: the DEM at RS_IN m onto the
grid of the target DEM, bicubic (RS_METHOD=bicubic, default) or bilinear. Only the target grid's metadata is
read, not its values. Usage: resample_py.py <xrs|xrsdask|tt> <target dem.tif> <output prefix>."""

import os
import sys

import rasterio
from rasterio.enums import Resampling

pkg, target, out = sys.argv[1:4]
src_file = f"data/elev_{os.environ.get('RS_IN', '3')}m.tif"
method = Resampling.cubic if os.environ.get("RS_METHOD", "bicubic") == "bicubic" else Resampling.bilinear
with rasterio.open(target) as t:
    shape, transform, crs = t.shape, t.transform, t.crs
nt = int(os.environ.get("NTHREADS", 16))
if pkg == "xrs":  # rioxarray: one GDAL warp, NTHREADS warp threads
    import rioxarray

    a = rioxarray.open_rasterio(src_file, masked=True)
    r = a.squeeze("band", drop=True).rio.reproject(crs, shape=shape, transform=transform, resampling=method,
                                                    num_threads=nt)
    r.astype("float32").rio.to_raster(f"{out}.tif", compress="deflate", tiled=True, num_threads=nt)
elif pkg == "xrsdask":  # odc-geo: chunk-wise reprojection with dask (rioxarray's reproject is not dask-aware)
    import dask
    import odc.geo.xr  # noqa: F401
    import rioxarray
    from odc.geo.geobox import GeoBox

    cs = int(os.environ.get("XRS_CHUNK", 2048))
    a = rioxarray.open_rasterio(src_file, masked=True, chunks={"x": cs, "y": cs}).squeeze("band", drop=True)
    gb = GeoBox(shape, transform, crs)
    r = a.odc.reproject(gb, resampling="cubic" if method == Resampling.cubic else "bilinear",
                        chunks=(cs, cs)).astype("float32")
    with dask.config.set(scheduler="threads", num_workers=nt):
        r.rio.to_raster(f"{out}.tif", compress="deflate", tiled=True, lock=True, num_threads=nt)
elif pkg == "tt":
    import topotoolbox as tt

    tt.write_tif(tt.read_tif(src_file).resample(transform.a, method), f"{out}.tif")
else:
    sys.exit(f"no {pkg}/resample")
