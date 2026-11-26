#!/usr/bin/env bash
# Whitebox Workflows (Python wheel of whitebox_next_gen; RustGIS/GeoLibre run its fork geolibre-rust):
# fill_depressions -> d8_flow_accum / fd8_flow_accum. WBNG_METHOD = d8 (default) or fd8;
# WBNG_DEPS = fill (default), natural (flat_resolution=natural) or breach (least-cost breaching);
# WBNG_PROCS = RAYON_NUM_THREADS (default all; wbe.max_procs alone has no effect, and GeoTIFF
# compression uses further threads); WBNG_CORES = CPU list for taskset (e.g. 0 = one core).
cd "$(dirname "$0")/.."
m=${WBNG_METHOD:-d8}
d=${WBNG_DEPS:-fill}
sfx=${d/fill/}
env ${WBNG_PROCS:+RAYON_NUM_THREADS=$WBNG_PROCS} ${WBNG_CORES:+taskset -c $WBNG_CORES} /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE \
    .venv-wbng/bin/python -I wbng_flowacc.py data/elev_${1}m.tif out/wbng/acc_${m}${sfx:+_$sfx}_${1}m.tif $m r $d
