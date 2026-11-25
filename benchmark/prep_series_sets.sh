#!/usr/bin/env bash
# 12-layer series stacks, untimed (01_data.sh uses sun; rand is kept for a hard-to-compress stack):
#   rand  layer k = DEM + rand(0, 1) (seed k): incompressible noise in the low bits, a hard case for compression
#   sun   layer k = r.sun global irradiation for a mid-month day k, computed at SUN_RES (default ice100) and
#         interpolated (bilinear) onto the <res> grid within the DEM; smooth, a soft case
# Each as GeoTIFF data/series/<res>m_<set>/s<k>.tif (deflate, tiled, BigTIFF) for the other packages and as GRASS
# maps ser<set><k>_<res>m in project_iceland/PERMANENT (tools/ops_*.sh SERIES_SET=<set>), FCELL like the
# DEM + k stack and the Float32 GeoTIFFs.
# Usage: [NPROCS=8] [SUN_RES=ice100] prep_series_sets.sh <res> [set...]   (sets default: rand sun); res ice*
set -eu
cd "$(dirname "$0")"
G=${GRASS_BIN:-$PWD/grass-85-o2/bin.x86_64-pc-linux-gnu/grass}
r=$1; shift
np=${NPROCS:-8} sr=${SUN_RES:-ice100}
DAYS=(17 47 75 105 135 162 198 228 258 288 318 344)
co="createopt=COMPRESS=DEFLATE,TILED=YES,BIGTIFF=YES"
for set in ${@:-rand sun}; do
    d=data/series/${r}m_$set
    mkdir -p $d
    $G project_iceland/PERMANENT --exec bash -c "set -e
        for k in \$(seq 12); do
            m=ser${set}\${k}_${r}m
            if ! g.findfile element=cell file=\$m > /dev/null; then
                case $set in
                    rand) g.region raster=elev_${r}m
                          r.mapcalc seed=\$k expression=\"\$m = float(elev_${r}m + rand(0.0, 1.0))\" nprocs=$np --q ;;
                    sun) g.region raster=elev_${sr}m
                         day=\$(echo ${DAYS[*]} | cut -d' ' -f\$k)
                         g.findfile element=cell file=sun_\${day}_${sr}m > /dev/null ||
                             r.sun elevation=elev_${sr}m glob_rad=sun_\${day}_${sr}m day=\$day step=0.5 nprocs=$np --q
                         g.region raster=elev_${r}m
                         r.resamp.interp input=sun_\${day}_${sr}m output=sun_tmp method=bilinear nprocs=$np --o --q
                         r.mapcalc expression=\"\$m = float(if(isnull(elev_${r}m), null(), sun_tmp))\" nprocs=$np --q
                         g.remove -f type=raster name=sun_tmp --q ;;
                    *) echo unknown set $set >&2; exit 2 ;;
                esac
            fi
            [ -s $PWD/$d/s\$k.tif ] || { g.region raster=elev_${r}m; r.out.gdal -c -f input=\$m output=$PWD/$d/s\$k.tif type=Float32 $co --q; }
        done
        g.region raster=elev_${r}m
        r.univar -g ser${set}1_${r}m | grep -E '^(n|min|max|mean)=' | tr '\n' ' '; echo"
    echo "$r: series set $set ready ($(du -sh $d | cut -f1) GeoTIFF)"
done
