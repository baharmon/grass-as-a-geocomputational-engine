#!/usr/bin/env bash
# TAUDEM_NP: MPI processes (default 1). With >1, peak RSS is per process; use the cgroup peak.
# TAUDEM_ROUTING: d8 (default) or dinf.
# TAUDEM_DEM: input DEM instead of data/elev_<res>m.tif; TAUDEM_TAG: output suffix (with TAUDEM_DEM).
cd "$(dirname "$0")/.."
R=$PWD/mamba/root/envs/r
T=$PWD/mamba/root/envs/taudem
r=${TAUDEM_ROUTING:-d8}
sfx=${r/d8/}
PATH=$T/bin:$PATH TAUDEM_PATH=$T/bin PROJ_DATA=$R/share/proj GDAL_DATA=$R/share/gdal TMPDIR=$PWD/out \
    /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE \
    $R/bin/Rscript traudem_flowacc.R ${TAUDEM_DEM:-data/elev_${1}m.tif} out/acc_taudem${sfx:+_$sfx}${TAUDEM_TAG:+_$TAUDEM_TAG}_${1}m.tif ${TAUDEM_NP:-1} "" $r
