#!/usr/bin/env bash
# Agreement of the outputs (untimed; reads the outputs of the last run of each package in out/ops and out/, so run it
# right after 02_runs.sh, before anything overwrites them). Interior land cells only. Results in $RESULTS/agreement/:
#   agree_ice10.txt         GRASS as the reference (agree_ice.py; it exports the GRASS outputs first): relief |r|,
#                           slope r and mean |d|, resampling and focal median max / mean |d|, least-cost distance r,
#                           algebra max relative difference to a float64 NumPy reference
#   agree_series_ice10.txt  series mean on the r.sun stack, every package against GDAL (agree_cand.py)
#   agree_added_ice10.txt   the packages added after the main batch, against GDAL (cost: GRASS r.cost)
#   agree_sedona_ice10.txt  Sedona mosaics against GDAL (sedona_check.py)
#   fa_check_ice10.txt      flow accumulation: land cells without value, sea cells with value, maximum (fa_check.py)
# Usage: ./03_checks.sh
set -u
cd "$(dirname "$0")"
. ./config.sh
PY=$PWD/.venv-xrs/bin/python
R=$RESULTS/agreement
mkdir -p $R
taskset -c "$CPUS" $PY agree_ice.py ice10 relief slope resample focal cost algebra > $R/agree_ice10.txt 2>&1
PKGS=qgis taskset -c "$CPUS" $PY agree_ice.py ice10 relief slope >> $R/agree_ice10.txt 2>&1
# GRASS's series output on the r.sun stack (mapset ops, map smean of the last r.series run) for the series check
$GRASS_BIN $GRASS_PROJECT/$GRASS_OPS_MAPSET --exec bash -c "g.region raster=elev_ice10m@PERMANENT && r.out.gdal -c -f --q --o \
    input=smean output=$PWD/out/ops/series_sun_grass_ice10m.tif type=Float32 createopt=COMPRESS=DEFLATE,TILED=YES,BIGTIFF=YES" \
    > /dev/null 2>&1
# one package per call: all thirteen in one call ran out of memory
for p in grass terra saga wbw wbt xrs xrsdask qgis rt xdem pcraster otb geotools; do
    AGREE_OPS=series SERIES_SET=sun taskset -c "$CPUS" $PY agree_cand.py ice10 $p
done > $R/agree_series_ice10.txt 2>&1
# SERIES_SET=sun: the candidate runs were made with it, so their outputs are named <op>_sun_<package>
# one package per call: all fifteen in one call ran out of memory
for p in rt xdem xdemmp xdemmpw skimage landlab pcraster pcrastermc gdistance otb pyflwdir geotools geotools_c2g geotoolspar; do
    AGREE_OPS="relief slope focal algebra resample cost fa" SERIES_SET=sun taskset -c "$CPUS" $PY agree_cand.py ice10 $p
done > $R/agree_added_ice10.txt 2>&1
for f in out/ops/algebra_sedona_ice10m.tif out/ops/series_sun_sedona_ice10m.tif out/ops/resample_sedona_ice10m_h2.tif; do
    [ -e "$f" ] || continue
    ref=$(echo "$f" | sed 's/_sedona_/_gdal_/; s/_h[12]//')
    echo "$f vs $ref: $($PY -I sedona_check.py $f $ref 2>&1 | tail -1)"
done > $R/agree_sedona_ice10.txt
# GRASS flow accumulation outputs (mapset tier1) as GeoTIFF for the check
$GRASS_BIN $GRASS_PROJECT/$GRASS_MAPSET --exec bash -c "g.region raster=elev_ice10m@PERMANENT
    for m in acc_sfd_ice10m acc_m2400_sfd_ice10m tf_acc_sfd_ice10m; do
        g.findfile element=cell file=\$m > /dev/null &&
            r.out.gdal -c -f --q --o input=\$m output=$PWD/out/\${m/acc_/acc_grass_}.tif type=Float64 \
                createopt=COMPRESS=DEFLATE,TILED=YES,BIGTIFF=YES
    done" > /dev/null 2>&1
taskset -c "$CPUS" $PY fa_check.py ice10 out/acc_grass_sfd_ice10m.tif out/acc_grass_m2400_sfd_ice10m.tif \
    out/tf_acc_grass_sfd_ice10m.tif out/acc_taudem_ice10m.tif out/wbng/acc_d8_natural_ice10m.tif out/acc_wbt_ice10m.tif \
    out/acc_richdem_d8_f64_ice10m.tif out/acc_saga_m0_ms0.01_ice10m.tif out/acc_pysheds_f64_eps1e-9_ice10m.tif \
    out/acc_pyflwdir_ice10m.tif out/acc_terra_ice10m.tif out/acc_tt_ice10m.tif out/acc_xrs_ice10m.tif \
    out/acc_landlab_ice10m.tif out/acc_pcraster_ice10m.tif > $R/fa_check_ice10.txt 2>&1
tail -n +1 $R/agree_*ice10.txt $R/fa_check_ice10.txt
