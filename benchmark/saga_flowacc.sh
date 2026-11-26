#!/usr/bin/env bash
# Flow accumulation with SAGA 9.3.1 (Ubuntu 24.04 packages, extracted without root into saga/root):
# Fill Sinks XXL (Wang & Liu, minimum slope 0.1 degree, the variant for large grids) ->
# Flow Accumulation (Top-Down), D8 (METHOD=0; the SAGA default is MFD), unit: cells.
# Usage: saga_flowacc.sh <dem.tif> <out.tif> [method]   (SAGA_CORES: number of cores, default all)
# SAGA_MINSLOPE: Fill Sinks XXL minimum slope in degrees (default 0.1, SAGA's default).
set -e
SAGA_CORES=${SAGA_CORES:-${NTHREADS:-}}  # explicit when NTHREADS is set (SAGA's default: all CPUs it can see)
S="$(cd "$(dirname "$0")" && pwd)/saga/root/usr"
export LD_LIBRARY_PATH=$S/lib/x86_64-linux-gnu SAGA_TLB=$S/lib/x86_64-linux-gnu/saga SAGA_SHARE=$S/share/saga
filled="${2%.tif}_filled.sdat"
"$S/bin/saga_cmd" ${SAGA_CORES:+--cores=$SAGA_CORES} --flags=q ta_preprocessor 5 -ELEV="$1" -FILLED="$filled" ${SAGA_MINSLOPE:+-MINSLOPE=$SAGA_MINSLOPE}
"$S/bin/saga_cmd" ${SAGA_CORES:+--cores=$SAGA_CORES} --flags=q ta_hydrology 0 -ELEVATION="$filled" -FLOW="$2" \
    -METHOD="${3:-0}" -FLOW_UNIT=0
rm -f "${filled%.sdat}".*
