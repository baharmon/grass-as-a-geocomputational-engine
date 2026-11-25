"""Write versions.csv: the version of every package behind Figure 2, read from the files that install them.

Sources, in the column `source`:
- envs/mamba_<env>.txt: explicit conda-forge lists (the package version is in each URL);
- envs/pip_<venv>.txt: pip freeze of each Python venv; envs/python_<venv>.txt: its Python;
- envs/saga_debs.txt: the Ubuntu packages of SAGA;
- 00_envs.sh: what it downloads by version (GRASS tag, Orfeo ToolBox, the jars, micromamba, traudem, the
  WhiteboxTools version it checks for);
- machine.csv: what was recorded on the machine at the start of the runs (kernel).
Usage: python versions.py [results directory with machine.csv] > versions.csv
"""

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENVS = HERE / "envs"
rows = []


def add(package, version, environment, source, note=""):
    rows.append([package, version, environment, source, note])


# conda-forge environments: package name -> label
CONDA = {
    "qgis": {"qgis": "QGIS", "gdal": "GDAL", "python": "Python"},
    "r": {"r-base": "R", "r-terra": "terra", "libgdal-core": "GDAL library"},
    "taudem": {"taudem": "TauDEM", "mpich": "MPICH"},
    "gdistance": {"r-gdistance": "gdistance", "r-raster": "raster (R)", "r-sp": "sp (R)", "r-base": "R"},
    "richdem": {"richdem": "RichDEM", "python": "Python"},
    "pcraster": {"pcraster": "PCRaster", "python": "Python"},
}
for env, names in CONDA.items():
    f = ENVS / f"mamba_{env}.txt"
    for url in f.read_text().split():
        m = re.search(r"/([a-z0-9_.-]+?)-([0-9][^-]*)-[^-/]+\.(conda|tar\.bz2)", url)
        if m and m.group(1) in names:
            add(names[m.group(1)], m.group(2).replace("_", "-"), env, f"envs/{f.name}")

# Python venvs: pip name -> label
PIP = {
    "venv": {"whitebox": "whitebox (Python wrapper of WhiteboxTools)", "pysheds": "pysheds", "pyflwdir": "pyflwdir",
             "numpy": "NumPy", "numba": "numba", "scikit-image": "scikit-image", "scipy": "SciPy",
             "rasterio": "rasterio"},
    "venv-wbng": {"whitebox-workflows": "Whitebox Workflows"},
    "venv-xrs": {"xarray-spatial": "xarray-spatial", "xarray": "xarray", "dask": "dask", "rioxarray": "rioxarray",
                 "odc-geo": "odc-geo", "topotoolbox": "TopoToolbox (pytopotoolbox)", "numpy": "NumPy",
                 "numba": "numba", "scipy": "SciPy", "rasterio": "rasterio"},
    "venv-cand": {"raster-tools": "raster_tools", "xdem": "xDEM", "geoutils": "GeoUtils", "scikit-image": "scikit-image",
                  "landlab": "Landlab", "dask": "dask", "xarray": "xarray", "numpy": "NumPy", "numba": "numba",
                  "scipy": "SciPy", "rasterio": "rasterio", "rioxarray": "rioxarray", "odc-geo": "odc-geo"},
    "venv-sedona": {"apache-sedona": "Apache Sedona (Python)", "pyspark": "PySpark", "numpy": "NumPy",
                    "rasterio": "rasterio"},
}
for venv, names in PIP.items():
    f = ENVS / f"pip_{venv}.txt"
    for line in f.read_text().splitlines():
        name, _, version = line.partition("==")
        if name.lower() in names:
            add(names[name.lower()], version, f".{venv}", f"envs/{f.name}")
    p = ENVS / f"python_{venv}.txt"
    if p.exists():
        add("Python", p.read_text().split()[-1], f".{venv}", f"envs/{p.name}")

# SAGA: Ubuntu packages
for deb in (ENVS / "saga_debs.txt").read_text().split():
    if deb.startswith("saga_"):
        add("SAGA", deb.split("_")[1], "saga/root", "envs/saga_debs.txt", "Ubuntu 24.04 package, extracted without root")

# what 00_envs.sh downloads by version
s = (HERE / "00_envs.sh").read_text()
add("GRASS", re.search(r"archive/refs/tags/([^/]+)\.tar\.gz", s).group(1), "grass-85-o2", "00_envs.sh",
    "built from the tag with -O2 (grass_build_o2.sh), no addons")
add("Orfeo ToolBox", re.search(r"OTB-([0-9.]+)-Linux", s).group(1), "otb", "00_envs.sh", "official Linux package")
add("micromamba", re.search(r"MMV=([0-9.]+)", s).group(1), "mamba", "00_envs.sh")
add("traudem", re.search(r"traudem_([0-9.]+)\.tar\.gz", s).group(1), "r", "00_envs.sh", "CRAN archive")
m = re.search(r"geotools-wrapper-([0-9.]+)-([0-9.]+)\.jar", s)
add("GeoTools", m.group(2), "envs/sedona_jars", "00_envs.sh", f"geotools-wrapper {m.group(1)}-{m.group(2)}")
m = re.search(r"sedona-spark-shaded-([0-9.]+)_([0-9.]+)-([0-9.]+)\.jar", s)
add("Apache Sedona", m.group(3), "envs/sedona_jars", "00_envs.sh", f"sedona-spark-shaded for Spark {m.group(1)}, Scala {m.group(2)}")
add("WhiteboxTools", re.search(r"must report v([0-9.]+)", s).group(1), ".venv", "00_envs.sh",
    "binary fetched by the whitebox Python package; 00_envs.sh checks this version")

# machine record
results = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "results"
mc = results / "machine.csv"
if mc.exists():
    kernels = sorted({r["kernel"] for r in csv.DictReader(mc.open()) if r.get("kernel")})
    if kernels:
        add("Linux kernel", ", ".join(kernels), "", f"{results.name}/machine.csv")

w = csv.writer(sys.stdout, lineterminator="\n")
w.writerow(["package", "version", "environment", "source", "note"])
w.writerows(rows)
