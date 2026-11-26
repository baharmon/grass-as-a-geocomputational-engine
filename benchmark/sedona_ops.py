"""Raster operations in Apache Sedona (Spark, local mode) for tools/sedona.sh:
python sedona_ops.py <op> <res> <out dir>. op = algebra | series | resample.

Input: data/elev_<res>m.tif read whole (one binaryFile row, RS_FromGeoTiff, RS_TileExplode into TILE x TILE
tiles, repartitioned over the cores), or, with SEDONA_INPUT=tiles, the GeoTIFF tiles made by
tools/sedona.sh (data/sedona_tiles/<name><TILE_SUFFIX>/, one row per tile; TILE_SUFFIX=_h<n> for tiles that
overlap by n cells, tools/sedona_gdal.py; needed where one raster object would be
too large, Iceland 10 m). Output: one GeoTIFF per tile in <out dir> (Sedona's raster writer); the mosaic to
one file is a separate GDAL step (tools/sedona.sh, SEDONA_STEP=mosaic).

SEDONA_STOP = start | read | compute | write (default): stop after that step, so that run.sh can time each
step separately (read and compute end with a pixel count, which forces the lazy plan to run). The script
also prints its own step times. Bicubic resampling sees only
its tile: cells next to tile edges have no neighbours there and come out as no data (Sedona has no tile
overlap), see the quality notes in README; with overlapping GDAL tiles (HALO in tools/sedona.sh) they do.

Settings as for the other packages: algebra = ops_expr.py; series = mean of the 12-layer stack; resample =
bicubic from data/elev_<RS_IN>m.tif onto the <res> grid."""

import atexit
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # ops_expr.py (python -I drops it)
import ops_expr  # noqa: E402

op, res, out = sys.argv[1:4]
stop = os.environ.get("SEDONA_STOP", "write")
tile = int(os.environ.get("TILE", 2048))
nt = int(os.environ.get("NTHREADS", 8))
ND = -9999.0
t0 = t_start = time.perf_counter()


def stamp(what):
    global t0
    t = time.perf_counter()
    print(f"{what}: {t - t0:.2f} s (total {t - t_start:.2f} s)", flush=True)
    t0 = t


from sedona.spark import SedonaContext  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

cfg = (
    SedonaContext.builder()
    .master(f"local[{nt}]")
    .config("spark.jars", ",".join(sorted(glob.glob("envs/sedona_jars/*.jar"))))
    .config("spark.driver.memory", os.environ.get("SEDONA_HEAP", "48g"))
    .config("spark.driver.maxResultSize", "4g")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.shuffle.partitions", str(4 * nt))
    .getOrCreate()
)
spark = SedonaContext.create(cfg)
spark.sparkContext.setLogLevel("ERROR")


def report_peak():
    """Peak RSS of the JVM (VmHWM, read before Spark stops it) and of this Python process, for the harness
    and the JVM's CPU time (/usr/bin/time does not see the JVM, which PySpark starts and kills itself)."""
    import resource

    try:
        pid = spark.sparkContext._jvm.java.lang.ProcessHandle.current().pid()
        with open(f"/proc/{pid}/status") as f:
            jvm = next(int(line.split()[1]) for line in f if line.startswith("VmHWM"))
        with open(f"/proc/{pid}/stat") as f:
            st = f.read().rsplit(")", 1)[1].split()
        jvm_cpu = (int(st[11]) + int(st[12])) / os.sysconf("SC_CLK_TCK")  # utime + stime
    except Exception:  # noqa: BLE001
        jvm, jvm_cpu = -1, 0.0
    py = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"peak_rss_kb jvm {jvm} python {py} jvm_cpu_s {jvm_cpu:.1f}", flush=True)
    if os.environ.get("PEAKFILE"):
        with open(os.environ["PEAKFILE"], "w") as f:
            f.write(f"{jvm} {py} {jvm_cpu:.1f}\n")


atexit.register(report_peak)
stamp("start")
if stop == "start":
    sys.exit(0)


def tiles_of(name):
    """DataFrame (tx, ty, r) of one raster: whole file + RS_TileExplode, or the pre-made tiles."""
    if os.environ.get("SEDONA_INPUT", "whole") == "tiles":
        df = spark.read.format("binaryFile").load(f"data/sedona_tiles/{name}{os.environ.get('TILE_SUFFIX', '')}/*.tif")
        xy = F.regexp_extract("path", r"t_(\d+)_(\d+)\.tif$", 1), F.regexp_extract("path", r"t_(\d+)_(\d+)\.tif$", 2)
        return df.select(xy[0].cast("int").alias("tx"), xy[1].cast("int").alias("ty"),
                         F.expr("RS_FromGeoTiff(content)").alias("r"))
    df = spark.read.format("binaryFile").load(f"data/{name}.tif")
    return (df.selectExpr(f"RS_TileExplode(RS_FromGeoTiff(content), {tile}, {tile})")
            .select(F.col("x").alias("tx"), F.col("y").alias("ty"),
                    F.expr(f"RS_SetBandNoDataValue(tile, 1, {ND})").alias("r"))  # tiles lose it
            .repartition(4 * nt))


def force(df, what):
    """Run the plan so far: count the valid cells of every tile."""
    n = df.selectExpr("sum(RS_SummaryStats(r, 'count', 1, true)) as n").collect()[0][0]
    stamp(f"{what} (valid cells {n:.0f})")


def jiffle(script):
    return f"RS_MapAlgebra(r, 'F', '{script}', {ND})"


def union12(item):
    """12-band raster from the layers k = 1..12 (RS_Union takes at most 7 rasters: two levels)."""
    half = lambda ks: "RS_Union(" + ", ".join(item.format(k=k) for k in ks) + ")"  # noqa: E731
    return f"RS_Union({half(range(1, 7))}, {half(range(7, 13))})"


if op == "series":
    if os.environ.get("SEDONA_INPUT", "whole") == "tiles":
        sfx = os.environ.get("TILE_SUFFIX", "")
        ss = "_" + os.environ["SERIES_SET"] if os.environ.get("SERIES_SET") else ""  # tools/sedona.sh
        df = spark.read.format("binaryFile").load(f"data/sedona_tiles/series_{res}m{ss}_s[0-9]*{sfx}/*.tif")
        rx = r"series_[^/]*_s(\d+)(?:_h\d+)?/t_(\d+)_(\d+)\.tif$"
        layers = df.select(F.regexp_extract("path", rx, 1).cast("int").alias("k"),
                           F.regexp_extract("path", rx, 2).cast("int").alias("tx"),
                           F.regexp_extract("path", rx, 3).cast("int").alias("ty"), "content")
        # group the compressed bytes per tile, decode after the shuffle
        g = layers.groupBy("tx", "ty").agg(F.array_sort(F.collect_list(F.struct("k", "content"))).alias("l"))
        stack = g.select("tx", "ty", F.expr(union12("RS_FromGeoTiff(element_at(l, {k}).content)")).alias("r"))
    else:
        parts = []
        for k in range(1, 13):
            t = (spark.read.format("binaryFile").load(f"data/series/{res}m/s{k}.tif")
                 .selectExpr(f"RS_TileExplode(RS_FromGeoTiff(content), {tile}, {tile})")
                 .select(F.lit(k).alias("k"), F.col("x").alias("tx"), F.col("y").alias("ty"), F.col("tile").alias("t")))
            parts.append(t)
        u = parts[0]
        for t in parts[1:]:
            u = u.unionByName(t)
        g = u.repartition(4 * nt, "tx", "ty").groupBy("tx", "ty").agg(
            F.array_sort(F.collect_list(F.struct("k", "t"))).alias("l"))
        stack = g.select("tx", "ty", F.expr(union12("element_at(l, {k}).t")).alias("r"))
    src = stack
    expr = jiffle("out = (isnull(rast[0]) || rast[0] == -9999) ? -9999 : (" + " + ".join(f"rast[{k}]" for k in range(12)) + ") / 12;")
elif op == "resample":
    rs_in = os.environ.get("RS_IN", "3")
    import rasterio

    with rasterio.open(f"data/elev_{res}m.tif") as t:
        gx, gy, sx = t.transform.c, t.transform.f, t.res[0]
    src = tiles_of(f"elev_{rs_in}m")
    expr = f"RS_Resample(r, {sx}, {-sx}, {gx}, {gy}, true, 'Bicubic')"
else:
    src = tiles_of(f"elev_{res}m")
    if op == "algebra":
        expr = jiffle("e = rast[0]; out = (isnull(e) || e == -9999) ? -9999 : " + ops_expr.render("grass", "e") + ";")
    else:
        raise SystemExit(f"unknown op {op}")

if stop == "read":
    force(src, "read")
    sys.exit(0)
outs = {"": expr}
results = {suf: src.select("tx", "ty", F.expr(e).alias("r")) for suf, e in outs.items()}
if stop == "compute":
    for suf, df in results.items():
        force(df, f"compute{suf}")
    sys.exit(0)
for suf, df in results.items():
    (df.select(F.expr("RS_AsGeoTiff(r, 'Deflate', 1.0)").alias("g"),
               F.format_string("t_%d_%d", "tx", "ty").alias("name"))
     .write.format("raster").mode("overwrite").option("rasterField", "g").option("pathField", "name")
     .option("fileExtension", ".tif").save(f"{out}{suf}"))
    stamp(f"write{suf}")
