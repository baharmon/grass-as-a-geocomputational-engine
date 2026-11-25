#!/usr/bin/env bash
cd "$(dirname "$0")/.."
R=$PWD/mamba/root/envs/r
PROJ_DATA=$R/share/proj GDAL_DATA=$R/share/gdal /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE \
    $R/bin/Rscript terra_flowacc.R data/elev_${1}m.tif out/acc_terra_${1}m.tif
