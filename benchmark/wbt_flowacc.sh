#!/usr/bin/env bash
# Flow accumulation with WhiteboxTools: FillDepressions (with flat fixing), then
# D8FlowAccumulation (WBT_METHOD=d8, default) or FD8FlowAccumulation (WBT_METHOD=fd8: MFD,
# Freeman 1991, default exponent 1.1). Output in cells. WBT_PROCS sets --max_procs.
# Usage: wbt_flowacc.sh <dem.tif> <out.tif>
set -e
WBT_PROCS=${WBT_PROCS:-${NTHREADS:--1}}  # never the value stored in WBT/settings.json (-1 = all)
WBT="$(dirname "$0")/.venv/lib/python3.12/site-packages/whitebox/WBT/whitebox_tools"
filled="${2%.tif}_filled.tif"
"$WBT" --max_procs=$WBT_PROCS --compress_rasters=true -r=FillDepressions --dem="$1" --output="$filled" --fix_flats
if [ "${WBT_METHOD:-d8}" = fd8 ]; then
    "$WBT" --max_procs=$WBT_PROCS --compress_rasters=true -r=FD8FlowAccumulation --dem="$filled" --output="$2" --out_type=cells
else
    "$WBT" --max_procs=$WBT_PROCS --compress_rasters=true -r=D8FlowAccumulation --input="$filled" --output="$2" --out_type=cells
fi
rm -f "$filled"
