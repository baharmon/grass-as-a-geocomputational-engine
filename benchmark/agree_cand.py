"""Agreement of the candidate packages (ops_cand.py, cost_gdistance.R, OTB) with a reference package at one resolution:
python agree_cand.py <res> [pkg ...]; AGREE_OPS="series ..." limits the operations. Interior land cells (2 cells in from the data edge; FOCAL_SIZE // 2 + 2 for
focal). Reference: GDAL (relief, slope, focal, algebra, series, resample), GRASS r.cost (cost), pyflwdir (flow
accumulation). Relief: |r| of the shading; slope: mean |difference| of slope (degrees) and of aspect (circular);
others: mean and max |difference|; cost: |r| and the relative difference of the median (median from every 97th
cell); flow accumulation: share of cells with the same count, the largest count and |r| of log(1 + count).
Reads in row blocks (BLOCK_ROWS, default 2048) so that Iceland 10 m (2.1e9 cells) fits in a few GB.
Outputs may carry the series set in their name (<op>_<SERIES_SET>_<pkg>, as written by ops_other.sh)."""

import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage

r = sys.argv[1]
PK = sys.argv[2:] or ["rt", "xdem", "xdemmp", "skimage", "landlab", "pcraster", "gdistance", "otb"]
O = Path("out/ops")
SS = os.environ.get("SERIES_SET", "")
B = int(os.environ.get("BLOCK_ROWS", 2048))
REF = {"relief": "gdal", "slope": "gdal", "focal": "gdal", "algebra": "gdal", "series": "gdal", "resample": "gdal",
       "cost": "grass"}


def find(op, p, suffix=""):
    for name in ([f"{op}_{SS}_{p}", f"{op}_{p}"] if SS else [f"{op}_{p}"]):
        for ext in (".tif", ".sdat"):  # SAGA writes its own grid format (as in agree_ice.py)
            f = O / f"{name}_{r}m{suffix}{ext}"
            if f.exists():
                return f
    return None


DEM = rasterio.open(f"data/elev_{r}m.tif")
H, W = DEM.height, DEM.width


def blocks(k):
    """Row blocks (core rows, interior mask of the core) with a halo of k rows for the erosion."""
    for y0 in range(0, H, B):
        y1 = min(y0 + B, H)
        a0, a1 = max(y0 - k, 0), min(y1 + k, H)
        land = ~np.ma.getmaskarray(DEM.read(1, window=Window(0, a0, W, a1 - a0), masked=True))
        # rows outside the raster count as no data, as in the whole-raster erosion
        pad = np.zeros((k, W), bool)
        land = np.vstack([pad] * (a0 == 0 and k > 0) + [land] + [pad] * (a1 == H and k > 0))
        off = y0 - a0 + (k if a0 == 0 else 0)
        m = ndimage.binary_erosion(land, iterations=k)[off:off + (y1 - y0)]
        yield Window(0, y0, W, y1 - y0), m


def rd(src, w):
    a = src.read(1, window=w, masked=True)
    return a.astype("f8").filled(np.nan)


class Acc:
    def __init__(self):
        self.n = self.sx = self.sy = self.sxx = self.syy = self.sxy = self.sd = 0.0
        self.dmax = 0.0
        self.miss = self.ref_n = 0
        self.sub_x, self.sub_y = [], []
        self.an = self.asd = self.a90 = 0.0

    def add(self, x, y):
        self.n += x.size
        self.sx += x.sum(); self.sy += y.sum()
        self.sxx += (x * x).sum(); self.syy += (y * y).sum(); self.sxy += (x * y).sum()
        if x.size:
            d = np.abs(x - y)
            self.sd += d.sum(); self.dmax = max(self.dmax, d.max())
        self.sub_x.append(x[::97]); self.sub_y.append(y[::97])

    def r(self):
        n = self.n
        cov = self.sxy / n - self.sx / n * self.sy / n
        return abs(cov / np.sqrt((self.sxx / n - (self.sx / n) ** 2) * (self.syy / n - (self.sy / n) ** 2)))


OPS = os.environ.get("AGREE_OPS", "").split()  # only these operations (default: all)
for op, ref in REF.items():
    if OPS and op not in OPS:
        continue
    f0 = find(op, ref)
    if f0 is None:
        print(f"{op}: no reference {ref}", flush=True)
        continue
    cands = {p: find(op, p) for p in PK}
    cands = {p: f for p, f in cands.items() if f is not None}
    if not cands:
        continue
    s0 = rasterio.open(f0)
    S = {p: rasterio.open(f) for p, f in cands.items()}
    for p, s in list(S.items()):
        if (s.height, s.width) != (H, W):
            print(f"{op:8} {p:9} shape {(s.height, s.width)} vs {(H, W)}")
            del S[p]
    asp0 = rasterio.open(find(op, ref, "_asp")) if op == "slope" and find(op, ref, "_asp") else None
    ASP = {p: rasterio.open(find(op, p, "_asp")) for p in S if op == "slope" and find(op, p, "_asp")}
    A = {p: Acc() for p in S}
    k = int(os.environ.get("FOCAL_SIZE", 25)) // 2 + 2 if op == "focal" else 2
    for w, m in blocks(k):
        a0 = rd(s0, w)
        b0 = rd(asp0, w) if asp0 is not None else None
        for p, s in S.items():
            a = rd(s, w)
            v = m & np.isfinite(a) & np.isfinite(a0)
            acc = A[p]
            acc.miss += int((m & np.isfinite(a0) & ~np.isfinite(a)).sum())
            acc.ref_n += int((m & np.isfinite(a0)).sum())
            acc.add(a[v], a0[v])
            if p in ASP and b0 is not None:
                b = rd(ASP[p], w)
                ww = v & np.isfinite(b) & np.isfinite(b0) & (a0 > 1)  # aspect where slope > 1 degree
                da = np.abs((b[ww] - b0[ww] + 180) % 360 - 180)
                acc.an += da.size; acc.asd += da.sum(); acc.a90 += (da > 90).sum()
    for p, acc in A.items():
        if op in ("relief", "cost"):
            extra = f"|r| {acc.r():.4f}"
            if op == "cost":
                extra += f", median {np.median(np.concatenate(acc.sub_x)) / np.median(np.concatenate(acc.sub_y)):.4f} of ref"
        else:
            extra = f"mean |d| {acc.sd / acc.n:.4g}, max {acc.dmax:.4g}"
            if acc.an:
                extra += f"; aspect mean |d| {acc.asd / acc.an:.3g} (|d| > 90: {acc.a90 / acc.an:.1%})"
        print(f"{op:8} {p:9} {extra}; no value on {acc.miss / max(acc.ref_n, 1):.2%} of the reference's interior cells",
              flush=True)

f0 = Path(f"out/acc_pyflwdir_{r}m.tif")
for p in PK if not OPS or "fa" in OPS else []:
    f = Path(f"out/acc_{p}_{r}m.tif")
    if not f.exists() or not f0.exists():
        continue
    s, s0 = rasterio.open(f), rasterio.open(f0)
    n = same = 0
    mx = mx0 = 0.0
    acc = Acc()
    for w, m in blocks(2):
        a, a0 = rd(s, w), rd(s0, w)
        v = m & np.isfinite(a) & np.isfinite(a0)
        n += v.sum(); same += (a[v] == a0[v]).sum()
        mx = max(mx, np.nanmax(a, initial=0)); mx0 = max(mx0, np.nanmax(a0, initial=0))
        acc.add(np.log1p(a[v]), np.log1p(a0[v]))
    print(f"fa       {p:9} same count on {same / n:.1%}, max {mx:.0f} vs {mx0:.0f} (pyflwdir), |r| of log {acc.r():.4f}")
