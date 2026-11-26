#!/usr/bin/env bash
# RICHDEM_METHOD: D8 (default) or Freeman (MFD, exponent 1.1). RICHDEM_THREADS: OpenMP threads (default: all).
# RICHDEM_DTYPE=float64 and RICHDEM_EPS=1: variants (see richdem_flowacc.py), output suffix _f64 / _eps.
cd "$(dirname "$0")/.."
R=$PWD/mamba/root/envs/richdem
m=${RICHDEM_METHOD:-D8}
v=${RICHDEM_DTYPE:+_f64}${RICHDEM_EPS:+_eps}
env ${RICHDEM_DTYPE:+RICHDEM_DTYPE=$RICHDEM_DTYPE} ${RICHDEM_EPS:+RICHDEM_EPS=$RICHDEM_EPS} PROJ_DATA=$R/share/proj GDAL_DATA=$R/share/gdal ${RICHDEM_THREADS:+OMP_NUM_THREADS=$RICHDEM_THREADS} \
    /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE \
    $R/bin/python -I richdem_flowacc.py data/elev_${1}m.tif out/acc_richdem_${m,,}${v}_${1}m.tif $m
