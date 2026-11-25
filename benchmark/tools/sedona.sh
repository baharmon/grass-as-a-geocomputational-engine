#!/usr/bin/env bash
# Apache Sedona 1.9.1 (Spark 4.1 local mode, Java 21) raster operations, one step per call:
# tools/sedona.sh <res>, with OP = algebra | series | resample and
# SEDONA_STEP = start | read | compute | write (sedona_ops.py stops after that step) | mosaic | tile.
#   mosaic: GDAL gdalbuildvrt + gdal_translate of the written tiles onto the grid of data/elev_<res>m.tif,
#           one DEFLATE GeoTIFF out/ops/<op>_sedona_<res>m.tif (as the other packages write).
#   tile:   GDAL split of the inputs of OP into TILE x TILE GeoTIFFs in data/sedona_tiles/ (SEDONA_INPUT=tiles,
#           for rasters too large for one Sedona raster object).
# HALO=<n> (default 0): overlapping tiles for operations that read neighbouring cells (tools/sedona_gdal.py): tile cuts tiles with n
# cells of their neighbours into data/sedona_tiles/<name>_h<n>/, Sedona reads those (sedona_ops.py, TILE_SUFFIX),
# mosaic cuts each result tile back to its own area. Bicubic resampling needs 2 (source cells).
# NTHREADS: Spark cores and GDAL threads (default 8). SEDONA_HEAP: JVM heap (default 48g). Time and peak RSS
# go to $TIMEFILE (/usr/bin/time) and $PEAKFILE (JVM VmHWM, written by sedona_ops.py).
cd "$(dirname "$0")/.."
r=$1 np=${NTHREADS:-8} T=${TILE:-2048} Q=$PWD/mamba/root/envs/qgis/bin H=${HALO:-0}
hs=$([ "$H" -gt 0 ] && echo _h$H)
# SERIES_SET=<name>: the series stack data/series/<res>m_<name> (e.g. sun, the 12 r.sun layers), outputs series_<name>_*
ss=$([ "$OP" = series ] && [ -n "${SERIES_SET:-}" ] && echo _$SERIES_SET)
o=out/sedona/tiles/${OP}${ss}_${r}m$hs
case $OP in  # the input raster that defines the tile grid
    series) src=data/series/${r}m$ss/s1.tif ;;
    resample) src=data/elev_${RS_IN:-3}m.tif ;;
    *) src=data/elev_${r}m.tif ;;
esac
. out/sedona/env.sh
case ${SEDONA_STEP:?set SEDONA_STEP} in
    start | read | compute | write)
        rm -rf $o
        TILE_SUFFIX=$hs SERIES_SET=${ss#_} SEDONA_STOP=$SEDONA_STEP /usr/bin/time -f "%e %M %x %U %S" -o "$TIMEFILE" \
            .venv-sedona/bin/python -I sedona_ops.py $OP $r $o ;;
    mosaic)
        if [ "$H" -gt 0 ]; then
            /usr/bin/time -f "%e %M %x %U %S" -o "$TIMEFILE" $Q/python -I tools/sedona_gdal.py mosaic $o \
                out/ops/${OP}_sedona_${r}m_h$H.tif data/elev_${r}m.tif $src $T $H $np
            exit
        fi
        te=$(.venv-xrs/bin/python -c "import rasterio; b = rasterio.open('data/elev_${r}m.tif'); print(*b.bounds, *b.res)")
        set -- $te
        /usr/bin/time -f "%e %M %x %U %S" -o "$TIMEFILE" bash -c '
            find '"$o"' -name "t_*.tif" > '"$o"'.list &&
            '"$Q"'/gdalbuildvrt -q -overwrite -te '"$1 $2 $3 $4"' -tr '"$5 $6"' -input_file_list '"$o"'.list '"$o"'.vrt &&
            '"$Q"'/gdal_translate -q -co COMPRESS=DEFLATE -co TILED=YES -co BIGTIFF=IF_SAFER -co NUM_THREADS='"$np"' \
                --config GDAL_NUM_THREADS '"$np"' '"$o"'.vrt out/ops/${OP}'"$ss"'_sedona_'"$r"'m.tif' ;;
    tile)
        if [ "$H" -gt 0 ]; then
            case $OP in
                series) ins=$(for k in $(seq 12); do echo "data/series/${r}m$ss/s$k.tif:series_${r}m${ss}_s$k"; done) ;;
                resample) ins="data/elev_${RS_IN:-3}m.tif:elev_${RS_IN:-3}m" ;;
                *) ins="data/elev_${r}m.tif:elev_${r}m" ;;
            esac
            /usr/bin/time -f "%e %M %x %U %S" -o "$TIMEFILE" bash -c '
                for io in '"$(echo $ins)"'; do
                    d=data/sedona_tiles/${io#*:}'"$hs"'; rm -rf $d
                    '"$Q"'/python -I tools/sedona_gdal.py tile ${io%%:*} $d '"$T $H $np"' || exit 1
                done'
            exit
        fi
        case $OP in
            series) ins=$(for k in $(seq 12); do echo "data/series/${r}m$ss/s$k.tif:series_${r}m${ss}_s$k"; done) ;;
            resample) ins="data/elev_${RS_IN:-3}m.tif:elev_${RS_IN:-3}m" ;;
            *) ins="data/elev_${r}m.tif:elev_${r}m" ;;
        esac
        /usr/bin/time -f "%e %M %x %U %S" -o "$TIMEFILE" bash -c '
            for io in '"$(echo $ins)"'; do
                f=${io%%:*} d=data/sedona_tiles/${io#*:}; rm -rf $d; mkdir -p $d
                read w h < <('"$Q"'/gdalinfo $f | sed -n "s/^Size is \([0-9]*\), \([0-9]*\)/\1 \2/p")
                for ((y = 0; y * '"$T"' < h; y++)); do for ((x = 0; x * '"$T"' < w; x++)); do
                    echo "$x $y $((x * '"$T"')) $((y * '"$T"')) $(( (x + 1) * '"$T"' > w ? w - x * '"$T"' : '"$T"' )) $(( (y + 1) * '"$T"' > h ? h - y * '"$T"' : '"$T"' ))"
                done; done | xargs -P '"$np"' -L 1 sh -c "'"$Q"'/gdal_translate -q -srcwin \$2 \$3 \$4 \$5 -co COMPRESS=DEFLATE $f $d/t_\$0_\$1.tif" || exit 1
            done' ;;
    *) echo "unknown SEDONA_STEP=$SEDONA_STEP" >&2; exit 2 ;;
esac
