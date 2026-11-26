#!/usr/bin/env bash
# Generic GRASS tool run: tools/grass.sh <res>; GCMD is the tool command with @R@ for the
# resolution. /usr/bin/time wraps the tool process itself inside the session.
cd "$(dirname "$0")/.."
G=${GRASS_BIN:-$PWD/grass-85-o2/bin.x86_64-pc-linux-gnu/grass}
cmd=${GCMD//@R@/$1}
GRASS_ADDON_BASE=${ADDONS:-$PWD/addons} $G ${GRASS_PROJECT:-project}/${GRASS_MAPSET:-PERMANENT} --exec bash -c \
    "g.region raster=elev_${1}m && /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE $cmd --o"
