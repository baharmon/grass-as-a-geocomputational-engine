"""Write machine.csv: one row per machine_*.txt record that 02_runs.sh (`info`) writes at the start of each batch.

Columns: the record (file name), the batch settings, the CPU, memory, kernel, governor, turbo (no_turbo 1 = off) and
GRASS version. The instantaneous `CPU(s) scaling MHz` reading of lscpu is left out. Columns that no record has are
left out too.
Usage: python machine.py [results directory] > results/machine.csv
"""

import csv
import re
import sys
from pathlib import Path

results = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "results"
COLS = ["record", "date", "res", "rs_in", "rep", "focal", "memmax", "nthreads", "pinned_cpus", "xrs_chunk",
        "sig_digits", "min_cap_s", "cpu_model", "logical_cpus", "threads_per_core", "cores_per_socket",
        "cpu_max_mhz", "memory_gb", "kernel", "governor", "no_turbo", "grass", "affinity", "thread_env",
        "whitebox_tools_settings"]
rows = []
for f in sorted(results.glob("machine*.txt")):
    t = f.read_text()

    def g(pattern):
        m = re.search(pattern, t, re.M)
        return m.group(1).strip() if m else ""

    d = {"record": f.stem, "date": g(r"^date (\S+)") or g(r"^(\d{4}-\d\d-\d\dT\S+)$")}
    for key in ["res", "rs_in", "memmax", "nthreads", "xrs_chunk", "sig_digits", "min_cap_s", "kernel", "governor",
                "no_turbo", "affinity"]:
        d[key] = g(rf"\b{key} (\S+)")
    d["pinned_cpus"] = g(r"\bpinned_cpus (\S+)") or g(r"\bpinned_runs (\S+)") or g(r"\bcpus (\S+)")
    d["memory_gb"] = g(r"\bmemory_GB (\S+)")
    d["rep"] = g(r"\brep (\d+)")
    m = re.search(r"\bfocal (\S+) (\d+)", t)
    d["focal"] = f"{m.group(1)} {m.group(2)}" if m else ""
    d["cpu_model"] = g(r"^Model name:\s+(.*)$")
    d["logical_cpus"] = g(r"^CPU\(s\):\s+(\S+)$")
    d["threads_per_core"] = g(r"^Thread\(s\) per core:\s+(\S+)")
    d["cores_per_socket"] = g(r"^Core\(s\) per socket:\s+(\S+)")
    d["cpu_max_mhz"] = g(r"^CPU max MHz:\s+(\S+)")
    d["grass"] = g(r"^(?:grass )?(GRASS \S+)")
    d["thread_env"] = " ".join(re.findall(r"\b(\w+_NUM_THREADS \S+)", t))
    d["whitebox_tools_settings"] = g(r"^whitebox_tools_settings (.*)$")
    rows.append(d)
rows.sort(key=lambda d: d["date"])
cols = [c for c in COLS if any(d.get(c) for d in rows)]
w = csv.DictWriter(sys.stdout, cols, extrasaction="ignore", lineterminator="\n")
w.writeheader()
w.writerows(rows)
