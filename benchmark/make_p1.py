"""Figure 2 from paper_points.csv and paper_numbers.csv (paper_data.py).
Usage: .venv-xrs/bin/python make_p1.py <paper_data.py output dir> <figure dir> [--dnf=count|lane]
  -> <figure dir>/figure-benchmark.png (no title: the caption carries it); --dnf=lane and --grey add a suffix
One panel per main operation: memory / DEM in memory vs wall time / median of all packages, GRASS included
(log-log). Every package one point, no names, GRASS green and bigger; its slower
lower-memory runs small and linked (GRASS: each of its configurations that needs at most half the memory of
the one before; paper_points.csv column fig); hollow: approximate, incomplete or no path.
Runs that did not finish (status dnf), without names (user, 2026-11-12; meeting notes 2026-11-19):
  count  one hollow diamond per run in a column right of the panel's lower right corner, time and memory limit
         alike (the primary style).
  lane   a run stopped at the time limit is a hollow point with an up arrow at the limit and the memory it had
         reached; runs stopped by memory (a limit or the package's own guard) or an error go to a "did not finish"
         strip above the plot, placed by memory and counted when they coincide."""

import csv
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, LogLocator, NullFormatter  # noqa: E402

from memory_time_data import PKG  # noqa: E402

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DATA, FIGDIR = Path(ARGS[0]), Path(ARGS[1])
DNF = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dnf=")), "count")
# Other packages in the GRASS secondary (dark teal) brand color, grassdocs.css --gs-secondary-alt-color, and the
# interquartile band in its lighter teal (--gs-secondary-light-color), light like the green < 1x DEM area
# (variant 3, user 2026-11-20). --grey: the earlier grey dots and band.
GREY = "--grey" in sys.argv[1:]
DARK = TEAL_BAND = not GREY
GREEN, OTHER = PKG["GRASS"], ("#27575c" if DARK else "#9a9a9a")
BAND = dict(color="#4a787d", alpha=0.16) if TEAL_BAND else dict(color="#999", alpha=0.18)
PARTIAL = ("approximate", "incomplete", "no path", "user")  # user: user-written implementation
TOP = 25  # time / median above this: drawn at the top edge with its value


def num(x):
    return float(x) if x not in ("", "None", None) else None


rows = list(csv.DictReader(open(DATA / "paper_points.csv")))
for r in rows:
    for k in ("wall_s", "mem_GB", "mem_per_dem", "alt_mem_per_dem", "mem_reached_GB", "limit_GB", "cap_s",
              "time_per_median", "all_q1", "all_q3", "alt_time_per_median"):
        r[k] = num(r.get(k))
DEM = float({r["key"]: r["value"] for r in csv.DictReader(open(DATA / "paper_numbers.csv"))}["dem_in_memory_GiB"])
OPS = list(dict.fromkeys(r["op"] for r in rows if "supplement" not in r["op"]))
TITLE = {"flow accumulation": "Flow accumulation", "least-cost distance + path": "Least-cost distance & path",
         "shaded relief": "Shaded relief", "resampling, bicubic": "Bicubic resampling",
         "slope + aspect": "Slope & aspect", "raster algebra": "Raster algebra",
         "series mean, 12 layers": "Series mean (12 layers)", "focal median 25 × 25": "Focal median (25 × 25)"}
S_MAIN, S_ALT = 60, 14  # marker areas: every package's main point, its linked lower-memory runs
G_MAIN, G_ALT = 105, 24  # GRASS 1.75x the area of the others (as before 2026-11-19: easier to find)


def ticks(ax):
    f = FuncFormatter(lambda v, _: f"{v:g}×")
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_locator(LogLocator(base=10, subs=(1,) if a is ax.xaxis else (1, 2, 5)))
        a.set_major_formatter(f)
        a.set_minor_formatter(NullFormatter())


def panel(ax, op):
    pts = [r for r in rows if r["op"] == op]
    ok = [r for r in pts if r["status"] == "ok"]
    others = [r for r in ok if r["package"] != "GRASS"]
    dnf = [r for r in pts if r["status"] == "dnf" and r["package"] != "GRASS"]
    q = next((r for r in pts if r["all_q1"] is not None), None)
    if q:
        ax.axhspan(q["all_q1"], q["all_q3"], lw=0, **BAND)
    ax.axhline(1, color="#888", ls="--", lw=0.8)
    ax.axvline(1, color="#888", ls="--", lw=0.8)
    ax.axvspan(0.001, 1, color=GREEN, alpha=0.06, lw=0)
    for r in others:
        if r["alt_mem_per_dem"] is not None:
            ys = [min(r["time_per_median"], 22), min(r["alt_time_per_median"], 22)]
            ax.plot([r["mem_per_dem"], r["alt_mem_per_dem"]], ys, color=OTHER, lw=0.9, zorder=2.5)
            ah = any(f in r["alt_flags"] for f in PARTIAL)  # the linked run's own marking (user, 2026-11-19)
            ax.scatter(r["alt_mem_per_dem"], ys[1], s=S_ALT, facecolor="white" if ah else OTHER, edgecolor=OTHER,
                       lw=1.1 if ah else 0.6, zorder=3)
        x, y = r["mem_per_dem"], r["time_per_median"]
        if y > TOP:
            ax.scatter(x, 22, s=S_MAIN, marker="^", color=OTHER, zorder=3)
            ax.annotate(f"{y:.0f}×", (x, 22), xytext=(6, -2), textcoords="offset points", fontsize=6.5, color="#555",
                        va="center")
            continue
        hollow = any(f in r["flags"] for f in PARTIAL)
        ax.scatter(x, y, s=S_MAIN, facecolor="white" if hollow else OTHER, edgecolor=OTHER, lw=1.4 if hollow else 0.6,
                   zorder=3)
    g = sorted((r for r in ok if r["package"] == "GRASS" and r["fig"] in ("main", "alt")), key=lambda r: -r["mem_per_dem"])
    if g:  # the main point first, then its lower-memory configurations, linked in order of memory
        ax.plot([r["mem_per_dem"] for r in g], [r["time_per_median"] for r in g], color=GREEN, lw=1.0, zorder=2.5)
        for r in g:
            ax.scatter(r["mem_per_dem"], r["time_per_median"], s=G_MAIN if r["fig"] == "main" else G_ALT, color=GREEN,
                       zorder=4)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.003, max([30] + [1.6 * r[k] for r in pts for k in ("mem_per_dem", "alt_mem_per_dem") if r[k]]))
    ax.set_ylim(0.03, 30)
    ticks(ax)
    if DNF == "count":
        for i in range(len(dnf)):  # one per run, upward from the lower right corner, outside the plot area
            ax.scatter(1.045, 0.045 + i * 0.075, s=40, marker="d", facecolor="white", edgecolor=OTHER, lw=1.1,
                       transform=ax.transAxes, clip_on=False, zorder=4)
    if DNF == "lane":
        for r in dnf:
            if r["reason"] == "time limit" and r["time_per_median"]:
                x, y = r["mem_per_dem"], min(r["time_per_median"], 22)
                ax.annotate("", (x, y * 1.9), (x, y), zorder=3,
                            arrowprops=dict(arrowstyle="-|>", color=OTHER, lw=1, shrinkA=4, shrinkB=0))
                ax.scatter(x, y, s=40, facecolor="white", edgecolor=OTHER, lw=1.4, zorder=4)
        ax.set_ylim(0.03, 100)
        ax.axhspan(32, 100, color="#f2f2f2", lw=0, zorder=0)
        ax.axhline(32, color="#bbb", lw=0.8)
        ax.text(0.0045, 56, "did not finish", fontsize=6.5, color="#777", va="center")
        lane = {}
        for r in dnf:
            if not (r["reason"] == "time limit" and r["time_per_median"]):
                k = ("memory" if r["reason"] == "memory limit" else r["reason"], round(r["mem_per_dem"], 2))
                lane[k] = lane.get(k, 0) + 1
        last = None
        for (why, x), n in sorted(lane.items(), key=lambda t: t[0][1]):
            y = 44 if last and x / last[0] < 1.6 and last[1] == 62 else 62
            last = (x, y)
            ax.scatter(x, y, s=46, marker=">" if why == "memory" else "X", facecolor="white" if why == "memory" else OTHER,
                       edgecolor=OTHER, lw=1.3, zorder=4)
            if n > 1:
                ax.annotate(f"×{n}", (x, y), xytext=(6, 0), textcoords="offset points", fontsize=6.5, color="#555",
                            va="center")
        ax.yaxis.set_major_locator(FixedLocator([0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]))
    ax.set_title(TITLE.get(op, op[:1].upper() + op[1:]), fontsize=10, loc="left")
    ax.grid(True, color="#eee", lw=0.5)
    ax.tick_params(labelsize=7.5)


cols = 4
nrows = math.ceil(len(OPS) / cols)
fig, axes = plt.subplots(nrows, cols, figsize=(14.4, 3.6 * nrows), dpi=150, squeeze=False)
for ax, op in zip(axes.flat, OPS):
    panel(ax, op)
for ax in list(axes.flat)[len(OPS):]:
    ax.axis("off")
for ax in [axes[max(r for r in range(nrows) if r * cols + c < len(OPS)), c]
           for c in range(min(cols, len(OPS)))]:  # the lowest panel of each column
    ax.set_xlabel("Peak memory relative to the DEM size (log)", fontsize=8.5)
for ax in axes[:, 0]:
    ax.set_ylabel("Time relative to the median time (log)", fontsize=8.5)
ms_main, ms_alt = math.sqrt(S_MAIN), math.sqrt(S_ALT)
h = [Line2D([], [], marker="o", ls="", ms=math.sqrt(G_MAIN), color=GREEN, label="GRASS"),
     Line2D([], [], marker="o", ls="", ms=ms_main, color=OTHER, label="other packages"),
     Line2D([], [], marker="o", ms=ms_alt, color=OTHER, lw=0.9, label="same package, slower lower-memory run"),
     Line2D([], [], marker="o", ls="", ms=ms_main, color=OTHER, markerfacecolor="white", label="approximate result, omitted processing step, or user-written implementation"),
     plt.Rectangle((0, 0), 1, 1, **BAND, label="middle half of all packages (interquartile range)")]
if DNF == "count":
    h.append(Line2D([], [], marker="d", ls="", ms=6.5, color=OTHER, markerfacecolor="white",
                    label="did not finish (time or memory limit), one per package"))
if DNF == "lane":
    h[4:4] = [Line2D([], [], marker="$\\uparrow$", ls="", ms=7, color=OTHER, label="stopped at the time limit"),
              Line2D([], [], marker=">", ls="", ms=6, color=OTHER, markerfacecolor="white", label="stopped by memory")]
fig.legend(handles=h, loc="lower center", ncol=3, fontsize=8.5, frameon=False)
fig.tight_layout(rect=(0, 0.07, 0.985, 1), w_pad=2.5)  # right: the diamonds of the last column
out = FIGDIR / f"figure-benchmark{'' if DNF == 'count' else '_dnf-' + DNF}{'_grey' if GREY else ''}.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out)
print(out)
