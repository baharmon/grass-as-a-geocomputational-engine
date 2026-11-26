#!/usr/bin/env bash
# PYSHEDS_ROUTING: d8 (default) or mfd.
cd "$(dirname "$0")/.."
r=${PYSHEDS_ROUTING:-d8}
sfx=${r/d8/}
v=${PYSHEDS_DTYPE:+_f64}${PYSHEDS_EPS:+_eps$PYSHEDS_EPS}
env ${PYSHEDS_DTYPE:+PYSHEDS_DTYPE=$PYSHEDS_DTYPE} ${PYSHEDS_EPS:+PYSHEDS_EPS=$PYSHEDS_EPS} OPENBLAS_NUM_THREADS=1 /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE .venv/bin/python pysheds_flowacc.py data/elev_${1}m.tif out/acc_pysheds${sfx:+_$sfx}${v}_${1}m.tif $r
