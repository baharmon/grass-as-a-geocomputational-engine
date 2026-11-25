#!/usr/bin/env bash
cd "$(dirname "$0")/.."
${GRASS_BIN:-$PWD/grass-85-o2/bin.x86_64-pc-linux-gnu/grass} ${GRASS_PROJECT:-project}/${GRASS_MAPSET:-PERMANENT} --exec bash -c "g.region raster=elev_${1}m && /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE r.watershed ${RW_FLAGS:-} elevation=elev_${1}m accumulation=acc_${RW_TAG:-ram}_${1}m --o --q"
