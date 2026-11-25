"""D8 flow accumulation in xarray-spatial and TopoToolbox for the flow-accumulation harness
(tools/xrs.sh, tools/topotoolbox.sh): python fa_py.py <xrs|tt> <dem.tif> <out.tif>.
xarray-spatial: fill -> flow_direction (D8) -> flow_accumulation. TopoToolbox: FlowObject (D8,
its default sink handling: fill + carving through flats) -> flow_accumulation. Prints phase times."""

import sys
import time

pkg, dem, out = sys.argv[1:4]
t0 = time.perf_counter()


def stamp(what):
    global t0
    t = time.perf_counter()
    print(f"{what}: {t - t0:.2f} s", flush=True)
    t0 = t


if pkg == "xrs":
    import rioxarray
    import xrspatial

    a = rioxarray.open_rasterio(dem, masked=True).squeeze("band", drop=True).astype("float64").load()
    stamp("read")
    f = xrspatial.fill(a)
    stamp("fill")
    d = xrspatial.flow_direction(f)
    stamp("direction")
    acc = xrspatial.flow_accumulation(d)
    stamp("accumulation")
    acc.rio.write_crs(a.rio.crs, inplace=True)
    acc.astype("float32").rio.to_raster(out, compress="deflate", tiled=True)
    stamp("write")
elif pkg == "tt":
    import topotoolbox as tt

    g = tt.read_tif(dem)
    stamp("read")
    fd = tt.FlowObject(g)
    stamp("flow directions (fill, flats)")
    acc = fd.flow_accumulation()
    stamp("accumulation")
    if not isinstance(acc, tt.GridObject):
        acc = g.duplicate_with_new_data(acc)
    tt.write_tif(acc, out)
    stamp("write")
