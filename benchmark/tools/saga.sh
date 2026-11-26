#!/usr/bin/env bash
# SAGA_METHOD: 0 = D8 (default here), 4 = MFD (SAGA's own default). SAGA_MINSLOPE: fill minimum slope
# (degrees; output suffix _ms<value>).
cd "$(dirname "$0")/.."
v=${SAGA_MINSLOPE:+_ms$SAGA_MINSLOPE}
/usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE ./saga_flowacc.sh data/elev_${1}m.tif out/acc_saga_m${SAGA_METHOD:-0}${v}_${1}m.tif ${SAGA_METHOD:-0}
