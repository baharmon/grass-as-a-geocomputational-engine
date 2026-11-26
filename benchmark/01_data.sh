#!/usr/bin/env bash
# Inputs of the benchmark (untimed), all under data/ and the GRASS project project_iceland/:
#   1. ArcticDEM v4.1 10 m mosaic tiles covering Iceland (24 tiles) and the Natural Earth 10 m admin-0 polygons
#   2. a source GRASS project data/raw/iceland (EPSG:3413): tiles imported and patched (raster iceland), the Iceland
#      polygon (vector iceland)
#   3. prep_iceland.sh: region = the landmass bounding box on the 10 m grid, DEM masked to the polygon (the sea becomes
#      no-data), voids inside the polygon filled with the nearest value, 20/50/100 m averages; then -9999 no-data
#      (nan_to_nodata.py; TauDEM, RichDEM, terra and pysheds MFD mishandle NaN) -> data/elev_ice{10,20,50,100}m.tif
#   4. project_iceland/PERMANENT with elev_ice10m, elev_ice20m, elev_ice100m
#   5. least-cost inputs (prep_cost.py): friction = 1 + slope / 5 (degrees, Horn), start (Reykjavik) and end
#      (Akureyri) points and rasters, imported as friction_ice10m
#   6. the series stack: 12 r.sun global irradiation layers (mid-month days, step 0.5 h) computed at 100 m and
#      interpolated bilinearly onto the 10 m grid within the DEM (prep_series_sets.sh): GRASS maps sersun<k>_ice10m,
#      GeoTIFFs data/series/ice10m_sun/s<k>.tif
# Needs network for step 1 (about 30 GB of tile archives). Usage: ./01_data.sh
set -eu
cd "$(dirname "$0")"
. ./config.sh
G=$GRASS_BIN
Q=$PWD/mamba/root/envs/qgis/bin
PY=$PWD/.venv-xrs/bin/python
ADEM=${ADEM_URL:-https://data.pgc.umn.edu/elev/dem/setsm/ArcticDEM/mosaic/v4.1/10m}
NE=${NE_URL:-https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip}
TILES="14_51 14_52 14_53 14_54 15_50 15_51 15_52 15_53 15_54 16_50 16_51 16_52 16_53 16_54 16_55
       17_50 17_51 17_52 17_53 17_54 17_55 18_53 18_54 18_55"  # the tiles patched into the reference DEM
raw=data/raw
mkdir -p $raw/arcticdem $raw/naturalearth data/nan_originals data/cost data/series

echo "== 1. download $(date +%FT%T)"
for t in $TILES; do
    f=$raw/arcticdem/${t}_10m_v4.1.tar.gz
    [ -s $raw/arcticdem/${t}_10m_v4.1_dem.tif ] && continue
    curl -fL -C - -o $f "$ADEM/$t/${t}_10m_v4.1.tar.gz"
    tar -xzf $f -C $raw/arcticdem --wildcards '*_dem.tif' && rm -f $f
done
[ -s $raw/naturalearth/ne_10m_admin_0_countries.shp ] ||
    { curl -fL -o $raw/naturalearth/ne.zip "$NE" && (cd $raw/naturalearth && unzip -o ne.zip && rm ne.zip); }

echo "== 2. source project $(date +%FT%T)"
if [ ! -d $raw/iceland/PERMANENT ]; then
    $G -c EPSG:3413 -e $raw/iceland
    $G $raw/iceland/PERMANENT --exec bash -c "set -e
        dems=
        for f in $PWD/$raw/arcticdem/*_dem.tif; do
            n=\$(basename \$f .tif); r.import --q input=\$f output=\$n; dems=\$dems,\$n
        done
        dems=\${dems#,}
        g.region raster=\$dems res=10
        r.patch --q input=\$dems output=iceland memory=1000 nprocs=$NTHREADS
        g.remove -f --q type=raster pattern='*_10m_v4.1_dem'
        r.univar -g iceland | grep -E '^n='
        v.import --q input=$PWD/$raw/naturalearth/ne_10m_admin_0_countries.shp output=countries extent=region
        v.extract --q input=countries output=iceland where=\"admin='Iceland'\"
        g.remove -f --q type=vector name=countries"
fi

echo "== 3. DEMs $(date +%FT%T)"
if [ ! -s data/elev_ice10m.tif ]; then
    OUT=$PWD/data/nan_originals $G --tmp-mapset $raw/iceland --exec bash prep_iceland.sh
    for r in 10 20 50 100; do $PY -I nan_to_nodata.py data/nan_originals/elev_ice${r}m.tif data/elev_ice${r}m.tif; done
fi
# expected: 10 m 49,368 x 43,326 cells, 1,060,309,263 with values; 20 m 24,684 x 21,664, 265,162,192 with values

echo "== 4. project_iceland $(date +%FT%T)"
[ -d project_iceland/PERMANENT ] || $G -c data/elev_ice10m.tif -e project_iceland
$G project_iceland/PERMANENT --exec bash -c "set -e
    for r in 10 20 100; do
        g.findfile element=cell file=elev_ice\${r}m > /dev/null ||
            r.in.gdal --q input=$PWD/data/elev_ice\${r}m.tif output=elev_ice\${r}m memory=300
    done
    g.region raster=elev_ice10m
    r.univar -g elev_ice10m | grep -E '^(n|null_cells)='"

echo "== 5. least-cost inputs $(date +%FT%T)"
[ -s data/cost/friction_ice10m.tif ] || PATH=$Q:$PATH $PY -I prep_cost.py ice10
$G project_iceland/PERMANENT --exec bash -c "g.findfile element=cell file=friction_ice10m > /dev/null ||
    r.in.gdal --q input=$PWD/data/cost/friction_ice10m.tif output=friction_ice10m"

echo "== 6. r.sun series stack $(date +%FT%T)"
NPROCS=$NTHREADS SUN_RES=ice100 ./prep_series_sets.sh ice10 sun
echo "== done $(date +%FT%T)"
