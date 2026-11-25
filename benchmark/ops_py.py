"""Raster operations in Python packages for ops_batch.sh (tools/ops_other.sh):
python ops_py.py <pkg> <op> <dem.tif> <out prefix>. pkg = xrs (xarray-spatial, NumPy), xrsdask
(xarray-spatial on dask chunks of 4096 x 4096), tt (TopoToolbox), richdem. Settings as for the other
tools: hillshade azimuth 270, altitude 30; slope in degrees + aspect; viewshed from 637500, 221750,
observer 1.75 m, target 0; focal mean 5 x 5. Prints read / compute / write times."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # ops_expr.py (python -I drops it)

pkg, op, dem, out = sys.argv[1:5]  # cost: argv[5] = resolution
X, Y = 637500.0, 221750.0
t0 = time.perf_counter()


def yx(var, default):  # "x,y" from the environment as (y, x) for a_star_search
    x, y = map(float, os.environ.get(var, default).split(","))
    return (y, x)


def stamp(what):
    global t0
    t = time.perf_counter()
    print(f"{what}: {t - t0:.2f} s", flush=True)
    t0 = t


if pkg in ("xrs", "xrsdask"):
    import numpy as np
    import rioxarray
    import xrspatial
    from xrspatial import focal

    cs = int(os.environ.get("XRS_CHUNK", 4096))  # dask chunk size (cells per side)
    chunks = {"x": cs, "y": cs} if pkg == "xrsdask" else None
    if pkg == "xrsdask":  # dask's default worker count is the CPUs it can see: set it
        import dask

        dask.config.set(scheduler="threads", num_workers=int(os.environ.get("NTHREADS", 16)))
    a = rioxarray.open_rasterio(dem, masked=True, chunks=chunks).squeeze("band", drop=True).astype("float32")
    if chunks is None:
        a = a.load()
    stamp("read")
    res = {}
    if op == "relief":
        res[""] = xrspatial.hillshade(a, azimuth=270, angle_altitude=30)
    elif op == "slope":
        res[""] = xrspatial.slope(a)
        res["_asp"] = xrspatial.aspect(a)
    elif op == "viewshed":
        res[""] = xrspatial.viewshed(a, x=X, y=Y, observer_elev=1.75, target_elev=0)
    elif op == "focal":
        fs = int(os.environ.get("FOCAL_SIZE", 5))
        if os.environ.get("FOCAL_METHOD", "mean") == "median":  # no median in focal_stats: apply with a numba kernel
            from xrspatial.utils import ngjit

            @ngjit
            def _median(k):
                return np.nanmedian(k)

            res[""] = focal.apply(a, np.ones((fs, fs)), func=_median)
        else:
            res[""] = focal.focal_stats(a, np.ones((fs, fs)), stats_funcs=["mean"]).sel(stats="mean", drop=True)
    elif op == "algebra":  # plain xarray arithmetic (xarray-spatial has no map algebra), ops_expr.py
        import xarray as xr
        from ops_expr import render

        res[""] = eval(render("numpy", "a")).astype("float32")
    elif op == "resample":  # onto the grid of the <res> DEM, GDAL-based (rioxarray reproject_match)
        from rasterio.enums import Resampling

        m = Resampling.cubic if os.environ.get("RS_METHOD", "bicubic") == "bicubic" else Resampling.bilinear
        src = rioxarray.open_rasterio(f"data/elev_{os.environ.get('RS_IN', '3')}m.tif", masked=True, chunks=chunks)
        res[""] = src.squeeze("band", drop=True).rio.reproject_match(a, resampling=m).astype("float32")
    elif op == "series":  # mean of the 12-layer stack (prep_series.sh)
        import xarray as xr

        r = sys.argv[5]
        s = [rioxarray.open_rasterio(f"data/series/{r}m{'_' + os.environ['SERIES_SET'] if os.environ.get('SERIES_SET') else ''}/s{k}.tif", masked=True, chunks=chunks).squeeze("band", drop=True)
             for k in range(1, 13)]
        res[""] = xr.concat(s, dim="t").mean("t").astype("float32")
    elif op == "cost":
        r = sys.argv[5]
        rd_ = lambda f: rioxarray.open_rasterio(f, masked=True, chunks=chunks).squeeze("band", drop=True)
        src, fr = rd_(f"data/cost/src_{r}m.tif"), rd_(f"data/cost/friction_{r}m.tif").astype("float32")
        if chunks is None:
            src, fr = src.load(), fr.load()
        res[""] = xrspatial.cost_distance(src, fr, target_values=[1])
        res["_path"] = xrspatial.a_star_search(fr, yx("COST_START", "1122385,-2618715"), yx("COST_END", "1206305,-2388085"), friction=fr,
                                               snap_start=True, snap_goal=True)
    else:
        sys.exit(f"no {pkg}/{op}")
    if chunks is None:
        stamp("compute")
    for k, v in res.items():
        v.rio.write_crs(a.rio.crs, inplace=True)
        v.rio.to_raster(f"{out}{k}.tif", compress="deflate", tiled=True, lock=chunks is not None or None,
                        num_threads=int(os.environ.get("NTHREADS", 16)))  # threaded compression (2026-10-30)
    stamp("write" if chunks is None else "compute + write")
elif pkg == "tt":
    import topotoolbox as tt

    g = tt.read_tif(dem)
    stamp("read")
    res = {}
    if op == "relief":
        res[""] = g.hillshade(azimuth=270, altitude=30)
    elif op == "slope":
        res[""] = g.evansslope()
        res["_asp"] = g.aspect()
    elif op == "resample":
        from rasterio.enums import Resampling

        src = tt.read_tif(f"data/elev_{os.environ.get('RS_IN', '3')}m.tif")
        m = Resampling.cubic if os.environ.get("RS_METHOD", "bicubic") == "bicubic" else Resampling.bilinear
        res[""] = src.resample(g.cellsize, m)
    elif op == "focal":
        res[""] = g.filter(method=os.environ.get("FOCAL_METHOD", "mean"), kernelsize=int(os.environ.get("FOCAL_SIZE", 5)))
    else:
        sys.exit(f"no {pkg}/{op}")
    stamp("compute")
    for k, v in res.items():
        tt.write_tif(v, f"{out}{k}.tif")
    stamp("write")
elif pkg == "richdem":
    import richdem as rd

    try:
        d = rd.LoadGDAL(dem)
    except UnboundLocalError:  # no no-data value in the file (as in richdem_flowacc.py)
        d = rd.LoadGDAL(dem, no_data=-9999)
    stamp("read")
    if op != "slope":
        sys.exit(f"no {pkg}/{op}")
    s = rd.TerrainAttribute(d, attrib="slope_degrees")
    a = rd.TerrainAttribute(d, attrib="aspect")
    stamp("compute")
    rd.SaveGDAL(f"{out}.tif", s)
    rd.SaveGDAL(f"{out}_asp.tif", a)
    stamp("write")
