"""GDAL steps around Sedona (tools/sedona.sh), with overlapping tiles for neighbourhood operations.
  tile <src.tif> <out dir> <T> <H> <np>: split src into T x T tiles t_<x>_<y>.tif, each with H cells of its
      neighbours on every side (H = 0: no overlap), np tiles at a time, DEFLATE.
  mosaic <tiles dir> <out.tif> <target.tif> <src.tif> <T> <H> <np>: one DEFLATE GeoTIFF on the grid of target
      from the tiles Sedona wrote (named as their input tiles). With H > 0 each tile is first cut back to the
      area of its input tile without the overlap (src gives that tile grid), so every cell comes from the tile
      that computed it with its neighbours.
Sedona's own tiling (RS_TileExplode, RS_Tile) has no overlap, so cells at tile edges lack neighbours (README
section 19); this is the usual halo approach of tiled raster processing (as dask map_overlap). Run with the QGIS
environment's Python (GDAL bindings)."""

import glob
import multiprocessing
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

from osgeo import gdal

gdal.UseExceptions()


def windows(src, T, H):
    """(x, y, xoff, yoff, xsize, ysize) of every tile of src, overlap H included, clipped to the raster."""
    ds = gdal.Open(src)
    w, h = ds.RasterXSize, ds.RasterYSize
    for y in range(0, (h + T - 1) // T):
        for x in range(0, (w + T - 1) // T):
            x0, y0 = max(0, x * T - H), max(0, y * T - H)
            x1, y1 = min(w, (x + 1) * T + H), min(h, (y + 1) * T + H)
            yield x, y, x0, y0, x1 - x0, y1 - y0


def _cut(a):  # the gdal_translate program, as without overlap: the Python bindings here write the CRS without its
    # EPSG code, which Sedona's GeoTools reader refuses ("Only Geographic & Projected Systems are supported")
    src, out, xoff, yoff, xs, ys = a
    subprocess.run([os.path.join(os.path.dirname(sys.executable), "gdal_translate"), "-q", "-srcwin", str(xoff),
                    str(yoff), str(xs), str(ys), "-co", "COMPRESS=DEFLATE", src, out], check=True)


def tile(src, out, T, H, np):
    os.makedirs(out, exist_ok=True)
    jobs = [(src, f"{out}/t_{x}_{y}.tif", *win) for x, y, *win in windows(src, T, H)]
    with ProcessPoolExecutor(np, mp_context=multiprocessing.get_context("fork")) as ex:  # no forkserver socket
        list(ex.map(_cut, jobs, chunksize=4))


def mosaic(tiles, out, target, src, T, H, np):
    t = gdal.Open(target)
    gt, tw, th = t.GetGeoTransform(), t.RasterXSize, t.RasterYSize
    te = [gt[0], gt[3] + th * gt[5], gt[0] + tw * gt[1], gt[3]]
    files = sorted(glob.glob(f"{tiles}/**/t_*.tif", recursive=True))
    if H > 0:  # each tile cut back to its own input tile's area (map coordinates of the src tile grid)
        s = gdal.Open(src)
        sg, sw, sh = s.GetGeoTransform(), s.RasterXSize, s.RasterYSize
        cut = []
        for f in files:
            x, y = map(int, re.search(r"t_(\d+)_(\d+)\.tif$", f).groups())
            c0, r0, c1, r1 = x * T, y * T, min(sw, (x + 1) * T), min(sh, (y + 1) * T)
            v = f[:-4] + "_core.vrt"
            gdal.BuildVRT(v, [f], outputBounds=[sg[0] + c0 * sg[1], sg[3] + r1 * sg[5], sg[0] + c1 * sg[1],
                                                sg[3] + r0 * sg[5]], xRes=gt[1], yRes=-gt[5])
            cut.append(v)
        files = cut
    vrt = out[:-4] + ".vrt"
    gdal.BuildVRT(vrt, files, outputBounds=te, xRes=gt[1], yRes=-gt[5])
    gdal.SetConfigOption("GDAL_NUM_THREADS", str(np))
    gdal.Translate(out, vrt, creationOptions=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER",
                                              f"NUM_THREADS={np}"])


if __name__ == "__main__":
    cmd, *a = sys.argv[1:]
    if cmd == "tile":
        tile(a[0], a[1], int(a[2]), int(a[3]), int(a[4]))
    else:
        mosaic(a[0], a[1], a[2], a[3], int(a[4]), int(a[5]), int(a[6]))
