"""Compare a Sedona output (mosaic GeoTIFF or VRT of the tiles) with a reference output of another package:
python sedona_check.py <sedona.tif|vrt> <reference.tif>. Prints cells valid in both, valid in only one, and the
absolute difference (max, 99.9th percentile, mean) over the cells valid in both. Read in row blocks."""
import sys

import numpy as np
import rasterio
from rasterio.windows import Window

a, b = rasterio.open(sys.argv[1]), rasterio.open(sys.argv[2])
assert a.shape == b.shape, (a.shape, b.shape)
n_both = n_a = n_b = 0
mx, s = 0.0, 0.0
hist = np.zeros(200)
edges = np.concatenate([[0], np.logspace(-7, 3, 199)])
for r0 in range(0, a.height, 1024):
    w = Window(0, r0, a.width, min(1024, a.height - r0))
    x, y = a.read(1, window=w, masked=True).astype("float64"), b.read(1, window=w, masked=True).astype("float64")
    vx = ~np.ma.getmaskarray(x) & np.isfinite(x.filled(np.nan))
    vy = ~np.ma.getmaskarray(y) & np.isfinite(y.filled(np.nan))
    both = vx & vy
    n_both += both.sum(); n_a += (vx & ~vy).sum(); n_b += (vy & ~vx).sum()
    d = np.abs(x.data[both] - y.data[both])
    if d.size:
        mx = max(mx, d.max()); s += d.sum(); hist += np.histogram(d, bins=np.append(edges, np.inf))[0][:200]
c = np.cumsum(hist) / max(n_both, 1)
p999 = edges[np.searchsorted(c, 0.999)] if n_both else np.nan
print(f"both {n_both} only_sedona {n_a} only_ref {n_b} max {mx:.6g} p99.9 <= {p999:.3g} mean {s / max(n_both, 1):.3g}")
