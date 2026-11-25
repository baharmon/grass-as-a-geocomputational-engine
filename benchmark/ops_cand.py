"""Candidate packages added on 2026-11-12 (user: test raster_tools, xDEM, scikit-image, Landlab, PCRaster, gdistance,
Orfeo ToolBox; every operation of the eight that a package has as a ready-made function, in the tested version).
Usage: python ops_cand.py <pkg> <op> <res> <out prefix>   (tools/ops_other.sh and tools/fa_cand.sh call it)
pkg = rt (raster_tools 0.13.2, dask), xdem (xDEM 0.2.3), xdemmp (xDEM
with its multiprocessing / out-of-memory mode, MultiprocConfig, default cluster: one process), xdemmpw (the same on
a multiprocessing cluster of NTHREADS workers; 2026-11-20), skimage (scikit-image 0.26.0), landlab (2.11.0),
pcraster (4.4.3, run with the pcraster env's Python), pcrastermc (the same with
pcraster.multicore on NTHREADS worker threads where it has the operation; 2026-11-20),\npyflwdir (0.5.12, cost surface only, the .venv env; added 2026-11-16).
Settings as for the other packages (ops_py.py): hillshade azimuth 270, altitude 30; slope in degrees + aspect; focal
median FOCAL_SIZE x FOCAL_SIZE; algebra ops_expr.py; series mean of the 12-layer stack; bicubic resampling of
data/elev_<RS_IN>m.tif onto the DEM grid; least-cost distance from COST_START and path to COST_END over
data/cost/friction_<res>m.tif; flow accumulation D8 with the package's depression handling (op fa, output
<out prefix>.tif in cells). Prints read / compute / write times. Not available in a package: exit code 3."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # ops_expr.py (python -I drops it)

pkg, op, res, out = sys.argv[1:5]
DEM = f"data/elev_{res}m.tif"
FS = int(os.environ.get("FOCAL_SIZE", 25))
NT = int(os.environ.get("NTHREADS", 8))
SERIES = f"data/series/{res}m{'_' + os.environ['SERIES_SET'] if os.environ.get('SERIES_SET') else ''}"
RS_IN = f"data/elev_{os.environ.get('RS_IN', '3')}m.tif"
t0 = time.perf_counter()


def stamp(what):
    global t0
    t = time.perf_counter()
    print(f"{what}: {t - t0:.2f} s", flush=True)
    t0 = t


def missing():
    print(f"{pkg} has no {op}", file=sys.stderr)
    sys.exit(3)


def xy(var, default):
    return tuple(map(float, os.environ.get(var, default).split(",")))


def read_np(path, dtype="float32"):
    """Array (NaN for no-data), profile."""
    import numpy as np
    import rasterio

    with rasterio.open(path) as s:
        a = s.read(1, masked=True).astype(dtype).filled(np.nan)
        return a, s.profile


def write_np(a, profile, path, dtype="float32"):
    import numpy as np
    import rasterio

    p = dict(profile, driver="GTiff", dtype=dtype, count=1, compress="deflate", tiled=True, blockxsize=512,
             blockysize=512, bigtiff="if_safer", num_threads=NT, nodata=np.nan if dtype.startswith("float") else 0)
    with rasterio.open(path, "w", **p) as d:
        d.write(a.astype(dtype), 1)


def rowcol(profile, x, y):
    import rasterio

    return rasterio.transform.rowcol(profile["transform"], x, y)


START, END = xy("COST_START", "1122385,-2618715"), xy("COST_END", "1206305,-2388085")

if pkg == "rt":
    import dask
    import numpy as np
    import raster_tools as rt
    from raster_tools import distance, focal, general, surface, warp

    dask.config.set(scheduler="threads", num_workers=NT)
    r = rt.Raster(DEM)
    stamp("open")
    if op == "relief":
        x = surface.hillshade(r, azimuth=270, altitude=30)
    elif op == "slope":
        x, x_asp = surface.slope(r, degrees=True), surface.aspect(r)
    elif op == "focal":
        x = focal.focal(r, "median", FS, FS, ignore_null=True)
    elif op == "algebra":
        from ops_expr import render

        a = r.astype("float32")
        x = eval(render("numpy", "a")).astype("float32")
    elif op == "series":
        x = general.local_stats(rt.band_concat([f"{SERIES}/s{k}.tif" for k in range(1, 13)]), "mean")
    elif op == "resample":
        x = warp.reproject(RS_IN, r.geobox, resample_method="cubic").astype("float32")
    elif op == "cost":  # cost distance + traceback (the traceback raster is the path's backlink; no path tool)
        f = rt.Raster(f"data/cost/friction_{res}m.tif")
        x = distance.cda_cost_distance(f, np.array([rowcol(dict(transform=f.affine), *START)]))
    else:
        missing()
    x.save(f"{out}.tif", compress="deflate")
    if op == "slope":
        x_asp.save(f"{out}_asp.tif", compress="deflate")
    stamp("compute + write")

elif pkg in ("xdem", "xdemmp", "xdemmpw"):
    import numpy as np
    import xdem
    from geoutils.raster.distributed_computing import ClusterGenerator, MultiprocConfig

    # out-of-memory mode: tiles of XDEM_CHUNK cells written straight to the output file; without a cluster
    # (xdemmp) GeoUtils runs the tiles one after another in this process, xdemmpw on NT worker processes
    cl = ClusterGenerator("multi", nb_workers=NT) if pkg == "xdemmpw" else None
    mp = (lambda o: MultiprocConfig(chunk_size=int(os.environ.get("XDEM_CHUNK", 4096)), outfile=o, cluster=cl)) \
        if pkg != "xdem" else (lambda o: None)
    if pkg != "xdem":  # its tiles go straight into the output files: start from none
        for k in ("", "_asp"):
            if os.path.exists(f"{out}{k}.tif"):
                os.remove(f"{out}{k}.tif")
    d = xdem.DEM(DEM) if pkg != "xdem" else xdem.DEM(DEM, load_data=True)
    stamp("read")
    outs = {}
    if op == "relief":
        # xDEM 0.2.3 turns the shading by 90 degrees: its azimuth=0 gives GDAL's (and the others') 270 (|r| 0.9998;
        # 270 gives |r| 0.03), although its docs describe azimuth clockwise from north
        outs[""] = d.hillshade(surface_fit="Horn", azimuth=0, altitude=30, mp_config=mp(f"{out}.tif"))
    elif op == "slope":
        outs[""] = d.slope(surface_fit="Horn", degrees=True, mp_config=mp(f"{out}.tif"))
        outs["_asp"] = d.aspect(surface_fit="Horn", degrees=True, mp_config=mp(f"{out}_asp.tif"))
    elif op == "focal" and pkg == "xdem":
        outs[""] = d.filter("median", size=FS)
    elif op == "algebra" and pkg == "xdem":
        from ops_expr import render

        a = d.astype("float32")
        outs[""] = eval(render("numpy", "a"))
    elif op == "series" and pkg == "xdem":
        import geoutils as gu

        s = [gu.Raster(f"{SERIES}/s{k}.tif", load_data=True) for k in range(1, 13)]
        m = s[0]
        for k in s[1:]:
            m = m + k
        outs[""] = m / 12
    elif op == "resample":
        outs[""] = xdem.DEM(RS_IN).reproject(ref=d, resampling="cubic", n_threads=NT,
                                              multiproc_config=mp(f"{out}.tif"))
    else:
        missing()
    stamp("compute")
    if cl is not None:
        cl.close()
    for k, v in outs.items():
        if pkg == "xdem":  # xdemmp(w) wrote its tiles to the output file already
            v.save(f"{out}{k}.tif", co_opts={"COMPRESS": "DEFLATE", "TILED": "YES", "BIGTIFF": "IF_SAFER"})
    stamp("write")

elif pkg == "skimage":
    import numpy as np

    if op == "focal":  # scipy.ndimage.median_filter behind skimage.filters.median (float input)
        from skimage.filters import median

        a, p = read_np(DEM)
        stamp("read")
        x = median(a, footprint=np.ones((FS, FS), bool), behavior="ndimage")
        x[np.isnan(a)] = np.nan
    elif op == "resample":  # bicubic spline (order 3) from the RS_IN grid onto the DEM grid
        from skimage.transform import AffineTransform, warp

        s, ps = read_np(RS_IN)
        _, p = read_np(DEM)
        stamp("read")
        # output (col, row) -> source (col, row) through map coordinates (cell centres)
        m = ~ps["transform"] * p["transform"]
        x = warp(s, AffineTransform(matrix=np.array([[m.a, m.b, m.c], [m.d, m.e, m.f], [0, 0, 1]])),
                 output_shape=(p["height"], p["width"]), order=3, mode="constant", cval=np.nan, preserve_range=True)
    elif op == "cost":  # MCP_Geometric: cumulative cost with diagonal steps x sqrt(2), times the cell size
        from skimage.graph import MCP_Geometric

        f, p = read_np(f"data/cost/friction_{res}m.tif", "float64")
        stamp("read")
        f[np.isnan(f)] = np.inf
        mcp = MCP_Geometric(f, fully_connected=True)
        c, _ = mcp.find_costs([rowcol(p, *START)])
        x = (c * abs(p["transform"].a)).astype("float32")
        x[~np.isfinite(x)] = np.nan
        path = np.zeros(f.shape, "uint8")
        rr, cc = np.array(mcp.traceback(rowcol(p, *END))).T
        path[rr, cc] = 1
        write_np(path, p, f"{out}_path.tif", "uint8")
    else:
        missing()
    stamp("compute")
    write_np(x, p, f"{out}.tif")
    stamp("write")

elif pkg == "landlab":
    import numpy as np
    from landlab import RasterModelGrid

    a, p = read_np(DEM, "float64")
    stamp("read")
    # Landlab nodes start at the lower-left corner: row 0 is the south edge, so the GeoTIFF rows are flipped
    g = RasterModelGrid(a.shape, xy_spacing=abs(p["transform"].a))
    z = g.add_field("topographic__elevation", np.flipud(a).ravel(), at="node")
    nd = np.isnan(np.asarray(z))
    z[nd] = -9999.0
    g.set_nodata_nodes_to_closed(z, -9999.0)
    stamp("grid")
    if op == "fa":
        from landlab.components import FlowAccumulator

        fa = FlowAccumulator(g, flow_director="FlowDirectorD8", depression_finder="DepressionFinderAndRouter")
        fa.run_one_step()
        x = g.at_node["drainage_area"] / abs(p["transform"].a) ** 2  # cells
    elif op == "relief":
        x = g.calc_hillshade_at_node(elevs="topographic__elevation", alt=30.0, az=270.0)
    elif op == "slope":
        x = np.degrees(g.calc_slope_at_node(elevs="topographic__elevation"))
        x_asp = g.calc_aspect_at_node(elevs="topographic__elevation", unit="degrees")
    else:
        missing()
    stamp("compute")
    for k, v in ({"": x, "_asp": x_asp} if op == "slope" else {"": x}).items():
        v = np.flipud(np.asarray(v).reshape(a.shape)).astype("float32")
        v[np.flipud(nd.reshape(a.shape))] = np.nan
        write_np(v, p, f"{out}{k}.tif")
    stamp("write")

elif pkg in ("pcraster", "pcrastermc"):
    import numpy as np
    import pcraster as pcr

    M = pcr  # the operations below; pcrastermc: their pcraster.multicore versions where they exist
    if pkg == "pcrastermc":
        import pcraster.multicore as M  # also replaces the Field operators (+ - * / ...) with multicore ones

        M.set_nr_worker_threads(NT)
        print(f"pcraster.multicore worker threads: {M.nr_worker_threads()}", flush=True)

    _, p = read_np(DEM)
    t = p["transform"]
    # setclone and readmap take only PCRaster's own format: the grid from the GeoTIFF, maps through numpy2pcr
    pcr.setclone(p["height"], p["width"], abs(t.a), t.c, t.f)
    pcr.setglobaloption("unitcell" if op == "fa" else "unittrue")

    def rdm(path):
        return pcr.numpy2pcr(pcr.Scalar, read_np(path)[0], np.nan)

    if op == "fa":  # lddcreate with every pit removed (huge outflow depth, core volume and area), then accuflux
        d = rdm(DEM)
        stamp("read")
        big = 1e31
        x = pcr.accuflux(pcr.lddcreate(d, big, big, big, big), 1)
    elif op == "slope":
        d = rdm(DEM)
        stamp("read")
        # atan in degrees (default); aspect has no multicore version
        x, x_asp = M.scalar(M.atan(M.slope(d))), pcr.scalar(pcr.aspect(d))
    elif op == "algebra":
        from ops_expr import render

        d = rdm(DEM)
        stamp("read")
        # exp has no multicore version, nor has unary minus
        x = eval(render("grass", "d").replace("sqrt(", "M.sqrt(").replace("exp(", "pcr.exp(")
                 .replace("abs(", "M.abs("))
    elif op == "series":
        s = [rdm(f"{SERIES}/s{k}.tif") for k in range(1, 13)]
        stamp("read")
        x = s[0]
        for k in s[1:]:
            x = x + k
        x = x / 12
    elif op == "cost":  # spread: accumulated friction x distance from the start cell; no least-cost path tool
        f = rdm(f"data/cost/friction_{res}m.tif")
        stamp("read")
        r_, c_ = rowcol(p, *START)
        pts = np.zeros((p["height"], p["width"]), "int32")
        pts[r_, c_] = 1
        x = pcr.spread(pcr.numpy2pcr(pcr.Nominal, pts, -1), 0, f)  # 0 = not a source (not missing)
    else:
        missing()
    stamp("compute")
    for k, v in ({"": x, "_asp": x_asp} if op == "slope" else {"": x}).items():
        write_np(pcr.pcr2numpy(v, np.nan), p, f"{out}{k}.tif")
    stamp("write")
elif pkg == "pyflwdir":  # coverage audit 2026-11-13: pyflwdir's only operation besides flow accumulation
    import numpy as np
    from pyflwdir import gis_utils

    if op != "cost":
        missing()
    # spread2d: 8-neighbour Dijkstra from the observation cells through the mask; each step costs the step length
    # (diagonal = hypot) times the friction; no least-cost path tool
    f, p = read_np(f"data/cost/friction_{res}m.tif", "float32")
    stamp("read")
    msk = np.isfinite(f)
    f[~msk] = 0
    obs = np.zeros(f.shape, "int8")
    obs[rowcol(p, *START)] = 1
    _, _, x = gis_utils.spread2d(obs, msk=msk, nodata=0, frc=f, latlon=False, transform=tuple(p["transform"])[:6])
    del obs, f
    x[~msk] = np.nan
    stamp("compute")
    write_np(x, p, f"{out}.tif")
    stamp("write")
else:
    sys.exit(f"unknown package {pkg}")
