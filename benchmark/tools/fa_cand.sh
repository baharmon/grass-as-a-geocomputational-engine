#!/usr/bin/env bash
# Flow accumulation (D8) of Landlab and PCRaster through ops_cand.py op fa: PKG=landlab (FlowAccumulator,
# FlowDirectorD8 + DepressionFinderAndRouter) or PKG=pcraster (lddcreate removing every pit, accuflux).
# Pinned like the other runs (PIN, default 0-15; all = no pinning). Output out/acc_<pkg>_<res>m.tif (cells).
cd "$(dirname "$0")/.."
[ "${PIN:-0-15}" = all ] && pin= || pin="taskset -c ${PIN:-0-15}"
case ${PKG:?PKG=landlab or pcraster} in
    landlab) py=.venv-cand/bin/python ;;
    pcraster) py=$PWD/mamba/root/envs/pcraster/bin/python ;;
    *) echo "no flow accumulation for $PKG" >&2; exit 2 ;;
esac
MPLCONFIGDIR=$PWD/out/ops/.mpl OMP_NUM_THREADS=${NTHREADS:-16} $pin /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE \
    $py -I ops_cand.py $PKG fa $1 out/acc_${PKG}_$1m
