"""Figure 2's points and numbers from one results directory (no hand-typed values), Iceland 10 m.
Usage: paper_data.py <results directory> ice10 <output directory>
Writes into the output directory:
  paper_points.csv   one row per operation and package (selection rule below), with ratios: the data of Figure 2
  paper_numbers.csv  every number the paper cites (key, value, how it is computed)
Selection rule (user, 2026-11-10 and 2026-11-12), per package and operation:
  - Candidates give the same result: repeats (time = median over them), memory-limit reruns, threads,
    processes, and settings that only trade memory (GDAL block cache, terra todisk, dask chunks).
  - Main point: among the candidates within TIE of the fastest, the one with the least memory.
  - Alternative point (alt_* columns): the least-memory candidate when it needs at most 1 / ALT of the main
    point's memory (so it is slower beyond TIE); drawn linked to the main point, not in the median.
  - Variants that change the result are not candidates: the batch runs only each package's closest
    setting (README section 14), and its flags say so (approximate, incomplete, no path).
  - GRASS: one point per configuration (role), linked.
  - status dnf: no candidate finished. reason: time limit, memory limit (also a package's own memory guard)
    or error; with the memory it had reached, the limit, and for a time limit the cap.
  - User-written code (user, 2026-11-13; decided from the effort, never from the result):
    flag user: natural use, the package provides the mechanism and we pass a standard function or expression,
      tile the data the documented way, or run its operations on threads (xarray-spatial focal median, Sedona
      algebra and resampling, GeoTools parallel tiles): drawn hollow, in the median and quartiles;
  - The median and quartiles of the others are over their main points.
Memory: peak RSS of the largest process; for multi-process tools (TauDEM MPI) the cgroup peak
(an upper bound: it includes page cache), or the lowest memory limit the run passed, if lower.
"""

import csv
import math
import statistics as st
import sys
from pathlib import Path

from summarize_ops import summary

RESULTS = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
RES = (sys.argv[2] if len(sys.argv) > 2 else "ice10") + "m"
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else "out/figure2")
TIE = 0.05
ALT = 2  # an alternative point needs at most 1 / ALT of the main point's memory
HOST_GB = (lambda v: int(v) if v.isdigit() else float(v))(__import__("os").environ.get("HOST_GB", "125"))  # machine RAM (the reference machine: 125); a run without MemoryMax is limited by it
CELLS = {"ice10m": 49368 * 43326}
DEM_GB = CELLS[RES] * 4 / 2**30  # Float32 in memory, GiB like the memory columns
MULTIPROC = ("traudem_np",)

# operation -> [(package, label, name, memmax, role, flags)]; role: lowmem / inmem (GRASS) or "" (others)
I = "infinity"
def ops_ice():
    """The eight operations of the paper at Iceland 10 m, run names as in runs.tsv without ops_(grass|other)_ and
    _r<n>; every memory limit of a name is a candidate."""
    f = "flow accumulation"
    nt = int(__import__("os").environ.get("NTHREADS", 8))  # run names carry the thread count (02_runs.sh)
    fa_grass = [("GRASS", "r.terraflow memory=500", "grass_terraflow_sfd_m500", I, "lowmem", ""),
         ("GRASS", "r.watershed -m memory=2400", "r.watershed_m2400_sfd_2560M", I, "mid", ""),
         ("GRASS", "r.watershed -m memory=2400", "r.watershed_m2400_sfd_3G", I, "mid", ""),
         ("GRASS", "r.watershed -m memory=2400", "r.watershed_m2400_sfd", I, "mid", "")]  # no limit (2026-11-16)
    ops = {f: fa_grass + [("GRASS", "r.watershed -s", "r.watershed_sfd", I, "inmem", ""),
               ("TauDEM", f"TauDEM, {nt} processes", f"traudem_np{nt}", I, "", ""),
               ("Whitebox Workflows", f"{nt} threads", f"wbng_d8_natural_t{nt}", I, "", ""),
               ("WhiteboxTools", "WBT 2.4", f"wbt_d8_t{nt}", I, "", ""),
               ("RichDEM", "RichDEM, Float64", f"richdem_d8_f64_t{nt}", I, "", "input doubled"),
               ("SAGA", "SAGA, minimum slope 0.01", "saga_ms0.01", I, "", ""),
               ("pysheds", "pysheds, Float64, eps 1e-9", "pysheds_d8_f64_eps", I, "", "incomplete"),
               ("pyflwdir", "pyflwdir", "pyflwdir_d8", I, "", ""),
               ("terra", "terra (no fill)", "terra_d8", I, "", "incomplete"),
               ("TopoToolbox", "TopoToolbox", "topotoolbox_d8", I, "", ""),
               ("xarray-spatial", "xarray-spatial (no flats)", "xrs_d8", I, "", "incomplete memguard")]}
    title = {"cost": "least-cost distance + path", "relief": "shaded relief", "resample": "resampling, bicubic",
             "slope": "slope + aspect", "algebra": "raster algebra", "series": "series mean, 12 layers",
             "focal": "focal median 25 × 25"}
    grass = {"cost": [("memory=300", "cost_grass_m300", "lowmem"), ("memory=20000", "cost_grass_m20000", "inmem")],
             "relief": [("r.relief", "relief_grass", "lowmem")],
             "resample": [("memory=300", f"resample_grass_m300_n{nt}", "lowmem"),
                          ("memory=20000", f"resample_grass_m20000_n{nt}", "inmem")],
             "slope": [("r.slope.aspect", f"slope_grass_n{nt}", "lowmem")],
             "algebra": [("r.mapcalc", f"algebra_grass_n{nt}", "lowmem")],
             "series": [("r.series", "series_sun_grass_fcell", "lowmem")],  # FCELL maps
             "focal": [("r.neighbors", f"focal_grass_n{nt}", "lowmem")]}
    pk = {"gdal": "GDAL", "terra": "terra", "saga": "SAGA", "wbw": "Whitebox Workflows", "wbt": "WhiteboxTools",
          "xrs": "xarray-spatial", "xrsdask": "xarray-spatial dask", "tt": "TopoToolbox", "richdem": "RichDEM",
          "qgis": "QGIS", "sedona": "Sedona"}
    # settings that only trade memory; reruns of the same setting; QGIS relief only with the corrected sun angle
    common = ["", "_cache64", "_todisk"]
    variants = {("cost", "wbw"): ["_sdat"], ("focal", "terra"): ["_narm"],
                # rerun of 2026-11-26 with BigTIFF output (the classic TIFF of the runs before was unreadable above 4 GiB)
                ("series", "wbw"): ["_bigtiff_b"]}
    only = {("relief", "qgis"): ["_v60"]}
    flags = {("focal", "wbw"): "approximate", ("focal", "wbt"): "approximate", ("cost", "terra"): "no path",
             ("cost", "xrs"): "memguard",
             ("focal", "xrs"): "user", ("focal", "xrsdask"): "user",  # our numba median in focal.apply
             # user: our pipeline around the package's own functions (GDAL tiles -> Sedona -> GDAL mosaic); drawn hollow
             ("algebra", "sedona"): "user", ("resample", "sedona"): "user", ("series", "sedona"): "user"}
    for op, t in title.items():
        tag = "series_sun" if op == "series" else op  # the 12 r.sun layers (user, 2026-11-10)
        ops[t] = [("GRASS", lab, n, I, role, "") for lab, n, role in grass[op]]
        for p, name in pk.items():
            if p == "sedona":  # pipeline rows from results_sedona (sedona_rows()); series on the r.sun stack (2026-11-16)
                if op in ("algebra", "resample", "series"):
                    ops[t].append((name, name, f"sedona_{op}", I, "", flags.get((op, p), "")))
                continue
            for v in only.get((op, p), common + variants.get((op, p), [])):
                ops[t].append((name, name, f"{tag}_{p}{v}", I, "", flags.get((op, p), "")))
    # candidate packages, cand_batch.sh 2026-11-12/13 (NIGHT_2026-11-12.md); xdemmp = xDEM out-of-memory mode
    cpk = {"rt": "raster_tools", "xdem": "xDEM", "xdemmp": "xDEM", "skimage": "scikit-image", "landlab": "Landlab",
           "pcraster": "PCRaster", "gdistance": "gdistance", "otb": "Orfeo ToolBox", "geotools": "GeoTools",
           "pyflwdir": "pyflwdir", "pcrastermc": "PCRaster", "xdemmpw": "xDEM"}  # pyflwdir: cost surface found by the coverage audit (2026-11-16)
    # pcrastermc: pcraster.multicore on 8 threads; xdemmpw: xDEM out-of-memory mode on 8 worker processes; OTB focal:
    # BandMathX 21 x 21, its largest window (mc_after_otb.sh, otb_focal_ice.sh, 2026-11-20; user: every finished run
    # in the figure, 2026-11-21; xdemmpw slope hung twice and has no time)
    cops = {"relief": ["rt", "xdem", "xdemmp", "xdemmpw", "landlab", "geotools"],
            "slope": ["rt", "xdem", "xdemmp", "landlab", "pcraster", "pcrastermc"],
            "focal": ["rt", "xdem", "skimage", "geotools", "otb"],
            "algebra": ["rt", "xdem", "pcraster", "pcrastermc", "otb", "geotools"],
            "series": ["rt", "xdem", "pcraster", "otb", "geotools"],
            "resample": ["rt", "xdem", "xdemmp", "xdemmpw", "skimage", "otb", "geotools"],
            "cost": ["rt", "skimage", "pcraster", "gdistance", "pyflwdir"]}
    # approximate: scikit-image resampling is a spline; OTB resampling and the scikit-image focal median differ next
    # to no-data cells only; raster_tools resampling has seams at its chunk edges (NIGHT_2026-11-12.md, follow-up)
    cflags = {("cost", "rt"): "no path", ("cost", "pcraster"): "no path", ("cost", "pyflwdir"): "no path", ("resample", "skimage"): "approximate",
              ("resample", "otb"): "approximate", ("focal", "skimage"): "approximate",
              ("resample", "rt"): "approximate", ("focal", "geotools"): "approximate",  # JAI median and bicubic: no-data edges
              ("resample", "geotools"): "approximate", ("focal", "otb"): "approximate"}  # OTB: 21 x 21
    for op, ps in cops.items():
        tag = "series_sun" if op == "series" else op
        # xDEM's algebra, series and resampling are GeoUtils code (xdem.DEM is a geoutils Raster): label only,
        # the package stays xDEM so that it counts once
        lab = lambda p: "xDEM (GeoUtils)" if p in ("xdem", "xdemmp", "xdemmpw") and op in ("algebra", "series", "resample") \
            else cpk[p]  # noqa: E731
        ops[title[op]] += [(cpk[p], lab(p), f"{tag}_{p}", I, "", cflags.get((op, p), "")) for p in ps]
    # GeoTools with a 2 GB JAI tile cache (only trades memory; the 64 MB default thrashes in resampling)
    ops[title["resample"]].append(("GeoTools", "GeoTools", "resample_geotools_c2g", I, "", "approximate"))
    # GeoTools with our parallel tile computation (natural use, flag user; geotools/Ops.java GT_PARALLEL)
    for op in ("relief", "focal", "resample"):
        ops[title[op]].append(("GeoTools", "GeoTools", f"{op}_geotoolspar", I, "",
                               "user" if op == "relief" else "user approximate"))
    ops[f] += [(cpk[p], cpk[p], f"fa_cand_{p}_d8", I, "", "") for p in ("landlab", "pcraster")]
    return ops


OPS = ops_ice()
MAIN = list(OPS)


def measured(s, name, memmax, res=RES):
    v = s.get((name, res, memmax))
    if not v or v["n"] == 0:
        return None
    mem = v["rss"]
    if name.startswith(MULTIPROC):  # cgroup peak (includes page cache), capped by the lowest limit it ran under
        mem = min([v["cg"]] + [float(m[:-1]) for (n, r, m), x in s.items()
                                if (n == name or n.startswith(name + "_rerun")) and r == res and m.endswith("G")
                                and x["n"]])
    return dict(wall=v["wall"], mem=mem, cpu_s=v.get("cpu_s"), n=v["n"], spread=v["spread"])


def pick(cands):
    """Fastest; within TIE of the fastest, the one with less memory."""
    cands = [c for c in cands if c[1]]
    if not cands:
        return None
    t0 = min(c[1]["wall"] for c in cands)
    return min((c for c in cands if c[1]["wall"] <= t0 * (1 + TIE)), key=lambda c: c[1]["mem"])


def alternative(cands, main):
    """The least-memory candidate when it needs at most 1 / ALT of the main point's memory, else None."""
    c = min((c for c in cands if c[1]), key=lambda c: c[1]["mem"])
    return c if c[1]["mem"] * ALT <= main[1]["mem"] else None


def limit_gb(memmax):
    return HOST_GB if memmax == I else float(memmax[:-1]) if memmax.endswith("G") else int(memmax) / 2**30


def cap_s(t):
    """Time limit of paper_iceland.sh cap_for(): k x GRASS's fastest time, k = 10 up to 0.5 h, 3 from 2 h on,
    log-linear between, at least 1 h."""
    h = t / 3600
    k = 10 if h <= 0.5 else 3 if h >= 2 else 10 * (h / 0.5) ** (math.log(0.3) / math.log(4))
    return max(k * t, 3600)


def candidates(s, op, spec):
    """(package, role) -> [(spec entry with the run's memmax, measured or None)]: every memory limit a name ran
    under."""
    groups = {}
    seen = set()
    for pkg, label, name, memmax, role, flags in spec:
        for m in sorted({k[2] for k in s if k[0] == name and k[1] == RES}):
            if (name, m) in seen:
                continue
            seen.add((name, m))
            groups.setdefault((pkg, role if pkg == "GRASS" else ""), []).append(
                ((pkg, label, name, m, role, flags), measured(s, name, m)))
        groups.setdefault((pkg, role if pkg == "GRASS" else ""), [])
    return groups


def dnf(s, cands, grass_fastest):
    """Why a package has no finished candidate: the attempt with the largest memory limit."""
    tries = [(c, s[(c[2], RES, c[3])]) for c, m in cands if (c[2], RES, c[3]) in s]
    if not tries:
        return None
    c, v = max(tries, key=lambda t: limit_gb(t[0][3]))
    rc = v["rc"]
    reason = ("memory limit" if rc == "143" or "memguard" in c[5] else "time limit" if rc == "124" else "error")
    cap = (v.get("cap_s") or (cap_s(grass_fastest) if grass_fastest else None)) if reason == "time limit" else None
    return c, dict(reason=reason, rc=rc, mem_reached_GB=round(v.get("cg", 0.0), 3),
                   limit_GB=round(limit_gb(c[3]), 3), cap_s=None if cap is None else round(cap))


def points(s):
    rows = []
    for op, spec in OPS.items():
        groups = candidates(s, op, spec)
        sel, failed = {}, {}
        for key, cands in groups.items():
            if not cands:
                continue
            p = pick(cands)
            if p:
                sel[key] = (p, alternative(cands, p))
            else:
                failed[key] = cands
        g_fast = min((m["wall"] for (pkg, _), ((c, m), a) in sel.items() if pkg == "GRASS"), default=None)
        walls = [sel[k][0][1]["wall"] for k in sel if k[0] != "GRASS"]
        base = {}
        # Figure 2 (user, 2026-11-19): GRASS by the same rule as the others, one main point among its configurations
        # and linked lower-memory ones (each at most 1 / ALT of the memory of the one before), and the median and
        # quartiles over all packages, GRASS's main point included (fig, time_per_median, all_q1, all_q3)
        gk = [k for k in sel if k[0] == "GRASS"]
        gmain = pick([sel[k][0] for k in gk]) if gk else None
        fig, chain = {}, []
        for k in sorted(gk, key=lambda k: -sel[k][0][1]["mem"]):
            m = sel[k][0][1]
            if sel[k][0] is gmain:
                fig[k] = "main"
            elif m["mem"] * ALT <= (chain[-1] if chain else gmain[1]["mem"]) and m["mem"] < gmain[1]["mem"]:
                fig[k] = "alt"
                chain.append(m["mem"])
            else:
                fig[k] = ""  # within TIE of the main point but with more memory: a candidate, not drawn
        walls_all = walls + ([gmain[1]["wall"]] if gmain else [])
        med_all = st.median(walls_all) if walls_all else None
        qa = st.quantiles(walls_all, n=4, method="inclusive") if len(walls_all) >= 2 else [med_all] * 3
        base.update(all_q1=None if not med_all else round(qa[0] / med_all, 3),
                    all_q3=None if not med_all else round(qa[2] / med_all, 3))
        for (pkg, role), ((c, m), a) in sel.items():
            r = dict(op=op, package=pkg, label=c[1], name=c[2], memmax=c[3], role=role, flags=c[5],
                     status="ok", n=m["n"], wall_s=round(m["wall"], 2),
                     mem_GB=round(m["mem"], 3), cpu_s=None if m["cpu_s"] is None else round(m["cpu_s"], 1),
                     spread=round(m["spread"], 3), mem_per_dem=round(m["mem"] / DEM_GB, 3),
                     **base,
                     fig=fig.get((pkg, role), "main"),
                     time_per_median=None if not med_all else round(m["wall"] / med_all, 3))
            if a:
                r.update(alt_name=a[0][2], alt_memmax=a[0][3], alt_wall_s=round(a[1]["wall"], 2),
                         alt_flags=a[0][5],  # its own marking (GeoTools as shipped: no "user")
                         alt_mem_GB=round(a[1]["mem"], 3), alt_mem_per_dem=round(a[1]["mem"] / DEM_GB, 3),
                         alt_time_per_median=None if not med_all else round(a[1]["wall"] / med_all, 3))
            rows.append(r)
        for (pkg, role), cands in failed.items():
            d = dnf(s, cands, g_fast)
            c = d[0] if d else cands[0][0]
            r = dict(op=op, package=pkg, label=c[1], name=c[2], memmax=c[3], role=role, flags=c[5],
                     status="dnf" if d else "missing", **base)
            if d:
                x = d[1]
                r.update(reason=x["reason"], rc=x["rc"], mem_reached_GB=x["mem_reached_GB"], limit_GB=x["limit_GB"],
                         cap_s=x["cap_s"],
                         mem_per_dem=round((x["limit_GB"] if x["rc"] == "143" else x["mem_reached_GB"]) / DEM_GB, 3),
                         time_per_median=round(x["cap_s"] / med_all, 3) if x["cap_s"] and med_all else None)
            rows.append(r)
    return rows


SHORT = ["shaded relief", "resampling, bicubic", "slope + aspect", "raster algebra", "series mean, 12 layers"]
UNLIMITED = (I, "110G", "100G")


def numbers(s, rows):
    """Every number the paper's benchmark paragraph and Figure 2's caption cite, with how it is computed."""
    out = []

    def add(key, value, how):
        out.append(dict(key=key, value=value, how=how))

    ok = [r for r in rows if r["status"] == "ok"]
    main = [r for r in ok if r["fig"] == "main"]
    grass = [r for r in ok if r["package"] == "GRASS"]
    others = [r for r in main if r["package"] != "GRASS"]
    add("dem_cells", CELLS[RES], "49,368 x 43,326")
    add("dem_in_memory_GB", round(CELLS[RES] * 4 / 1e9, 2), "cells x 4 bytes (Float32), 10^9 bytes")
    add("dem_in_memory_GiB", round(DEM_GB, 3), "cells x 4 bytes, 2^30 bytes: the unit of the memory ratios")
    pk = sorted({r["package"].replace(" dask", "") for r in rows if r["package"] != "GRASS"}, key=str.lower)
    add("other_packages", len(pk), "with a point or a run that did not finish (xarray-spatial on NumPy and on dask "
        "counted once): " + ", ".join(pk))
    # time: GRASS's fastest configuration / median of all packages' main points, GRASS included
    tp = {}
    for op in MAIN:
        r = min((r for r in grass if r["op"] == op), key=lambda r: r["wall_s"])
        tp[op] = r["time_per_median"]
        add(f"{op} | GRASS fastest | time / median", r["time_per_median"], r["label"])
    add("GRASS fastest | time / median | range", f"{min(tp.values()):.2f}-{max(tp.values()):.2f}",
        f"over the {len(tp)} operations")
    # memory: GRASS's main point and the other packages' main points, relative to the DEM in memory
    for op in MAIN:
        r = next(r for r in grass if r["op"] == op and r["fig"] == "main")
        add(f"{op} | GRASS main point | memory / DEM", r["mem_per_dem"], r["label"])
    nf = [r["mem_per_dem"] for r in grass if r["fig"] == "main" and r["op"] != "flow accumulation"]
    add("GRASS main point | memory / DEM | largest outside flow accumulation", max(nf), "below 0.1: less than a tenth")
    meds = {}
    for op in MAIN:
        m = [r["mem_per_dem"] for r in others if r["op"] == op]
        meds[op] = st.median(m)
        add(f"{op} | other packages | median memory / DEM", round(meds[op], 2), f"{len(m)} main points")
        add(f"{op} | other packages | main points at or above the DEM size", f"{sum(x >= 1 for x in m)} of {len(m)}", "")
    add("other packages | median memory / DEM | range", f"{min(meds.values()):.2f}-{max(meds.values()):.2f}",
        f"over the {len(meds)} operations")
    add("other packages | main points at or above the DEM size",
        f"{sum(r['mem_per_dem'] >= 1 for r in others)} of {len(others)}", "all operations")
    # flow accumulation: every GRASS configuration
    for r in sorted((r for r in grass if r["op"] == "flow accumulation"), key=lambda r: r["wall_s"]):
        add(f"flow accumulation | GRASS {r['label']} | time / median", r["time_per_median"], "")
        add(f"flow accumulation | GRASS {r['label']} | memory / DEM", r["mem_per_dem"], "")
    # within 1 GB: a GRASS candidate run that finished under the 1 GiB limit, else one that peaked below 1 GiB
    for op in MAIN:
        names = {e[2] for e in OPS[op] if e[0] == "GRASS"}
        lim = [(v["wall"], n) for (n, r, m), v in s.items() if n in names and r == RES and m == str(2**30) and v["n"]]
        if lim:
            w, n = min(lim)
            add(f"{op} | GRASS within 1 GB", "1 GiB limit", f"{n}, {w:.0f} s")
            continue
        low = [(v["rss"], n) for (n, r, m), v in s.items() if n in names and r == RES and m in UNLIMITED and v["n"]]
        rss, n = min(low)
        add(f"{op} | GRASS within 1 GB", f"no limit, peak {rss:.2f} GiB", n)
    # time limits as applied: cap_s() from GRASS's fastest time
    for op in MAIN:
        t = min(r["wall_s"] for r in grass if r["op"] == op)
        add(f"{op} | time limit, h", round(cap_s(t) / 3600, 1), f"{cap_s(t) / t:.1f} x GRASS's fastest ({t:.0f} s)")
    d = [r for r in rows if r["status"] == "dnf"]
    add("did not finish | memory limits, GiB", ", ".join(f"{x:g}" for x in sorted({r["limit_GB"] for r in d
                                                                                  if r["reason"] == "memory limit"})),
        f"{sum(r['reason'] == 'memory limit' for r in d)} runs (MemoryMax, the machine's RAM without one, or the "
        f"package's own memory check); {sum(r['reason'] == 'time limit' for r in d)} runs at the time limit")
    # repeats: the fewest runs behind a short-operation point, and the repeated long runs
    fewest = {}
    for op in SHORT:
        for pkg in {r["package"] for r in ok if r["op"] == op}:
            n = max((v["n"] for e in OPS[op] if e[0] == pkg for (nm, r, m), v in s.items()
                     if nm == e[2] and r == RES and m in UNLIMITED), default=0)
            fewest[(op, pkg)] = n
    add("short operations | fewest runs without a memory limit per package", min(fewest.values()),
        f"over the {len(fewest)} points of the short operations")
    pairs = sorted({(n, v["spread"]) for op in MAIN if op not in SHORT for e in OPS[op]
                    for (n, r, m), v in s.items() if n == e[2] and r == RES and m in UNLIMITED and v["n"] >= 2})
    add("long operations | repeated runs", len(pairs), ", ".join(n for n, _ in pairs))
    add("long operations | repeated runs | largest difference, %", round(100 * max(x for _, x in pairs), 1),
        "(slowest - fastest) / median")
    return out


def sedona_rows(s):
    """Apache Sedona (results/sedona, tools/sedona.sh): one pipeline per operation, GDAL tiling +
    Sedona write + GDAL mosaic; resampling on overlapping tiles (_h2: no seams). Memory: the
    largest peak of the steps (JVM + Python, no cgroup). Added to the summary as sedona_<op>, unlimited."""
    p = Path(__import__("os").environ.get("SEDONA_RESULTS", RESULTS / "sedona")) / "runs.tsv"  # run_sb.sh rows
    if not p.exists():
        return
    sd = {r["tool"]: r for r in csv.DictReader(open(p), delimiter="\t") if r["res"] == RES}
    halo = {"resample": ("resample", "_h2")}
    for op in ("algebra", "resample", "series"):
        t, h = halo.get(op, (op, ""))
        sun = "_sun" if op == "series" else ""  # the series panel's r.sun stack (sedona_series_sun.sh)
        # repeats (_r2, _r3) of the whole pipeline are pooled as in summarize_ops.py: median of the pipeline times
        ok, first = [], None
        for rep in ("", "_r2", "_r3"):
            try:
                steps = [sd[f"sedona_{t}_tile{h}{sun}{rep}"], sd[f"sedona_{op}_write{h or '_tiles'}{sun}{rep}"]]
            except KeyError:
                continue
            if steps[1]["rc"] == "0":
                steps.append(sd[f"sedona_{op}_mosaic{h or '_tiles'}{sun}{rep}"])
            rc = next((r["rc"] for r in steps if r["rc"] != "0"), "0")
            mem = max(float(r[k]) for r in steps for k in ("peak_rss_GB", "cgroup_peak_GB") if r[k] not in ("NA", ""))
            first = first or (rc, mem)
            if rc == "0":
                ok.append((sum(float(r["wall_s"]) for r in steps), mem))
        if ok:
            w = st.median(x[0] for x in ok)
            mem = max(x[1] for x in ok)
            s[(f"sedona_{op}", RES, I)] = dict(n=len(ok), rc="0", wall=w, rss=mem, cg=mem, cpu=None, cpu_s=None,
                                               spread=(max(x[0] for x in ok) - min(x[0] for x in ok)) / w)
        elif first:
            s[(f"sedona_{op}", RES, I)] = dict(n=0, rc=first[0], cg=first[1], cap_s=None)


def main():
    s = summary(RESULTS / "runs.tsv")
    sedona_rows(s)
    rows = points(s)
    cols = ["op", "package", "label", "role", "flags", "status", "name", "memmax", "n", "wall_s", "mem_GB", "cpu_s",
            "spread", "mem_per_dem", "alt_name", "alt_memmax",
            "alt_wall_s", "alt_mem_GB", "alt_mem_per_dem", "reason", "rc",
            "mem_reached_GB", "limit_GB", "cap_s", "fig", "time_per_median", "all_q1", "all_q3", "alt_time_per_median",
            "alt_flags"]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "paper_points.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    with open(OUT / "paper_numbers.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["key", "value", "how"])
        w.writeheader()
        w.writerows(numbers(s, rows))
    miss = [f"{r['op']}: {r['package']}" for r in rows if r["status"] in ("missing", "dnf")]
    print(f"{RESULTS}: {len(rows)} points ({len(miss)} missing{': ' + '; '.join(miss) if miss else ''})")


if __name__ == "__main__":
    main()
