"""Rewrite a Float32 GeoTIFF with NaN no-data as one with an explicit no-data value (-9999).

TauDEM, RichDEM, terra and pysheds MFD do not treat NaN as no-data (found 2026-10-16: TauDEM
filled the Iceland sea as a depression). Processed
block by block, so a multi-GB grid never has to fit in memory. Layout kept: deflate, 256 x 256
tiles, BigTIFF.

Usage: nan_to_nodata.py <in.tif> <out.tif>
"""

import sys

import numpy as np
import rasterio

NODATA = -9999.0
src_path, dst_path = sys.argv[1], sys.argv[2]
with rasterio.open(src_path) as src:
    profile = src.profile
    profile.update(nodata=NODATA, compress="deflate", tiled=True, blockxsize=256, blockysize=256,
                   BIGTIFF="YES", dtype="float32")
    n_nan = 0
    with rasterio.open(dst_path, "w", **profile) as dst:
        for _, window in dst.block_windows(1):
            a = src.read(1, window=window)
            nan = ~np.isfinite(a)
            n_nan += int(nan.sum())
            a[nan] = NODATA
            dst.write(a, 1, window=window)
print(f"{dst_path}: {n_nan:,} NaN cells set to {NODATA}")
