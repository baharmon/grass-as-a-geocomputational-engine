"""Agreement of the paper_iceland.sh outputs at one resolution, in row strips, so it works on Iceland 10 m
(2.14B cells): .venv-xrs/bin/python agree_ice.py <res> (e.g. ice10, ice100, 10, 1).

Exports the GRASS outputs of the last run from <project>/ops first (r.out.gdal, untimed); optional operation names after <res> limit the check. Land cells only, eroded
by 2 cells (13 for the focal median 25 x 25) so that edge handling does not count. Per operation and package:
- algebra, series: max relative difference to a float64 NumPy reference (ops_expr.py; DEM + 6.5);
- relief: |r| with GRASS (SAGA's shading runs the other way);
- slope: r and mean |difference| with GRASS, degrees (TopoToolbox gives a tangent);
- focal median, resampling: max and mean |difference| with GRASS, share of cells off by more than 1 mm;
- least-cost distance: r with GRASS (GRASS and SAGA count in cells, the others in map units).
Every comparison also reports the land cells where the package has no value."""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from ops_expr import render  # noqa: E402

r = sys.argv[1]
ONLY = set(sys.argv[2:])  # optional operations to check, e.g. agree_ice.py ice10 focal
O = Path("out/ops")
STRIP = 1024
ice = r.startswith("ice")
project = "project_iceland" if ice else "project"
grass_bin = os.environ.get("GRASS_BIN", "grass-85-o2/bin.x86_64-pc-linux-gnu/grass")

# GRASS outputs (map names in tools/ops_grass.sh) -> out/ops/<op>_grass_<res>m.tif
GRASS_MAPS = {"relief": "rel", "slope": "slp", "focal": "avg", "algebra": "alg", "series": "smean", "resample": "rs",
              "cost": "cost"}
exports = " && ".join(f"r.out.gdal -c -f input={m} output={O}/{op}_grass_{r}m.tif type=Float32 "
                      f"createopt=COMPRESS=DEFLATE,TILED=YES,BIGTIFF=YES --o --q" for op, m in GRASS_MAPS.items() if not ONLY or op in ONLY)
subprocess.run([grass_bin, f"{project}/ops", "--exec", "bash", "-c", f"g.region raster=elev_{r}m && {exports}"],
               check=False)

dem = rasterio.open(f"data/elev_{r}m.tif")
H = dem.height


def path(op, pkg):
    for ext in (".tif", ".sdat"):
        p = O / f"{op}_{pkg}_{r}m{ext}"
        if p.exists():
            return p
    return None


def strips(op, pkgs, k):
    """Yield (land mask, {pkg: float64 strip with NaN for no data}) per row strip, land eroded by k cells."""
    src = {p: rasterio.open(f) for p in pkgs if (f := path(op, p)) is not None}
    off = {}  # row/col offset of the DEM grid in a package grid with the same cell size and a larger extent
    for p, s in src.items():
        dr, dc = (dem.bounds.top - s.bounds.top) / -s.res[1], (dem.bounds.left - s.bounds.left) / s.res[0]
        if s.shape != dem.shape and s.res == dem.res and dr == int(dr) >= 0 and dc == int(dc) >= 0 \
                and s.height >= H + dr and s.width >= dem.width + dc:
            off[p] = (int(dr), int(dc))
            print(f"  {p}: grid {s.shape}, DEM grid at row {int(dr)}, column {int(dc)} of it")
    bad = [p for p, s in src.items() if s.shape != dem.shape and p not in off]
    for p in bad:
        print(f"  {p}: grid {src[p].shape} differs from the DEM {dem.shape}, skipped")
        del src[p]
    for row in range(0, H, STRIP):
        top, bot = max(row - k, 0), min(row + STRIP + k, H)
        e = dem.read(1, window=Window(0, top, dem.width, bot - top))
        # square structuring element: k iterations cover a (2k+1) x (2k+1) window (the default cross only a diamond)
        land = ndimage.binary_erosion(e != dem.nodata, np.ones((3, 3), bool), iterations=k) if k else e != dem.nodata
        cut = slice(row - top, row - top + min(STRIP, H - row))
        land = land[cut]
        if not land.any():
            continue
        out = {}
        for p, s in list(src.items()):
            try:  # outputs of failed or capped runs can be partial
                dr, dc = off.get(p, (0, 0))
                v = s.read(1, window=Window(dc, row + dr, dem.width, land.shape[0])).astype("f8")
            except Exception as err:  # noqa: BLE001
                print(f"  {p}: unreadable at row {row} ({type(err).__name__}), skipped")
                del src[p]
                continue
            if s.nodata is not None:
                v[v == s.nodata] = np.nan
            out[p] = v
        yield land, e[cut].astype("f8"), out


class Acc:
    """Streaming statistics of x (package) against y (reference) over valid cells."""

    def __init__(self):
        self.n = self.missing = 0
        self.s = np.zeros(5)  # sx, sy, sxx, syy, sxy
        self.absd = self.maxd = self.maxrel = 0.0
        self.over = 0

    def add(self, x, y, land):
        ok = land & np.isfinite(x) & np.isfinite(y)
        self.missing += int((land & np.isfinite(y) & ~np.isfinite(x)).sum())
        x, y = x[ok], y[ok]
        if not x.size:
            return
        self.n += x.size
        self.s += [x.sum(), y.sum(), (x * x).sum(), (y * y).sum(), (x * y).sum()]
        d = np.abs(x - y)
        self.absd += d.sum()
        self.maxd = max(self.maxd, d.max())
        self.maxrel = max(self.maxrel, (d / np.maximum(np.abs(y), 1e-9)).max())
        self.over += int((d > 1e-3).sum())

    def r(self):
        sx, sy, sxx, syy, sxy = self.s / self.n
        return (sxy - sx * sy) / np.sqrt((sxx - sx * sx) * (syy - sy * sy))

    def line(self, *what):
        if not self.n:
            return "no cells"
        f = {"r": f"r {self.r():.5f}", "absr": f"|r| {abs(self.r()):.5f}", "mean": f"mean |diff| {self.absd / self.n:.4g}",
             "max": f"max |diff| {self.maxd:.4g}", "rel": f"max rel diff {self.maxrel:.1e}",
             "over": f">1 mm {self.over / self.n:.3%}"}
        return ", ".join([f[w] for w in what] + [f"cells {self.n}", f"no value on land {self.missing}"])


def compare(op, ref, pkgs, k, what, ref_fn=None, fix=None):
    print(f"{op} (reference: {ref}):", flush=True)
    acc = {p: Acc() for p in pkgs if p != ref}
    for land, e, a in strips(op, ([ref] if ref_fn is None else []) + pkgs, k):
        if fix:
            fix(a)
        y = ref_fn(e) if ref_fn else a.get(ref)
        if y is None:
            break
        for p in acc:
            if p in a:
                acc[p].add(a[p], y, land)
    for p, s in acc.items():
        if path(op, p) is not None:
            print(f"  {p}: {s.line(*what)}", flush=True)


def tt_slope(a):
    if "tt" in a:  # TopoToolbox evansslope is a tangent
        a["tt"] = np.degrees(np.arctan(a["tt"]))


# PKGS: other package names to check (output <op>_<pkg>_<res>m), e.g. PKGS="wbtsd2 terra" for variants
ALL = os.environ.get("PKGS", "gdal terra saga wbw wbt xrs xrsdask tt").split()


def want(op):
    return not ONLY or op in ONLY

print(f"== {r}, strips of {STRIP} rows{', only ' + ' '.join(sorted(ONLY)) if ONLY else ''}", flush=True)
want("algebra") and compare("algebra", "float64 reference", ["grass"] + ALL, 2, ("rel",), ref_fn=lambda e: eval(render("numpy", "e")))
want("series") and compare("series", "DEM + 6.5", ["grass"] + ALL, 2, ("rel",), ref_fn=lambda e: e + 6.5)
want("relief") and compare("relief", "grass", ALL, 2, ("absr",))
want("slope") and compare("slope", "grass", ALL + ([] if "PKGS" in os.environ else ["richdem"]), 2, ("r", "mean"), fix=tt_slope)
want("resample") and compare("resample", "grass", ALL, 2, ("max", "mean", "over"))
want("focal") and compare("focal", "grass", ALL, 13, ("max", "mean", "over"))
want("cost") and compare("cost", "grass", [p for p in ALL if p not in ("gdal", "xrsdask", "tt")], 0, ("r",))
