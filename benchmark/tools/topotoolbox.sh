#!/usr/bin/env bash
# Flow accumulation (D8) in TopoToolbox (FlowObject, flow_accumulation): fa_py.py.
# TopoToolbox is built with OpenMP (OMP_NUM_THREADS). Pinned to the 16 physical cores 0-15 like the other multi-threaded runs (PIN=all: no pinning).
cd "$(dirname "$0")/.."
[ "${PIN:-0-15}" = all ] && pin= || pin="taskset -c ${PIN:-0-15}"
MPLCONFIGDIR=$PWD/out/ops/.mpl NUMBA_NUM_THREADS=${NTHREADS:-16} OMP_NUM_THREADS=${NTHREADS:-16} $pin /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE \
    .venv-xrs/bin/python -I fa_py.py tt data/elev_${1}m.tif out/acc_tt_${1}m.tif
