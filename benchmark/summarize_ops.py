"""Medians of results_ops/runs.tsv (ops_batch.sh): wall time, peak RSS, CPU/wall per pipeline,
resolution and memory limit; repeats (_r1.._r3) pooled; failed runs listed with their rc.
CPU time: median of cpu_s; runs without cpu_s give cpu_s=None."""
import csv, re, statistics as st, sys
from collections import defaultdict



def load(p="results_ops/runs.tsv"):
    g = defaultdict(list)
    for row in csv.DictReader(open(p), delimiter="\t"):
        name = re.sub(r"^ops_(grass|other)_|_r\d$", "", row["tool"])
        g[(name, row["res"], row["memmax"])].append(row)
    return g


def summary(p="results_ops/runs.tsv"):
    out = {}
    for k, rows in load(p).items():
        ok = [x for x in rows if x["rc"] == "0"]
        if not ok:
            cg = rows[-1].get("cgroup_peak_GB")  # memory reached when it stopped (0 or NA when unknown)
            out[k] = dict(n=0, rc=rows[-1]["rc"], cg=float(cg) if cg not in (None, "", "NA") else 0.0)
            continue
        w = st.median(float(x["wall_s"]) for x in ok)
        has_cpu = all(x.get("cpu_s") not in (None, "", "NA") for x in ok)
        out[k] = dict(n=len(ok), rc="0", wall=w, rss=max(float(x["peak_rss_GB"]) for x in ok),
                      cpu=st.median(float(x["cpu_s"]) / float(x["wall_s"]) for x in ok) if has_cpu else None,
                      cg=max(float(x["cgroup_peak_GB"]) for x in ok),
                      cpu_s=st.median(float(x["cpu_s"]) for x in ok) if has_cpu else None,
                      spread=(max(float(x["wall_s"]) for x in ok) - min(float(x["wall_s"]) for x in ok)) / w)
    return out


if __name__ == "__main__":
    order = {"10m": 0, "3m": 1, "1m": 2}
    print(f"{'pipeline':32s} {'res':>4s} {'limit':>8s} {'n':>2s} {'rc':>4s} {'wall s':>8s} {'rss GB':>7s} {'cpu/wall':>8s} {'spread':>6s}")
    p = sys.argv[1] if len(sys.argv) > 1 else "results_ops/runs.tsv"
    for (t, r, m), v in sorted(summary(p).items(), key=lambda kv: (kv[0][0], order[kv[0][1]], kv[0][2])):
        if v["n"] == 0:
            print(f"{t:32s} {r:>4s} {m:>8s} {0:>2d} {v['rc']:>4s}")
        else:
            print(f"{t:32s} {r:>4s} {m:>8s} {v['n']:>2d} {'0':>4s} {v['wall']:8.1f} {v['rss']:7.2f} {v['cpu'] or float('nan'):8.1f} {v['spread']:6.0%}")
