#!/usr/bin/env bash
# WBT_METHOD: d8 (default) or fd8; WBT_PROCS: --max_procs (default: all).
cd "$(dirname "$0")/.."
sfx=${WBT_METHOD:+_$WBT_METHOD}
sfx=${sfx/_d8/}
/usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE ./wbt_flowacc.sh "$PWD/data/elev_${1}m.tif" "$PWD/out/acc_wbt${sfx}_${1}m.tif"
