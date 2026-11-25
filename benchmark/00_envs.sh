#!/usr/bin/env bash
# Software of the benchmark, installed into this directory (no root needed except for the system packages listed in
# README.md, which GRASS's build, SAGA's libraries and Java need). Pinned: conda-forge environments from explicit
# package lists (envs/mamba_*.txt), Python venvs from pip freezes (envs/pip_*.txt), SAGA 9.3.1 from the Ubuntu 24.04
# packages, GRASS 8.5.0 built from its tag with -O2, Orfeo ToolBox 9.1.1, GeoTools 33.5 / Sedona 1.9.1 jars,
# WhiteboxTools 2.4.0. Needs network. Usage: [GRASS_SRC=<clone of OSGeo/grass>] ./00_envs.sh [step...]
#   steps (default all, in this order): micromamba conda traudem venvs saga grass otb jars wbt sedona_env
set -eu
cd "$(dirname "$0")"
MM=$PWD/mamba/bin/micromamba
MMV=2.9.0  # micromamba version of the reference run
step_micromamba() {
    [ -x $MM ] && return
    mkdir -p mamba && curl -fLs https://micro.mamba.pm/api/micromamba/linux-64/$MMV | tar -xj -C mamba bin/micromamba
}
step_conda() {  # R + terra, TauDEM, RichDEM, QGIS (also GDAL for the GDAL runs and the data steps), PCRaster, gdistance
    for e in r taudem richdem qgis pcraster gdistance; do
        [ -d mamba/root/envs/$e ] || $MM -r mamba/root create -y -n $e --file envs/mamba_$e.txt
    done
}
step_traudem() {  # traudem 1.0.3 is on CRAN only; its R dependencies are in the r environment
    mamba/root/envs/r/bin/Rscript -e 'if (!requireNamespace("traudem", quietly = TRUE)) install.packages(
        "https://cran.r-project.org/src/contrib/Archive/traudem/traudem_1.0.3.tar.gz", repos = NULL, type = "source")'
}
step_venvs() {  # Python 3.12 (Ubuntu 24.04 python3); one venv per group whose pins conflict
    for v in venv venv-wbng venv-xrs venv-cand venv-sedona; do
        [ -d .$v ] || { python3 -m venv .$v && .$v/bin/pip install -q -r envs/pip_$v.txt; }
    done
}
step_saga() {  # SAGA 9.3.1: the Ubuntu 24.04 packages extracted without root into saga/root
    mkdir -p saga/debs saga/root
    (cd saga/debs && for d in $(cat ../../envs/saga_debs.txt); do
        [ -s "$d" ] || apt-get download "${d%%_*}=$(echo "$d" | cut -d_ -f2)"; done)
    for d in saga/debs/*.deb; do dpkg-deb -x "$d" saga/root; done
}
step_grass() {  # GRASS 8.5.0 (tag 8.5.0, 8d6ceba290), -O2, no addons
    [ -x grass-85-o2/bin.x86_64-pc-linux-gnu/grass ] && return
    if [ -n "${GRASS_SRC:-}" ]; then
        git -C "$GRASS_SRC" archive 8.5.0 | (mkdir -p grass-85-o2 && tar -x -C grass-85-o2)
    else
        curl -fL https://github.com/OSGeo/grass/archive/refs/tags/8.5.0.tar.gz | (mkdir -p grass-85-o2 && tar -xz --strip-components=1 -C grass-85-o2)
    fi
    cp grass_build_o2.sh grass-85-o2/build-o2.sh
    (cd grass-85-o2 && bash build-o2.sh)
}
step_otb() {  # Orfeo ToolBox 9.1.1 (self-contained Linux package)
    [ -x otb/bin/otbcli_BandMath ] && return
    curl -fL -o otb/OTB-9.1.1-Linux.tar.gz https://www.orfeo-toolbox.org/packages/archives/OTB/OTB-9.1.1-Linux.tar.gz
    tar -xzf otb/OTB-9.1.1-Linux.tar.gz -C otb
}
step_jars() {  # GeoTools 33.5 (geotools-wrapper) and Sedona 1.9.1 (Spark 4.1, Scala 2.13), from Maven Central
    mkdir -p envs/sedona_jars
    local m=https://repo1.maven.org/maven2
    [ -s envs/sedona_jars/geotools-wrapper-1.9.1-33.5.jar ] || curl -fL -o envs/sedona_jars/geotools-wrapper-1.9.1-33.5.jar \
        $m/org/datasyslab/geotools-wrapper/1.9.1-33.5/geotools-wrapper-1.9.1-33.5.jar
    [ -s envs/sedona_jars/sedona-spark-shaded-4.1_2.13-1.9.1.jar ] || curl -fL -o envs/sedona_jars/sedona-spark-shaded-4.1_2.13-1.9.1.jar \
        $m/org/apache/sedona/sedona-spark-shaded-4.1_2.13/1.9.1/sedona-spark-shaded-4.1_2.13-1.9.1.jar
}
step_wbt() {  # WhiteboxTools: the whitebox Python package downloads the binary on first use; it must report v2.4.0
    .venv/bin/python -c "import whitebox; whitebox.WhiteboxTools().version()" >/dev/null
    .venv/lib/python3.12/site-packages/whitebox/WBT/whitebox_tools --version | head -1
}
step_sedona_env() {  # sourced by tools/sedona.sh: Spark on localhost with its scratch space in out/sedona/tmp
    mkdir -p out/sedona/tmp
    cat > out/sedona/env.sh <<EOF
export SPARK_LOCAL_HOSTNAME=localhost SPARK_LOCAL_IP=127.0.0.1 SPARK_LOCAL_DIRS=$PWD/out/sedona/tmp
export JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$PWD/out/sedona/tmp"
EOF
}
for s in ${@:-micromamba conda traudem venvs saga grass otb jars wbt sedona_env}; do
    echo "== $s $(date +%FT%T)"
    step_$s
done
echo "== done $(date +%FT%T); versions: versions.csv (python3 versions.py > versions.csv)"
